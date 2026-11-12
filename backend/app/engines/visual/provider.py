"""多模态视觉理解 Provider

对接任意 OpenAI-compatible 多模态 API（讯飞星火 / 通义千问 / DeepSeek-VL / 豆包 / MiniMax / 智谱 ...）。

设计原则：
1. Provider 是可插拔的——api_key 未配置时返回 None（调用方 fallback）
2. 模型返回严格 JSON，用 Pydantic 校验
3. 超时 / 网络错误 / 解析失败 → 静默返回 None（不阻塞主流程）
4. 图片自动压缩到合理尺寸（长边 ≤ 1280px），减少 token 和延迟
"""
from __future__ import annotations

import base64
import json
import logging
from typing import Optional
from abc import ABC, abstractmethod

import httpx

from app.core.config import settings
from app.engines.visual.schemas import VisualUnderstanding

logger = logging.getLogger(__name__)

# ========== Prompt 模板 ==========
# 中文 + 结构化 JSON 要求，让各种国产模型都能理解
VISUAL_SYSTEM_PROMPT = """你是一名专业的软件界面分析助手。
请严格按照要求输出 JSON，不要输出任何额外文字、markdown 或代码块标记。"""

VISUAL_USER_PROMPT = """请分析这张 {software} 软件的界面截图，返回严格 JSON：

{{
  "software": "软件名称",
  "window_title": "当前活动窗口标题",
  "elements": [
    {{
      "name": "控件上显示的文字或图标含义",
      "control_type": "Button|Edit|Text|MenuItem|TreeItem|Document|Tab|Dialog|ComboBox|CheckBox|Radio|Slider",
      "x": 整数, "y": 整数, "width": 整数, "height": 整数, "confidence": 0-1
    }}
  ],
  "current_state": "一句话描述当前界面处于什么状态",
  "confidence": 0-1
}}

这张截图是完整的单个软件窗口，尺寸为 {width} x {height} 像素。
坐标系：原点 (0,0) 是这张截图的左上角（不是屏幕左上角），x 向右增大，y 向下增大，单位像素。
每个控件的 x/y/width/height 必须紧贴它在截图中可见的实际边界，不得越出截图范围。
只列出与操作相关的控件（按钮、输入框、菜单、标签页），忽略纯装饰元素。
如果看不清或无法识别，给 confidence 较低值。"""


class BaseVisualProvider(ABC):
    """视觉理解 Provider 抽象基类"""

    @abstractmethod
    def is_available(self) -> bool:
        """配置就绪时返回 True"""

    @abstractmethod
    def analyze(
        self,
        image_base64: str,
        software_hint: str = "",
        image_width: int = 0,
        image_height: int = 0,
    ) -> Optional[VisualUnderstanding]:
        """分析一张截图。失败/不可用时返回 None。"""


class OpenAICompatibleProvider(BaseVisualProvider):
    """通用 OpenAI-compatible 多模态 API 实现

    兼容：OpenAI / 讯飞星火 / 通义千问 / DeepSeek-VL / 豆包 / MiniMax / 智谱 / Moonshot ...
    几乎所有国产大模型都提供此协议的 endpoint。

    配置项（.env）：
        AI_API_BASE_URL=https://api.siliconflow.cn/v1
        AI_API_KEY=sk-xxxx
        AI_VISION_MODEL=deepseek-ai/deepseek-vl2
    """

    def __init__(self):
        self.base_url = settings.ai_api_base_url.rstrip("/") if settings.ai_api_base_url else ""
        self.api_key = settings.ai_api_key
        self.model = settings.ai_vision_model
        self._client: httpx.Client | None = None

    def is_available(self) -> bool:
        return bool(self.base_url and self.api_key and self.model)

    def analyze(
        self,
        image_base64: str,
        software_hint: str = "",
        image_width: int = 0,
        image_height: int = 0,
    ) -> Optional[VisualUnderstanding]:
        if not self.is_available():
            logger.debug("视觉 API 未配置，跳过视觉理解")
            return None

        # --- 1. 图片预处理：不再缩放，保证模型返回的坐标与原始截图一一对应 ---
        pure_b64 = image_base64.replace("data:image/png;base64,", "") \
                               .replace("data:image/jpeg;base64,", "") \
                               .replace("data:image;base64,", "")

        image_url = f"data:image/jpeg;base64,{pure_b64}"

        # 未显式传入尺寸时，从图片头解析（提示词里给出尺寸能显著提升坐标精度）
        if not image_width or not image_height:
            image_width, image_height = _probe_image_size(pure_b64)

        url = f"{self.base_url}/chat/completions"
        payload = {
            "model": self.model,
            "messages": [
                {"role": "system", "content": VISUAL_SYSTEM_PROMPT},
                {
                    "role": "user",
                    "content": [
                        {
                            "type": "text",
                            "text": VISUAL_USER_PROMPT.format(
                                software=software_hint or "目标",
                                width=image_width or "未知",
                                height=image_height or "未知",
                            ),
                        },
                        {"type": "image_url", "image_url": {"url": image_url}},
                    ],
                },
            ],
            "response_format": {"type": "json_object"},
            # 推理模型（如 nemotron-3.5-super-vl）内部有 reasoning_content，
            # 需要更多 token 才能在思考完后输出真正的 JSON
            "max_tokens": 8192,
            "temperature": 0.1,
        }
        headers = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {self.api_key}",
        }

        # --- 2. 带重试的 API 调用（最多 2 次）---
        for attempt in range(2):
            try:
                client = self._get_client()
                resp = client.post(url, json=payload, headers=headers)
                resp.raise_for_status()
                data = resp.json()
                raw = data["choices"][0]["message"]["content"]
                # NVIDIA 某些响应 content 为 None（比如 finish_reason=length）
                if not raw or not isinstance(raw, str):
                    msg = data["choices"][0].get("message", {})
                    if msg.get("refusal"):
                        logger.warning("视觉 API 返回 refusal: %s", msg["refusal"][:200])
                    else:
                        logger.warning("视觉 API content 为空 (finish_reason=%s)",
                                       data["choices"][0].get("finish_reason"))
                    return None
                # 有些模型会用 ```json 包裹
                raw = raw.strip()
                if raw.startswith("```"):
                    raw = raw.strip("`")
                    if raw.startswith("json"):
                        raw = raw[4:].strip()
                obj = json.loads(raw)
                return VisualUnderstanding.model_validate(obj)
            except httpx.TimeoutException:
                if attempt == 0:
                    logger.warning("视觉 API 超时，重试中（1/2）...")
                    continue
                logger.warning("视觉 API 重试仍超时")
            except httpx.HTTPStatusError as e:
                code = e.response.status_code
                logger.warning("视觉 API HTTP %s: %s", code, e.response.text[:200])
                # 5xx / 429 是临时性故障，重试一次
                if code in (429, 500, 502, 503, 504) and attempt == 0:
                    logger.warning("视觉 API 临时性错误，重试中（1/2）...")
                    continue
                return None
            except httpx.HTTPError as e:
                if attempt == 0:
                    logger.warning("视觉 API 网络错误，重试中: %s", e)
                    continue
                logger.warning("视觉 API 重试仍失败: %s", e)
            except (json.JSONDecodeError, KeyError, TypeError, ValueError) as e:
                logger.warning("视觉 API 响应解析失败: %s", e)
                return None  # 解析错误不重试
        return None

    def _get_client(self) -> httpx.Client:
        if self._client is None:
            # NVIDIA 推理模型 + 8192 tokens 单次调用可能 60-120s，给足 180s
            self._client = httpx.Client(timeout=180.0)
        return self._client


# ========== 全局单例 ==========
_provider: Optional[BaseVisualProvider] = None


def get_visual_provider() -> BaseVisualProvider:
    """获取 Provider 单例"""
    global _provider
    if _provider is None:
        _provider = OpenAICompatibleProvider()
    return _provider


def analyze_screenshot(
    image_base64: str,
    software_hint: str = "",
    image_width: int = 0,
    image_height: int = 0,
) -> Optional[VisualUnderstanding]:
    """便捷函数：分析一张截图，失败返回 None（不阻塞）"""
    provider = get_visual_provider()
    if not provider.is_available():
        return None
    return provider.analyze(
        image_base64, software_hint, image_width=image_width, image_height=image_height,
    )


def _probe_image_size(image_b64: str) -> tuple[int, int]:
    """从 base64 图片头解析宽高，解析失败返回 (0, 0)"""
    try:
        import io

        from PIL import Image

        raw = base64.b64decode(image_b64)
        with Image.open(io.BytesIO(raw)) as img:
            return img.width, img.height
    except Exception:
        return 0, 0
