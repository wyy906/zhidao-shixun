"""AI 错误诊断（OpenAI 兼容文本接口）

设计原则：
1. 复用现有 AI_API_BASE_URL / AI_API_KEY / AI_VISION_MODEL 配置；
2. 未配置、超时、HTTP 错误、解析失败 → 返回 None，由路由回退到静态建议；
3. 只记录状态码与异常类型，不记录 API Key、学生代码或报错原文；
4. 发送给模型前对学生报错/上下文做常见密钥格式脱敏。
"""
from __future__ import annotations

import json
import logging
import re
from typing import Optional

import httpx

from app.core.config import settings
from app.schemas import DiagnoseResponse

logger = logging.getLogger(__name__)

DIAGNOSE_SYSTEM_PROMPT = """你是智导实训平台的故障诊断助教。
请根据实验步骤要求和学生遇到的报错，用中文给出可执行的下一步建议。
只输出严格 JSON，不要输出 markdown 或代码块标记：
{"error_type": "错误类型", "suggestion": "一条具体、可操作的修复建议", "possible_causes": ["原因1", "原因2"]}
不要臆造界面中不存在的按钮或菜单；不确定时给出排查方向而不是虚构事实。"""

DIAGNOSE_USER_PROMPT = """实验：{experiment_title}
当前步骤：{step_title}
步骤要求：{instruction}
预期结果：{expected_result}
常见错误：{common_errors}
学生报错或描述：{error_text}
补充上下文：{context}"""

# 常见密钥格式，避免学生把密钥粘进报错后被写入日志或直接转发
_SECRET_PATTERNS = (
    re.compile(r"nvapi-[A-Za-z0-9_\-]{8,}"),
    re.compile(r"sk-[A-Za-z0-9_\-]{12,}"),
    re.compile(r"AKIA[0-9A-Z]{16}"),
    re.compile(r"(?i)(api[_-]?key|access[_-]?token|authorization)\s*[:=]\s*['\"]?[A-Za-z0-9_\-]{8,}"),
)


def redact_secrets(text: str) -> str:
    """把文本中的常见密钥替换为 [REDACTED]。"""
    if not text:
        return ""
    result = str(text)
    for pattern in _SECRET_PATTERNS:
        result = pattern.sub("[REDACTED]", result)
    return result


def _clip(value: object, limit: int) -> str:
    text = "" if value is None else str(value)
    return text if len(text) <= limit else text[:limit] + "…"


def _strip_code_fence(raw: str) -> str:
    text = raw.strip()
    if text.startswith("```"):
        text = text.strip("`")
        if text.startswith("json"):
            text = text[4:].strip()
    return text


class ErrorDiagnoser:
    """调用 OpenAI 兼容文本模型做错误诊断。"""

    def __init__(self, timeout: float = 30.0):
        self.base_url = (settings.ai_api_base_url or "").rstrip("/")
        self.api_key = settings.ai_api_key or ""
        self.model = settings.ai_vision_model or ""
        self.timeout = timeout

    def is_available(self) -> bool:
        return bool(self.base_url and self.api_key and self.model)

    def diagnose(
        self,
        *,
        experiment_title: str = "",
        step_title: str = "",
        instruction: str = "",
        expected_result: str = "",
        common_errors: object = None,
        error_text: str = "",
        context: object = None,
    ) -> Optional[DiagnoseResponse]:
        if not self.is_available():
            logger.debug("AI 诊断未配置，跳过模型调用")
            return None

        context_text = context if isinstance(context, str) else json.dumps(
            context or {}, ensure_ascii=False
        )
        user_prompt = DIAGNOSE_USER_PROMPT.format(
            experiment_title=_clip(experiment_title, 200),
            step_title=_clip(step_title, 200),
            instruction=_clip(instruction, 1200),
            expected_result=_clip(expected_result, 500),
            common_errors=_clip(json.dumps(common_errors or [], ensure_ascii=False), 800),
            error_text=_clip(redact_secrets(error_text), 2000),
            context=_clip(redact_secrets(context_text), 1500),
        )
        payload = {
            "model": self.model,
            "messages": [
                {"role": "system", "content": DIAGNOSE_SYSTEM_PROMPT},
                {"role": "user", "content": user_prompt},
            ],
            "response_format": {"type": "json_object"},
            "max_tokens": 800,
            "temperature": 0.2,
        }
        headers = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {self.api_key}",
        }

        try:
            with httpx.Client(timeout=self.timeout) as client:
                resp = client.post(
                    f"{self.base_url}/chat/completions",
                    json=payload,
                    headers=headers,
                )
                resp.raise_for_status()
                data = resp.json()
            raw = data["choices"][0]["message"]["content"]
            if not raw or not isinstance(raw, str):
                logger.warning("AI 诊断返回空内容")
                return None
            obj = json.loads(_strip_code_fence(raw))
            return self._to_response(obj)
        except httpx.TimeoutException:
            logger.warning("AI 诊断超时（%.0fs）", self.timeout)
        except httpx.HTTPStatusError as exc:
            logger.warning("AI 诊断 HTTP %s", exc.response.status_code)
        except httpx.HTTPError as exc:
            logger.warning("AI 诊断网络错误: %s", type(exc).__name__)
        except (json.JSONDecodeError, KeyError, TypeError, ValueError) as exc:
            logger.warning("AI 诊断响应解析失败: %s", type(exc).__name__)
        return None

    @staticmethod
    def _to_response(obj: object) -> Optional[DiagnoseResponse]:
        if not isinstance(obj, dict):
            return None
        suggestion = str(obj.get("suggestion") or "").strip()
        if not suggestion:
            return None
        error_type = str(obj.get("error_type") or "操作错误").strip()[:100]
        causes = obj.get("possible_causes")
        if not isinstance(causes, list):
            causes = []
        cleaned: list[str] = []
        for item in causes[:5]:
            text = str(item).strip()
            if text:
                cleaned.append(text[:200])
        return DiagnoseResponse(
            error_type=error_type or "操作错误",
            suggestion=suggestion[:1000],
            possible_causes=cleaned or None,
        )
