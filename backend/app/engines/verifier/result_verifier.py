"""结果验证器：对接软件适配器的 validate_result()

判定顺序：
1. 根据步骤 / 实验信息选择适配器（python、mysql）；
2. 适配器明确返回 passed / failed；
3. 无适配器时，回退到 actual_result 中的显式 passed / failed 信号；
4. 都没有明确信号时返回“不确定”，不把未知当成失败。
"""
import logging

from sqlalchemy.orm import Session

from app.adapters.registry import get_adapter
from app.models import ExperimentStep
from app.schemas import VerifyResponse

logger = logging.getLogger(__name__)

# 实验类型 -> 适配器 key。仅映射已实现的适配器，其余类型走通用回退。
_ADAPTER_BY_EXPERIMENT_TYPE = {
    "python": "python",
    "database": "mysql",
    "mysql": "mysql",
}


class ResultVerifier:
    def __init__(self, db: Session):
        self.db = db

    def _adapter_key(self, step: ExperimentStep) -> str | None:
        hint = step.adapter_hint or {}
        if isinstance(hint, dict):
            # 显式声明优先；兼容字符串与 {"software": "..."} 两种写法
            for field in ("adapter_key", "software_key", "software", "adapter"):
                value = hint.get(field)
                if isinstance(value, str) and value.strip():
                    return value.strip().lower()
                if isinstance(value, dict):
                    for nested in ("software", "software_key", "adapter"):
                        nested_value = value.get(nested)
                        if isinstance(nested_value, str) and nested_value.strip():
                            return nested_value.strip().lower()

        experiment = getattr(step, "experiment", None)
        exp_type = (getattr(experiment, "type", "") or "").lower()
        return _ADAPTER_BY_EXPERIMENT_TYPE.get(exp_type)

    def verify(self, step: ExperimentStep, actual_result: dict | None) -> VerifyResponse:
        if not isinstance(actual_result, dict) or not actual_result:
            return VerifyResponse(
                passed=False,
                feedback="尚未检测到实际操作结果。请先完成操作，再刷新屏幕识别。",
                confidence=0.3,
            )

        adapter_key = self._adapter_key(step)
        adapter = get_adapter(adapter_key) if adapter_key else None
        if adapter is not None:
            try:
                outcome = adapter.validate_result(step, actual_result) or {}
                passed = bool(outcome.get("passed"))
                feedback = str(outcome.get("feedback") or "").strip()
                if not feedback:
                    feedback = "操作成功！可以继续下一步。" if passed else "操作未完成，请检查后重试。"
                confidence = outcome.get("confidence", 0.8 if passed else 0.6)
                confidence = float(confidence)
                return VerifyResponse(
                    passed=passed,
                    feedback=feedback,
                    confidence=min(max(confidence, 0.0), 1.0),
                )
            except Exception:
                # 适配器异常不应让接口 500，也不应把未知结果当成失败依据
                logger.exception("适配器校验异常: %s", adapter_key)
                return VerifyResponse(
                    passed=False,
                    feedback="暂时无法确认操作结果，请刷新屏幕识别后重试。",
                    confidence=0.2,
                )

        # 无适配器：只信任显式信号
        if isinstance(actual_result.get("passed"), bool):
            passed = actual_result["passed"]
            return VerifyResponse(
                passed=passed,
                feedback=actual_result.get("feedback") or (
                    "操作成功！可以继续下一步。" if passed else "操作未完成，请检查后重试。"
                ),
                confidence=0.9,
            )
        if actual_result.get("failed") is True:
            return VerifyResponse(
                passed=False,
                feedback=actual_result.get("feedback") or "检测到操作未完成。请按指导重试。",
                confidence=0.7,
            )

        return VerifyResponse(
            passed=False,
            feedback="暂未检测到明确的成功信号。请确认操作是否真的完成了，或尝试刷新屏幕识别。",
            confidence=0.4,
        )
