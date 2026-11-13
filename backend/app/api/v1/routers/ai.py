"""AI 指导路由 —— 连接实训引擎 + 真实多模态视觉理解"""
import base64
import json
import logging
import time
from typing import Optional

import httpx
from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, Form
from sqlalchemy.orm import Session
from starlette.concurrency import run_in_threadpool

from app.api.deps import get_current_user
from app.db.session import get_db
from app.models import User, Experiment, ExperimentStep
from app.schemas import (
    AIGuideRequest, AIGuideResponse,
    VerifyRequest, VerifyResponse,
    DiagnoseResponse,
)
from app.engines.guide.dynamic_guide import DynamicGuideEngine
from app.engines.diagnosis.diagnoser import ErrorDiagnoser
from app.engines.verifier.result_verifier import ResultVerifier
from app.engines.visual.provider import analyze_screenshot, get_visual_provider
from app.engines.visual.schemas import VisualUnderstanding
from app.knowledge.software_tutorials import match_tutorial, match_step_target

logger = logging.getLogger(__name__)
router = APIRouter()


# ============ 视觉分析端点（桌面助手直接调用） ============
@router.post("/analyze-screen")
async def analyze_screen(
    file: UploadFile = File(..., description="屏幕截图 PNG/JPG"),
    software_hint: str = Form("", description="提示软件名称，提高识别准确率"),
    current_step: int = Form(0, description="当前实验步骤索引"),
    current_step_title: str = Form("", description="当前步骤标题，辅助模型理解意图"),
):
    """上传屏幕截图 → 多模态视觉理解 → 返回结构化界面信息

    成功时返回 VisualUnderstanding（software / window_title / elements[] / confidence）
    API 未配置或分析失败时返回 {available: false}。
    """
    provider = get_visual_provider()
    if not provider.is_available():
        return {"available": False, "reason": "AI_API_BASE_URL / AI_API_KEY / AI_VISION_MODEL 未配置"}

    # 读取文件并转 base64
    try:
        raw = await file.read()
        b64 = base64.b64encode(raw).decode("ascii")
    except Exception as e:
        raise HTTPException(400, f"图片读取失败: {e}")

    result = await run_in_threadpool(analyze_screenshot, b64, software_hint=software_hint)
    if result is None:
        return {"available": True, "analysis": None, "message": "视觉模型返回为空或解析失败"}

    return {
        "available": True,
        "analysis": result.model_dump(),
    }


# ============ 通用屏幕指导（无实验环境，基于真实桌面） ============
def _pick_primary_target(elements: list[dict]) -> Optional[dict]:
    """从识别到的控件中挑出最该提示用户操作的那个"""
    if not elements:
        return None
    # UIA 只抓到零星几个控件时，按面积/类型猜出来的一定是标题栏按钮之类，
    # 宁可不出框，也不要框错位置
    if len(elements) < 5 and all(el.get("source") == "uia" for el in elements):
        return None
    generic = {"close", "minimize", "maximize", "关闭", "最小化", "最大化", "×", "x"}
    best = None
    best_score = -999.0
    for el in elements:
        name = (el.get("name") or "").strip()
        ctype = (el.get("control_type") or "").lower()
        try:
            w = max(int(el.get("width", 0)), 1)
            h = max(int(el.get("height", 0)), 1)
        except (TypeError, ValueError):
            w, h = 1, 1
        score = min(w * h / 20000.0, 3.0)          # 面积越大越显眼
        if "edit" in ctype or "input" in ctype:
            score += 3.5                            # 输入框优先（用户最常操作）
        if "button" in ctype:
            score += 2.0
        if "tab" in ctype or "menuitem" in ctype:
            score += 0.5
        if not name:
            score -= 1.0
        if name.lower() in generic:
            score -= 4.0                            # 排除关闭/最小化等窗口按钮
        score += float(el.get("confidence", 0.5))
        if score > best_score:
            best_score, best = score, el
    return best


def _build_screen_instruction(software, window_title, state, el) -> str:
    """基于真实识别结果拼装一句可执行的建议"""
    facts = []
    if software:
        facts.append(f"当前软件：{software}")
    if window_title:
        facts.append(f"窗口：{window_title}")
    if state:
        facts.append(state)
    head = "；".join(facts) if facts else "已识别当前桌面"
    if not el:
        return f"{head}。\n\n未识别到明确的可操作控件，请打开需要操作的窗口后重试。"
    ctype = (el.get("control_type") or "").lower()
    verb = "输入内容" if ("edit" in ctype or "input" in ctype) else "点击"
    label = el.get("name") or "主要控件"
    return (
        f"{head}。\n\n"
        f"👉 建议下一步：{verb}「{label}」。\n"
        f"已用绿框标出它的位置，可以直接操作试试。"
    )


def _build_tutorial_instruction(tutorial: dict, step_index: int, step: dict) -> str:
    """把教程步骤渲染成指导文字"""
    steps = tutorial["steps"]
    lines = [
        f"📘 {tutorial['display_name']} · 使用教程",
        f"{tutorial['intro']}",
        "",
        f"第 {step_index + 1}/{len(steps)} 步：{step['title']}",
        f"{step['detail']}",
        "",
        "—— 完整步骤 ——",
    ]
    for i, s in enumerate(steps):
        mark = "▶" if i == step_index else "·"
        lines.append(f"{mark} {i + 1}. {s['title']}")
    return "\n".join(lines)


def _normalize_elements(raw_list: list, source: str, dx: int = 0, dy: int = 0) -> list[dict]:
    """把桌面端 UIA / 视觉模型返回的控件统一成内部格式（屏幕坐标）"""
    out: list[dict] = []
    for el in raw_list or []:
        try:
            name = str(el.get("name") or "").strip()
            if not name:
                continue
            x = int(float(el.get("x", 0))) + dx
            y = int(float(el.get("y", 0))) + dy
            width = int(float(el.get("width", 0)))
            height = int(float(el.get("height", 0)))
            if width <= 0 or height <= 0:
                continue
            out.append({
                "name": name,
                "control_type": str(el.get("control_type") or "Custom"),
                "x": x, "y": y, "width": width, "height": height,
                "confidence": float(el.get("confidence", 1.0)),
                "source": source,
            })
        except (TypeError, ValueError):
            continue
    return out


@router.post("/screen-guide")
async def screen_guide(
    file: UploadFile = File(..., description="屏幕截图 PNG/JPG"),
    software_hint: str = Form("", description="窗口标题/软件名提示"),
    step_index: int = Form(0, description="教程步骤索引（桌面端翻页时传入）"),
    region_left: int = Form(0, description="截图左上角在屏幕上的 X（窗口截图时）"),
    region_top: int = Form(0, description="截图左上角在屏幕上的 Y"),
    image_width: int = Form(0, description="截图宽度（像素）"),
    image_height: int = Form(0, description="截图高度（像素）"),
    uia_elements: str = Form("", description="桌面端 UIA 抓到的精确控件（JSON 数组）"),
    force_vision: bool = Form(False, description="用户手动刷新时才允许调用视觉模型"),
):
    """通用屏幕指导：识别真实桌面软件 → 匹配该软件的教程 → 标注当前步骤目标

    精度策略（从高到低）：
    1. 桌面端 UIA 控件坐标（精确到像素，无需视觉模型）
    2. 视觉模型识别结果（坐标已按窗口偏移换算到屏幕坐标）
    不依赖实验步骤，适用于没有实训环境的自由操作场景。
    """
    # ---- UIA 控件（桌面端已抓到精确矩形）----
    uia_list: list[dict] = []
    if uia_elements:
        try:
            uia_list = _normalize_elements(json.loads(uia_elements), "uia")
        except (json.JSONDecodeError, TypeError, ValueError):
            uia_list = []

    tutorial = match_tutorial(software_hint)

    # ---- 快路径：有 UIA 控件且教程步骤命中 → 直接返回，无需等待视觉模型 ----
    if tutorial and uia_list:
        steps = tutorial["steps"]
        resolved_index = max(0, min(step_index, len(steps) - 1))
        step = steps[resolved_index]
        target_el = match_step_target(uia_list, step, require_keyword=True)
        if target_el:
            return {
                "available": True,
                "software": tutorial["display_name"],
                "window_title": "",
                "tutorial": tutorial,
                "step_index": resolved_index,
                "instruction": _build_tutorial_instruction(tutorial, resolved_index, step),
                "target": target_el,
                "target_source": "uia",
                "elements": uia_list,
                "elapsed_ms": 0,
                "vision_used": False,
            }
        # 教程命中但当前界面找不到该步骤的控件：只给文字，不画框；
        # 视觉模型只在用户手动刷新（force_vision）时才调用
        if not force_vision:
            return {
                "available": True,
                "software": tutorial["display_name"],
                "window_title": "",
                "tutorial": tutorial,
                "step_index": resolved_index,
                "instruction": _build_tutorial_instruction(tutorial, resolved_index, step),
                "target": None,
                "target_source": None,
                "elements": uia_list,
                "elapsed_ms": 0,
                "vision_used": False,
                "note": "当前界面未找到该步骤对应的控件，未标注位置",
            }

    # ---- 未收录教程但有 UIA 控件：直接给通用提示，不调用慢速视觉模型 ----
    if not tutorial and uia_list and not force_vision:
        return {
            "available": True,
            "software": "",
            "window_title": "",
            "tutorial": None,
            "step_index": 0,
            "instruction": (
                f"已识别窗口：{software_hint}\n"
                "尚未收录该软件的教程，因此不做位置标注。\n"
                "可点击「立即刷新」让视觉模型尝试识别界面。"
            ),
            "target": None,
            "target_source": None,
            "elements": uia_list,
            "elapsed_ms": 0,
            "vision_used": False,
        }

    provider = get_visual_provider()
    if not provider.is_available():
        if tutorial:
            steps = tutorial["steps"]
            resolved_index = max(0, min(step_index, len(steps) - 1))
            step = steps[resolved_index]
            return {
                "available": True,
                "software": tutorial["display_name"],
                "window_title": software_hint,
                "tutorial": tutorial,
                "step_index": resolved_index,
                "instruction": _build_tutorial_instruction(tutorial, resolved_index, step),
                "target": match_step_target(uia_list, step, require_keyword=True),
                "target_source": "uia" if uia_list else None,
                "elements": uia_list,
                "elapsed_ms": 0,
                "vision_used": False,
                "note": "视觉模型未配置，按窗口标题匹配教程",
            }
        return {"available": False, "reason": "视觉模型未配置（AI_API_KEY / AI_VISION_MODEL）"}

    try:
        raw = await file.read()
        b64 = base64.b64encode(raw).decode("ascii")
    except Exception as e:
        raise HTTPException(400, f"图片读取失败: {e}")

    t0 = time.time()
    result = await run_in_threadpool(
        analyze_screenshot, b64,
        software_hint=software_hint,
        image_width=image_width,
        image_height=image_height,
    )
    elapsed = int((time.time() - t0) * 1000)

    if result is None:
        # 视觉暂不可用 → 仍可按窗口标题/进程名匹配出教程
        if tutorial:
            steps = tutorial["steps"]
            resolved_index = max(0, min(step_index, len(steps) - 1))
            step = steps[resolved_index]
            return {
                "available": True,
                "software": tutorial["display_name"],
                "tutorial": tutorial,
                "step_index": resolved_index,
                "instruction": _build_tutorial_instruction(tutorial, resolved_index, step),
                "target": match_step_target(uia_list, step, require_keyword=True),
                "target_source": "uia" if uia_list else None,
                "elements": uia_list,
                "elapsed_ms": elapsed,
                "vision_used": False,
                "note": "视觉模型暂不可用，已按窗口/进程匹配教程",
            }
        return {
            "available": True,
            "instruction": "视觉模型暂时没有返回结果，请稍后重试。",
            "target": None,
            "elements": uia_list,
            "elapsed_ms": elapsed,
            "vision_used": False,
        }

    # 视觉坐标以「截图左上角」为原点 → 加上窗口在屏幕上的偏移
    vision_elements = _normalize_elements(
        [e.model_dump() for e in result.elements], "vision",
        dx=region_left, dy=region_top,
    )

    # 教程匹配：视觉识别到的软件名优先级更高
    tutorial = match_tutorial(result.software, result.window_title, software_hint) or tutorial

    target_el = None
    target_source = None
    resolved_index = 0
    if tutorial:
        steps = tutorial["steps"]
        resolved_index = max(0, min(step_index, len(steps) - 1))
        step = steps[resolved_index]
        instruction = _build_tutorial_instruction(tutorial, resolved_index, step)
        # UIA 精确坐标优先；视觉结果兜底
        target_el = match_step_target(uia_list, step, require_keyword=True)
        if target_el:
            target_source = "uia"
        else:
            target_el = match_step_target(vision_elements, step)
            target_source = "vision" if target_el else None
        if not target_el:
            target_el = _pick_primary_target(uia_list + vision_elements)
            target_source = "heuristic" if target_el else None
    else:
        target_el = _pick_primary_target(uia_list + vision_elements)
        target_source = "heuristic" if target_el else None
        instruction = _build_screen_instruction(
            result.software, result.window_title, result.current_state, target_el
        )

    return {
        "available": True,
        "software": result.software or (tutorial["display_name"] if tutorial else ""),
        "window_title": result.window_title,
        "current_state": result.current_state,
        "confidence": result.confidence,
        "tutorial": tutorial,
        "step_index": resolved_index,
        "instruction": instruction,
        "target": target_el,
        "target_source": target_source,
        "elements": uia_list or vision_elements,
        "vision_elements": vision_elements,
        "elapsed_ms": elapsed,
        "vision_used": True,
    }


# ============ 核心指导端点（有截图就先跑视觉理解） ============
@router.post("/guide", response_model=AIGuideResponse)
def request_guide(
    req: AIGuideRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """请求 AI 指导（核心接口）

    流程：
    1. 如果 screen_state 中包含 image_base64 → 先调多模态 API 做视觉理解
    2. DynamicGuideEngine 结合视觉理解结果 + 适配器 + 步骤，生成精准指导
    3. 没截图 → 走原 Stub 流程（适配器填 target）
    """
    exp = db.query(Experiment).filter(Experiment.id == req.experiment_id).first()
    if not exp:
        raise HTTPException(404, "实验不存在")
    steps = db.query(ExperimentStep).filter(
        ExperimentStep.experiment_id == req.experiment_id
    ).order_by(ExperimentStep.order_index).all()

    # ---- 尝试视觉理解 ----
    visual_result: Optional[VisualUnderstanding] = None
    image_b64 = None
    software_hint = exp.software or exp.type or ""
    if req.screen_state:
        image_b64 = (
            req.screen_state.get("image_base64")
            or req.screen_state.get("screenshot_base64")
            or req.screen_state.get("image")
        )
    if image_b64:
        try:
            visual_result = analyze_screenshot(image_b64, software_hint=software_hint)
            if visual_result:
                logger.info(
                    "视觉理解成功: software=%s, elements=%d, confidence=%.2f",
                    visual_result.software, len(visual_result.elements), visual_result.confidence,
                )
        except Exception as e:
            logger.warning("视觉理解异常（将 fallback）: %s", e)

    engine = DynamicGuideEngine()
    guide = engine.generate_guide(
        experiment=exp,
        steps=steps,
        current_step_index=req.current_step,
        user_state={
            "user_id": current_user.id,
            "context": req.context,
            "screen_state": req.screen_state,
            # 把视觉理解结果传进去，引擎可以用真实坐标替换 Stub
            "visual_understanding": visual_result.model_dump() if visual_result else None,
        },
    )
    return guide


# ============ 结果验证 ============
@router.post("/verify/{exp_id}/{step_id}", response_model=VerifyResponse)
def verify_result(
    exp_id: int,
    step_id: int,
    req: VerifyRequest,
    db: Session = Depends(get_db),
):
    step = db.query(ExperimentStep).filter(
        ExperimentStep.id == step_id,
        ExperimentStep.experiment_id == exp_id,
    ).first()
    if not step:
        raise HTTPException(404, "步骤不存在")
    verifier = ResultVerifier(db)
    return verifier.verify(step, req.actual_result)


# ============ 错误诊断 ============
@router.post("/diagnose/{exp_id}", response_model=DiagnoseResponse)
def diagnose_error(
    exp_id: int,
    req: dict,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    exp = db.query(Experiment).filter(Experiment.id == exp_id).first()
    if not exp:
        raise HTTPException(404, "实验不存在")

    step = None
    step_id = req.get("step_id")
    if isinstance(step_id, int):
        step = db.query(ExperimentStep).filter(
            ExperimentStep.id == step_id,
            ExperimentStep.experiment_id == exp_id,
        ).first()

    error_text = str(
        req.get("error") or req.get("error_message") or req.get("message") or ""
    ).strip()

    diagnosed = ErrorDiagnoser().diagnose(
        experiment_title=exp.title,
        step_title=step.title if step else "",
        instruction=step.instruction if step else "",
        expected_result=step.expected_result if step else "",
        common_errors=step.common_errors if step else None,
        error_text=error_text,
        context=req.get("context"),
    )
    if diagnosed is not None:
        return diagnosed

    # 模型不可用 / 调用失败：回退到步骤自身的常见错误与预期结果
    causes: list[str] = []
    if step and isinstance(step.common_errors, list):
        causes = [str(item) for item in step.common_errors[:3]]
    suggestion = "请对照当前步骤的预期结果，检查操作是否真的完成。"
    if step and step.expected_result:
        suggestion = f"请检查是否达到这一步的预期结果：{step.expected_result}"
    return DiagnoseResponse(
        error_type="操作错误",
        suggestion=suggestion,
        possible_causes=causes or ["目标控件不在当前视图", "软件版本差异", "权限不足"],
    )
