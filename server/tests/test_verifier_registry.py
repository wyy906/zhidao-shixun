"""验证器白名单注册机制测试：白名单不可被实验 JSON 扩展或绕过；fail-closed；三态行为。"""

import sys
from pathlib import Path

import pytest
from zhidao_contracts import VerifyOutcome

from app.experiments.verifiers.registry import (
    VERIFIER_REGISTRY,
    VerifierImplementation,
    evaluate_verifier,
    get_spec,
    validate_verifier_def,
)

sys.path.insert(0, str(Path(__file__).resolve().parent))
from helpers_experiment import deep_copy, make_valid_experiment  # noqa: E402


def test_registry_is_fixed_whitelist() -> None:
    assert set(VERIFIER_REGISTRY) == {
        "python_exit_code_zero",
        "python_stdout_contains",
        "mysql_query_result",
        "mysql_table_state",
    }
    # registry 是普通模块级映射，实验 JSON 只能引用其中的字符串，无法注入实现
    assert VERIFIER_REGISTRY["python_exit_code_zero"].implementation is VerifierImplementation.IMPLEMENTED
    assert VERIFIER_REGISTRY["mysql_query_result"].implementation is VerifierImplementation.RESERVED


def test_unknown_type_is_not_evaluatable_fail_closed() -> None:
    assert get_spec("not_a_verifier") is None
    result = evaluate_verifier("not_a_verifier", {}, {"stdout": "x"}, step_id="s1")
    assert result.outcome is VerifyOutcome.UNCERTAIN
    assert "未注册" in result.feedback


def test_exit_code_zero_three_states() -> None:
    passed = evaluate_verifier("python_exit_code_zero", {}, {"exit_code": 0}, step_id="s")
    failed = evaluate_verifier("python_exit_code_zero", {}, {"exit_code": 2}, step_id="s")
    uncertain = evaluate_verifier("python_exit_code_zero", {}, {}, step_id="s")
    not_int = evaluate_verifier("python_exit_code_zero", {}, {"exit_code": "0"}, step_id="s")
    assert (passed.outcome, failed.outcome, uncertain.outcome, not_int.outcome) == (
        VerifyOutcome.PASSED,
        VerifyOutcome.FAILED,
        VerifyOutcome.UNCERTAIN,
        VerifyOutcome.UNCERTAIN,
    )


def test_stdout_contains_case_handling() -> None:
    passed = evaluate_verifier(
        "python_stdout_contains", {"text": "HELLO"}, {"stdout": "say hello world"}, step_id="s"
    )
    strict_failed = evaluate_verifier(
        "python_stdout_contains", {"text": "HELLO", "case_sensitive": True}, {"stdout": "hello"}, step_id="s"
    )
    assert passed.outcome is VerifyOutcome.PASSED
    assert strict_failed.outcome is VerifyOutcome.FAILED


def test_reserved_verifier_evaluates_to_uncertain() -> None:
    result = evaluate_verifier(
        "mysql_query_result", {"query_description": "x", "expect": "y"}, {"rows": [["1"]]}, step_id="s"
    )
    assert result.outcome is VerifyOutcome.UNCERTAIN
    assert "尚未实现" in result.feedback


def test_reserved_verifier_with_valid_params_passes_load_validation() -> None:
    errors = validate_verifier_def(
        "mysql_query_result", {"query_description": "查询用户表", "expect": "至少 1 行"}, environment="mysql_workbench"
    )
    assert errors == []


def test_param_validation_rejects_unknown_and_bad_values() -> None:
    assert validate_verifier_def("python_stdout_contains", {"text": ""}, environment="python_web") != []
    assert validate_verifier_def("python_stdout_contains", {"evil": 1}, environment="python_web") != []
    assert validate_verifier_def("python_exit_code_zero", {"unexpected": 1}, environment="python_web") != []
    assert validate_verifier_def("python_stdout_contains", {"text": "x", "case_sensitive": "yes"}, environment="python_web") != []
    assert validate_verifier_def("python_stdout_contains", {"text": "x"}, environment="python_web") == []


def test_type_mismatch_between_verifier_and_environment() -> None:
    errors = validate_verifier_def("python_exit_code_zero", {}, environment="mysql_workbench")
    assert any("不支持环境 mysql_workbench" in e for e in errors)


def test_evaluator_exception_becomes_uncertain(monkeypatch) -> None:
    import dataclasses

    spec = get_spec("python_stdout_contains")
    assert spec is not None

    def boom(params, actual):  # noqa: ANN001
        raise RuntimeError("boom")

    broken_spec = dataclasses.replace(spec, evaluate=boom)
    monkeypatch.setitem(VERIFIER_REGISTRY, "python_stdout_contains", broken_spec)
    result = evaluate_verifier("python_stdout_contains", {"text": "x"}, {"stdout": "x"}, step_id="s")
    assert result.outcome is VerifyOutcome.UNCERTAIN
    assert "求值异常" in result.feedback


def test_experiment_json_cannot_inject_new_verifier_type() -> None:
    """实验文件声称实现了新验证器类型也无济于事：加载即拒绝，求值 fail-closed。"""
    data = deep_copy(make_valid_experiment())
    data["steps"][0]["verifier"] = {"type": "os_command", "params": {"cmd": "rm -rf /"}}
    # Schema 枚举拦截 + registry 白名单拦截（双层）
    from app.experiments.errors import ExperimentValidationError
    from app.experiments.loader import load_experiment_dict

    with pytest.raises(ExperimentValidationError):
        load_experiment_dict(data)
