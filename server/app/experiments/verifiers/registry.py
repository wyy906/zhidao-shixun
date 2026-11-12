"""验证器白名单注册机制。

安全边界（AI_COLLABORATION.md §7 V2-03 第 3 条）：
- 本模块是验证器类型的唯一事实来源；实验 JSON 只能引用这里的类型并提供受约束参数。
- 禁止 eval / exec / 任意 import / 任意函数名调用 / shell 拼接 / 动态模块路径——
  registry 只映射到本文件内定义的受控实现，实验文件无法扩展或绕过。
- fail-closed：未知类型返回 None 并在求值时输出 uncertain；reserved（已声明未实现）类型
  可被加载用于结构表达，但求值必须拒绝并返回 uncertain，绝不伪装成验证通过。
- 求值结果遵循跨端三态：passed / failed / uncertain；不确定不得推进步骤。
"""

from collections.abc import Callable, Mapping
from dataclasses import dataclass
from enum import Enum
from types import MappingProxyType
from typing import Any

from zhidao_contracts import VerifyOutcome, VerifyResult


class VerifierImplementation(Enum):
    """实现状态。"""

    IMPLEMENTED = "implemented"  # 已实现：可对传入的 actual 结果求值
    RESERVED = "reserved"        # 预留：结构可表达，加载允许；执行必须 fail-closed


@dataclass(frozen=True)
class VerifyEvaluation:
    """单次求值输出（由受控实现返回）。"""

    outcome: VerifyOutcome
    confidence: float
    feedback: str
    evidence: dict[str, Any]


@dataclass(frozen=True)
class VerifierSpec:
    """一个白名单类型的完整规格。"""

    verifier_type: str
    environments: frozenset[str]
    implementation: VerifierImplementation
    validate_params: Callable[[Mapping[str, Any]], list[str]]
    evaluate: Callable[[Mapping[str, Any], Mapping[str, Any]], VerifyEvaluation] | None
    description: str


def _param_errors_str(params: Mapping[str, Any], key: str, *, max_length: int) -> list[str]:
    errors: list[str] = []
    if key not in params:
        errors.append(f"缺少参数 {key}")
        return errors
    value = params[key]
    if not isinstance(value, str):
        errors.append(f"参数 {key} 必须是字符串")
        return errors
    if not (1 <= len(value) <= max_length):
        errors.append(f"参数 {key} 长度必须在 1..{max_length}")
    return errors


def _reject_unknown_params(params: Mapping[str, Any], allowed: set[str]) -> list[str]:
    return [f"不允许的参数 {key}" for key in params if key not in allowed]


# ---------- 已实现的受控求值（纯函数，不执行任何外部代码） ----------


def _eval_python_exit_code_zero(params: Mapping[str, Any], actual: Mapping[str, Any]) -> VerifyEvaluation:
    if "exit_code" not in actual:
        return VerifyEvaluation(
            outcome=VerifyOutcome.UNCERTAIN,
            confidence=0.0,
            feedback="actual 结果缺少 exit_code，无法验证",
            evidence={"actual_keys": sorted(actual.keys())},
        )
    exit_code = actual["exit_code"]
    if not isinstance(exit_code, int) or isinstance(exit_code, bool):
        return VerifyEvaluation(
            outcome=VerifyOutcome.UNCERTAIN,
            confidence=0.0,
            feedback="actual.exit_code 不是整数，无法验证",
            evidence={"exit_code": repr(exit_code)},
        )
    if exit_code == 0:
        return VerifyEvaluation(
            outcome=VerifyOutcome.PASSED, confidence=1.0, feedback="进程退出码为 0", evidence={"exit_code": 0}
        )
    return VerifyEvaluation(
        outcome=VerifyOutcome.FAILED,
        confidence=1.0,
        feedback=f"进程退出码为 {exit_code}，非 0",
        evidence={"exit_code": exit_code},
    )


def _eval_python_stdout_contains(params: Mapping[str, Any], actual: Mapping[str, Any]) -> VerifyEvaluation:
    expected_text: str = params["text"]
    case_sensitive: bool = bool(params.get("case_sensitive", False))
    stdout = actual.get("stdout")
    if not isinstance(stdout, str):
        return VerifyEvaluation(
            outcome=VerifyOutcome.UNCERTAIN,
            confidence=0.0,
            feedback="actual 结果缺少字符串 stdout，无法验证",
            evidence={"actual_keys": sorted(actual.keys())},
        )
    haystack, needle = (stdout, expected_text) if case_sensitive else (stdout.lower(), expected_text.lower())
    if needle in haystack:
        return VerifyEvaluation(
            outcome=VerifyOutcome.PASSED,
            confidence=1.0,
            feedback=f"输出包含期望内容（长度 {len(needle)}）",
            evidence={"stdout_length": len(stdout)},
        )
    return VerifyEvaluation(
        outcome=VerifyOutcome.FAILED,
        confidence=1.0,
        feedback="输出中未找到期望内容",
        evidence={"stdout_length": len(stdout), "stdout_head": stdout[:200]},
    )


def _validate_python_exit_code_zero(params: Mapping[str, Any]) -> list[str]:
    return _reject_unknown_params(params, set())


def _validate_python_stdout_contains(params: Mapping[str, Any]) -> list[str]:
    errors = _reject_unknown_params(params, {"text", "case_sensitive"})
    errors.extend(_param_errors_str(params, "text", max_length=500))
    if "case_sensitive" in params and not isinstance(params["case_sensitive"], bool):
        errors.append("参数 case_sensitive 必须是布尔值")
    return errors


def _validate_reserved_mysql_params(allowed_keys: set[str]) -> Callable[[Mapping[str, Any]], list[str]]:
    def _validate(params: Mapping[str, Any]) -> list[str]:
        errors = _reject_unknown_params(params, allowed_keys)
        for key in allowed_keys & set(params):
            errors.extend(_param_errors_str(params, key, max_length=300))
        return errors

    return _validate


# ---------- 白名单注册表（冻结；实验文件不可扩展） ----------

VERIFIER_REGISTRY: Mapping[str, VerifierSpec] = MappingProxyType({
    "python_exit_code_zero": VerifierSpec(
        verifier_type="python_exit_code_zero",
        environments=frozenset({"python_web"}),
        implementation=VerifierImplementation.IMPLEMENTED,
        validate_params=_validate_python_exit_code_zero,
        evaluate=_eval_python_exit_code_zero,
        description="Python 程序退出码为 0（actual 需提供 exit_code）",
    ),
    "python_stdout_contains": VerifierSpec(
        verifier_type="python_stdout_contains",
        environments=frozenset({"python_web"}),
        implementation=VerifierImplementation.IMPLEMENTED,
        validate_params=_validate_python_stdout_contains,
        evaluate=_eval_python_stdout_contains,
        description="Python 程序标准输出包含指定文本（actual 需提供 stdout）",
    ),
    "mysql_query_result": VerifierSpec(
        verifier_type="mysql_query_result",
        environments=frozenset({"mysql_workbench"}),
        implementation=VerifierImplementation.RESERVED,
        validate_params=_validate_reserved_mysql_params({"query_description", "expect"}),
        evaluate=None,
        description="（预留，V2-06 实现）SQL 查询结果满足条件；当前仅支持结构表达，拒绝执行",
    ),
    "mysql_table_state": VerifierSpec(
        verifier_type="mysql_table_state",
        environments=frozenset({"mysql_workbench"}),
        implementation=VerifierImplementation.RESERVED,
        validate_params=_validate_reserved_mysql_params({"table", "expect"}),
        evaluate=None,
        description="（预留，V2-06 实现）数据库表状态满足条件；当前仅支持结构表达，拒绝执行",
    ),
})

# 白名单是只读映射（MappingProxyType）：运行期赋值/删除会抛 TypeError；
# 实验 JSON 更不可能扩展它。测试需要注入异常求值时，应替换模块属性而非修改注册表本身。


def get_spec(verifier_type: str) -> VerifierSpec | None:
    """按类型取规格；未知类型返回 None（fail-closed，调用方不得自行解释）。"""
    return VERIFIER_REGISTRY.get(verifier_type)


def validate_verifier_def(
    verifier_type: str,
    params: Mapping[str, Any],
    *,
    environment: str,
) -> list[str]:
    """加载期校验：类型必须在白名单内、参数合法、类型支持当前实验环境。"""
    spec = VERIFIER_REGISTRY.get(verifier_type)
    if spec is None:
        return [f"验证器类型 {verifier_type!r} 不在白名单中"]
    errors: list[str] = list(spec.validate_params(params))
    if environment not in spec.environments:
        errors.append(f"验证器类型 {verifier_type} 不支持环境 {environment}（支持：{sorted(spec.environments)}）")
    return errors


def evaluate_verifier(verifier_type: str, params: Mapping[str, Any], actual: Mapping[str, Any], *, step_id: str) -> VerifyResult:
    """执行期求值：fail-closed。未知类型 / reserved 类型 / 求值异常 → 一律 uncertain。

    uncertain 永远不允许引擎推进步骤。
    """
    spec = VERIFIER_REGISTRY.get(verifier_type)
    if spec is None:
        return VerifyResult(
            step_id=step_id,
            outcome=VerifyOutcome.UNCERTAIN,
            confidence=0.0,
            feedback=f"验证器类型 {verifier_type!r} 未注册，拒绝验证（fail-closed）",
            evidence={},
        )
    if spec.implementation is VerifierImplementation.RESERVED or spec.evaluate is None:
        return VerifyResult(
            step_id=step_id,
            outcome=VerifyOutcome.UNCERTAIN,
            confidence=0.0,
            feedback=f"验证器类型 {verifier_type} 尚未实现（预留），拒绝验证",
            evidence={"description": spec.description},
        )
    try:
        evaluation = spec.evaluate(params, actual)
    except Exception as exc:  # noqa: BLE001 —— 受控实现抛错也必须 fail-closed
        return VerifyResult(
            step_id=step_id,
            outcome=VerifyOutcome.UNCERTAIN,
            confidence=0.0,
            feedback=f"验证器求值异常：{exc.__class__.__name__}",
            evidence={},
        )
    return VerifyResult(
        step_id=step_id,
        outcome=evaluation.outcome,
        confidence=evaluation.confidence,
        feedback=evaluation.feedback,
        evidence=evaluation.evidence,
    )


__all__ = [
    "VERIFIER_REGISTRY",
    "VerifyEvaluation",
    "VerifierImplementation",
    "VerifierSpec",
    "evaluate_verifier",
    "get_spec",
    "validate_verifier_def",
]
