"""动态指导引擎 —— 支持真实多模态视觉理解

核心逻辑：
1. 有 visual_understanding → 用真实识别到的 UI 元素匹配步骤目标 → 精准坐标
2. 没视觉理解 → 走原 Stub 流程（适配器 target）
3. 根据步骤 + 用户状态决定指导颗粒度
"""
import logging

from app.models import Experiment, ExperimentStep
from app.schemas import AIGuideResponse, GuideTarget
from app.adapters.registry import get_adapter

logger = logging.getLogger(__name__)

# 四种指导颗粒度模板
LEVEL_TEMPLATES = {
    "brief": "请完成：{title}。{hint}",
    "annotate": "我已在屏幕上标注了操作目标（绿框）。请{action}。{hint}",
    "detailed": (
        "当前步骤详解：\n"
        "1. 打开目标软件或窗口\n"
        "2. {title}\n"
        "3. {instruction}\n"
        "预期结果：{expected}\n"
        "如仍遇到困难，可以告诉我具体的报错信息。"
    ),
    "demo": (
        "这是本步骤的局部示范：\n"
        "▸ 点击顶部菜单 → 选择对应功能\n"
        "▸ 在弹出的对话框中填写必要信息\n"
        "▸ 点击确认/Apply 按钮\n"
        "请尝试按照以上步骤操作，AI 会自动识别你的操作结果。"
    ),
}


class DynamicGuideEngine:
    """动态指导引擎"""

    def decide_level(
        self,
        experiment: Experiment,
        step_index: int,
        user_state: dict,
    ) -> str:
        levels = ["brief", "annotate", "detailed", "demo"]
        return levels[step_index % 4]

    def generate_guide(
        self,
        experiment: Experiment,
        steps: list[ExperimentStep],
        current_step_index: int,
        user_state: dict,
    ) -> AIGuideResponse:
        if current_step_index >= len(steps):
            current_step_index = len(steps) - 1
        if current_step_index < 0:
            current_step_index = 0

        step = steps[current_step_index]
        level = self.decide_level(experiment, current_step_index, user_state)

        # 模板填充
        hint = ""
        if step.common_errors:
            hint = f"常见坑：{'；'.join(step.common_errors[:2])}。"
        visual_hint = self._build_visual_hint(user_state)
        if visual_hint:
            hint = f"{hint} {visual_hint}".strip()
        template = LEVEL_TEMPLATES[level]
        instruction = template.format(
            title=step.title,
            action=f"完成「{step.title}」",
            instruction=step.instruction or "",
            expected=step.expected_result or "界面应有相应变化",
            hint=hint,
        )

        # ---------- 决定 target：视觉理解 > 适配器 > Stub ----------
        target: GuideTarget | None = None

        visual = user_state.get("visual_understanding")
        if visual:
            target = self._match_element_from_visual(visual, step)
            if target:
                logger.info("✓ 视觉理解匹配到目标: %s (%d,%d,%d,%d)", target.label,
                            target.x, target.y, target.width, target.height)

        if not target:
            adapter = get_adapter(experiment.type or experiment.software or "")
            if adapter:
                target_data = adapter.locate_target(step, user_state.get("screen_state"))
                if target_data:
                    target = GuideTarget(**target_data)

        if not target:
            # 没有真实视觉理解结果、适配器也无法定位 → 不产出假坐标
            # 坐标只能来自真实 UIA / 视觉识别，此处保持 None
            target = None

        return AIGuideResponse(
            level=level,
            instruction=instruction,
            target=target,
            expected_result=step.expected_result,
            common_errors=step.common_errors,
            next_action="complete_step",
        )

    # ====================================================================
    # 辅助：从视觉理解结果中匹配目标元素
    # ====================================================================
    @staticmethod
    def _match_element_from_visual(visual: dict, step: ExperimentStep) -> GuideTarget | None:
        """从视觉理解结果中匹配目标元素

        匹配优先级：
        1. 步骤的 adapter_hint（预写的英文关键词，最准确）
        2. 步骤标题/指令分词（中英双语，长关键词优先）
        3. 类型推断（"点击"→Button，"输入"→Edit）
        4. 兜底：confidence 最高的 Button 元素
        """
        elements = visual.get("elements", [])
        if not elements:
            return None

        # --- 1. adapter_hint ---
        hint_keywords: list[str] = []
        adapter_hint = getattr(step, "adapter_hint", None)
        if adapter_hint:
            if isinstance(adapter_hint, dict):
                hint_keywords = adapter_hint.get("keywords", [])
            elif isinstance(adapter_hint, list):
                hint_keywords = [str(x) for x in adapter_hint]
            elif isinstance(adapter_hint, str):
                hint_keywords = [adapter_hint]

        # --- 2. 步骤标题/指令分词（中英混合） ---
        step_text = f"{step.title} {step.instruction or ''}".lower()
        # 从中文提取可能的英文同义词（步骤标题 → 可能的按钮名）
        cn_to_en = {
            "数据库": ["schema", "database", "create schema", "create database"],
            "创建": ["create", "new", "add"],
            "表": ["table"],
            "编辑": ["edit", "modify", "alter"],
            "保存": ["save", "apply", "ok", "confirm"],
            "执行": ["execute", "run", "go"],
            "插入": ["insert"],
            "查询": ["select", "query", "search"],
            "更新": ["update"],
            "删除": ["delete", "remove"],
            "登录": ["login", "sign in", "connect"],
            "连接": ["connect", "connection"],
            "打开": ["open", "launch"],
            "代码": ["code", "editor", "main.py"],
        }
        expanded: list[str] = []
        for cn, ens in cn_to_en.items():
            if cn in step.title or cn in step.instruction:
                expanded.extend(ens)
        # 原始关键词（包含中文/英文/标点以外所有字符序列）
        for seg in step_text.replace("，", " ").replace("。", " ").replace("\n", " ").split():
            if len(seg) >= 2:
                expanded.append(seg)
        all_keywords = [k.lower() for k in hint_keywords + expanded]

        # --- 3. 遍历元素打分 ---
        best = None
        best_score = 0.0

        for el in elements:
            el_name = el.get("name", "").lower()
            ctrl_type = el.get("control_type", "").lower()
            score = 0.0

            # 关键词命中（长关键词权重更高）
            for kw in all_keywords:
                if len(kw) < 2:
                    continue
                if kw in el_name or el_name in kw:
                    score += len(kw) * 1.0
                    # 英文关键词在英文控件名里命中，再加倍
                    if kw.isalpha() and any(c.isalpha() for c in el_name):
                        score += 2.0

            # 类型推断加分
            if "点击" in step.title or "click" in step_text:
                if "button" in ctrl_type or "menu" in ctrl_type:
                    score += 5.0
            if "输入" in step.title or "填写" in step.title:
                if "edit" in ctrl_type or "input" in ctrl_type:
                    score += 5.0
            if "select" in step.title.lower() or "查询" in step.title:
                if "button" in ctrl_type:
                    score += 3.0

            # 控件自身 confidence 权重
            score += el.get("confidence", 0.5) * 2

            if score > best_score:
                best_score = score
                best = el

        if best and best_score > 0:
            return GuideTarget(
                x=int(best.get("x", 0)),
                y=int(best.get("y", 0)),
                width=int(best.get("width", 100)),
                height=int(best.get("height", 32)),
                label=best.get("name", step.title),
            )

        # --- 4. 兜底：confidence 最高的 Button ---
        buttons = [e for e in elements
                   if "button" in e.get("control_type", "").lower()
                   or "button" in e.get("name", "").lower()]
        if buttons:
            buttons.sort(key=lambda e: e.get("confidence", 0), reverse=True)
            b = buttons[0]
            return GuideTarget(
                x=int(b.get("x", 0)), y=int(b.get("y", 0)),
                width=int(b.get("width", 120)), height=int(b.get("height", 36)),
                label=b.get("name", step.title),
            )
        return None

    @staticmethod
    def _build_visual_hint(user_state: dict) -> str:
        """视觉理解结果 → 补充到指导里的一句话"""
        visual = user_state.get("visual_understanding")
        if not visual:
            return ""
        software = visual.get("software", "")
        state = visual.get("current_state", "")
        parts = []
        if software:
            parts.append(f"检测到当前软件：{software}")
        if state:
            parts.append(f"界面状态：{state}")
        return " | ".join(parts)
