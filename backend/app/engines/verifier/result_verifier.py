"""结果验证器（首期 Stub）"""
from sqlalchemy.orm import Session

from app.models import ExperimentStep
from app.schemas import VerifyResponse


class ResultVerifier:
    def __init__(self, db: Session):
        self.db = db

    def verify(self, step: ExperimentStep, actual_result: dict | None) -> VerifyResponse:
        """
        首期 Stub：
        - 若 actual_result 包含 passed=True，返回通过
        - 否则返回不确定，但鼓励继续
        实际应：对接适配器的 validate_result()，或比对 expected_result
        """
        if actual_result and actual_result.get("passed"):
            return VerifyResponse(
                passed=True,
                feedback="操作成功！可以继续下一步。",
                confidence=0.95,
            )
        if actual_result and actual_result.get("failed"):
            return VerifyResponse(
                passed=False,
                feedback="检测到操作未完成。AI 正在重新识别屏幕并调整指导。",
                confidence=0.7,
            )
        # 不确定——不做错误判断
        return VerifyResponse(
            passed=False,
            feedback="暂未检测到明确的成功信号。请确认操作是否真的完成了，或尝试刷新屏幕识别。",
            confidence=0.4,
        )
