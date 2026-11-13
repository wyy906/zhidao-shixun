"""结果验证器：适配器接入与回退行为"""
from types import SimpleNamespace

from app.engines.verifier.result_verifier import ResultVerifier


def _step(exp_type: str = "python", hint: dict | None = None):
    experiment = SimpleNamespace(type=exp_type, title="测试实验")
    return SimpleNamespace(
        adapter_hint=hint,
        experiment=experiment,
        title="测试步骤",
        instruction="完成操作",
        expected_result="操作成功",
        common_errors=[],
    )


def test_python_adapter_accepts_non_empty_output():
    result = ResultVerifier(db=None).verify(_step(), {"code_output": "45"})
    assert result.passed is True
    assert result.confidence >= 0.5


def test_python_adapter_treats_empty_output_as_failure():
    result = ResultVerifier(db=None).verify(_step(), {"code_output": "   "})
    assert result.passed is False


def test_adapter_honours_explicit_passed_signal():
    """桌面端 UIA/视觉给出 passed 时，不应因缺少 code_output 被判失败"""
    result = ResultVerifier(db=None).verify(_step(), {"passed": True})
    assert result.passed is True
    assert result.confidence >= 0.8


def test_database_type_maps_to_mysql_adapter():
    result = ResultVerifier(db=None).verify(
        _step("database"), {"query_success": True}
    )
    assert result.passed is True


def test_adapter_hint_overrides_experiment_type():
    # 实验类型是 python，但步骤显式声明 mysql
    result = ResultVerifier(db=None).verify(
        _step("python", {"adapter": "mysql"}), {"grid_rows": 3}
    )
    assert result.passed is True


def test_explicit_signal_without_adapter_is_trusted():
    result = ResultVerifier(db=None).verify(_step("excel"), {"passed": True})
    assert result.passed is True
    assert result.confidence >= 0.8


def test_unknown_result_stays_uncertain():
    result = ResultVerifier(db=None).verify(_step("excel"), {"some": "value"})
    assert result.passed is False
    assert result.confidence <= 0.4


def test_missing_result_is_not_treated_as_success():
    result = ResultVerifier(db=None).verify(_step(), None)
    assert result.passed is False
    assert result.confidence <= 0.3


def test_adapter_exception_returns_uncertain(monkeypatch):
    class Boom:
        def validate_result(self, step, actual_result):
            raise RuntimeError("adapter failed")

    monkeypatch.setattr(
        "app.engines.verifier.result_verifier.get_adapter", lambda key: Boom()
    )
    result = ResultVerifier(db=None).verify(_step(), {"passed": True})
    assert result.passed is False
    assert result.confidence <= 0.2
    assert "无法确认" in result.feedback
