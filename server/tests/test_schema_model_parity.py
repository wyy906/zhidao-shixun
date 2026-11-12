"""Schema/Pydantic 镜像一致性表驱动测试（第三轮复审要求）。

关键点：不经过 load_experiment_dict（它会先跑 JSON Schema 门，可能掩盖 Pydantic 未镜像的问题），
而是直接分别调用：
1. JSON Schema validator（experiments/schema/experiment_definition.schema.json 独立校验）
2. ExperimentDefinition.model_validate()（Pydantic 独立校验）

每类约束分别断言：合法边界数据两者都接受；非法数据两者都拒绝。
"""

import json
import sys
from pathlib import Path

import jsonschema
import pytest
from pydantic import ValidationError

from app.experiments.loader import SCHEMA_FILE
from app.experiments.models import ExperimentDefinition, VerifierDef

sys.path.insert(0, str(Path(__file__).resolve().parent))
from helpers_experiment import deep_copy, make_valid_experiment  # noqa: E402

_SCHEMA = json.loads(SCHEMA_FILE.read_text(encoding="utf-8"))
_SCHEMA_VALIDATOR = jsonschema.validators.validator_for(_SCHEMA)(_SCHEMA)


def schema_accepts(data) -> bool:
    return _SCHEMA_VALIDATOR.is_valid(data)


def model_accepts(data) -> bool:
    try:
        ExperimentDefinition.model_validate(data)
        return True
    except ValidationError:
        return False


# ---------- 非法数据：JSON Schema 与 Pydantic 必须都拒绝 ----------

INVALID_CASES = [
    pytest.param(
        lambda d: d["steps"][0].update(depends_on=["s1", "s1"]),
        "depends_on 重复 ID",
        id="depends_on-duplicate",
    ),
    pytest.param(
        lambda d: d["steps"][0].update(depends_on=["BAD_ID"]),
        "depends_on 非法 ID（大写/空格）",
        id="depends_on-bad-pattern",
    ),
    pytest.param(
        lambda d: d["steps"][0]["expected_state"].update(artifacts=[""]),
        "artifacts 空字符串",
        id="artifacts-empty-string",
    ),
    pytest.param(
        lambda d: d["steps"][0]["expected_state"].update(artifacts=["x" * 201]),
        "artifacts 超长（>200）",
        id="artifacts-too-long",
    ),
    pytest.param(
        lambda d: d["steps"][0]["expected_state"].update(artifacts=[123]),
        "artifacts 非字符串",
        id="artifacts-non-string",
    ),
    pytest.param(
        lambda d: d["adapter"].update(capabilities=["read_stdout", "read_stdout"]),
        "capabilities 重复",
        id="capabilities-duplicate",
    ),
    pytest.param(
        lambda d: d["adapter"].update(capabilities=[""]),
        "capabilities 空字符串",
        id="capabilities-empty-string",
    ),
    pytest.param(
        lambda d: d["adapter"].update(capabilities=["x" * 41]),
        "capabilities 超长（>40）",
        id="capabilities-too-long",
    ),
    pytest.param(
        lambda d: d.update(prerequisites=[""]),
        "prerequisites 空字符串",
        id="prerequisites-empty-string",
    ),
    pytest.param(
        lambda d: d.update(prerequisites=["x" * 201]),
        "prerequisites 超长（>200）",
        id="prerequisites-too-long",
    ),
    pytest.param(
        lambda d: d.update(prerequisites=[123]),
        "prerequisites 非字符串",
        id="prerequisites-non-string",
    ),
    pytest.param(
        lambda d: d["steps"][0].update(preconditions=["x" * 301]),
        "preconditions 超长（>300）",
        id="preconditions-too-long",
    ),
    pytest.param(
        lambda d: d["steps"][0].update(preconditions=[""]),
        "preconditions 空字符串",
        id="preconditions-empty-string",
    ),
    pytest.param(
        lambda d: d["steps"][0].update(common_errors=[""]),
        "common_errors 空字符串",
        id="common_errors-empty-string",
    ),
    pytest.param(
        lambda d: d["steps"][0].update(recovery_hints=["x" * 301]),
        "recovery_hints 超长（>300）",
        id="recovery_hints-too-long",
    ),
    pytest.param(
        lambda d: d["steps"][0].update(step_id="BAD_STEP"),
        "step_id 非法格式",
        id="step_id-bad-pattern",
    ),
    pytest.param(
        lambda d: d["meta"].update(estimated_minutes=0),
        "estimated_minutes 超下界",
        id="meta-estimated-minutes-below",
    ),
    pytest.param(
        lambda d: d["meta"].update(estimated_minutes=601),
        "estimated_minutes 超上界",
        id="meta-estimated-minutes-above",
    ),
    pytest.param(
        lambda d: d["meta"].update(difficulty="expert"),
        "difficulty 非法枚举",
        id="meta-difficulty-bad-enum",
    ),
    pytest.param(
        lambda d: d["steps"][0].update(guide_hint=0),
        "guide_hint 超下界",
        id="guide_hint-below",
    ),
    pytest.param(
        lambda d: d["steps"][0].update(guide_hint=5),
        "guide_hint 超上界",
        id="guide_hint-above",
    ),
]


@pytest.mark.parametrize("mutate, description", INVALID_CASES)
def test_invalid_data_rejected_by_both_schema_and_model(mutate, description) -> None:
    data = deep_copy(make_valid_experiment())
    mutate(data)
    assert not schema_accepts(data), f"JSON Schema 应拒绝：{description}"
    assert not model_accepts(data), f"Pydantic 应拒绝（镜像缺失）：{description}"


# ---------- 合法边界数据：JSON Schema 与 Pydantic 必须都接受 ----------

BOUNDARY_CASES = [
    pytest.param(
        lambda d: d["steps"][0]["expected_state"].update(artifacts=["x" * 200]),
        "artifacts 恰好 200 字符",
        id="artifacts-200-ok",
    ),
    pytest.param(
        lambda d: d.update(prerequisites=["y" * 200]),
        "prerequisites 恰好 200 字符",
        id="prerequisites-200-ok",
    ),
    pytest.param(
        lambda d: d["adapter"].update(capabilities=["z" * 40]),
        "capabilities 恰好 40 字符",
        id="capabilities-40-ok",
    ),
    pytest.param(
        lambda d: d["steps"][0].update(preconditions=["p" * 300]),
        "preconditions 恰好 300 字符",
        id="preconditions-300-ok",
    ),
    pytest.param(
        lambda d: d["steps"][1].update(depends_on=["s1", "s1x", "s1-y"]),
        "depends_on 合法 ID 组合（下划线/连字符）",
        id="depends_on-valid-ids",
    ),
    pytest.param(
        lambda d: d["adapter"].update(capabilities=[]),
        "capabilities 空数组合法",
        id="capabilities-empty-ok",
    ),
    pytest.param(
        lambda d: d.update(prerequisites=[]),
        "prerequisites 空数组合法",
        id="prerequisites-empty-ok",
    ),
    pytest.param(
        lambda d: d["meta"].update(estimated_minutes=1),
        "estimated_minutes 下边界 1",
        id="meta-min-ok",
    ),
    pytest.param(
        lambda d: d["meta"].update(estimated_minutes=600),
        "estimated_minutes 上边界 600",
        id="meta-max-ok",
    ),
    pytest.param(
        lambda d: d["steps"][0].update(guide_hint=4),
        "guide_hint 上边界 4",
        id="guide_hint-max-ok",
    ),
]


@pytest.mark.parametrize("mutate, description", BOUNDARY_CASES)
def test_boundary_data_accepted_by_both_schema_and_model(mutate, description) -> None:
    data = deep_copy(make_valid_experiment())
    mutate(data)
    assert schema_accepts(data), f"JSON Schema 应接受合法边界：{description}"
    assert model_accepts(data), f"Pydantic 应接受合法边界（镜像过严）：{description}"


def test_baseline_valid_data_accepted_by_both() -> None:
    data = deep_copy(make_valid_experiment())
    assert schema_accepts(data)
    assert model_accepts(data)


# ---------- 第四轮复审：schema_version 与 verifier.type 的双通道镜像 ----------

ALL_VERIFIER_TYPES = [
    "python_exit_code_zero",
    "python_stdout_contains",
    "mysql_query_result",
    "mysql_table_state",
]


@pytest.mark.parametrize("version", ["1.1"])
def test_schema_version_1_1_accepted_by_both(version) -> None:
    data = deep_copy(make_valid_experiment())
    data["schema_version"] = version
    assert schema_accepts(data)
    assert model_accepts(data)


@pytest.mark.parametrize("version", ["1.0", "9.9", "2.0", ""])
@pytest.mark.parametrize("channel", ["schema", "model"], ids=str)
def test_schema_version_illegal_rejected_by_both_channels(version, channel) -> None:
    data = deep_copy(make_valid_experiment())
    data["schema_version"] = version
    if channel == "schema":
        assert not schema_accepts(data), f"JSON Schema 应拒绝 schema_version={version!r}"
    else:
        with pytest.raises(ValidationError):
            ExperimentDefinition.model_validate(data)


@pytest.mark.parametrize("verifier_type", ALL_VERIFIER_TYPES)
def test_all_whitelisted_verifier_types_accepted_by_both(verifier_type) -> None:
    """四种白名单类型在结构层均通过（是否实现/环境匹配由 registry 与语义校验负责）。"""
    data = deep_copy(make_valid_experiment())
    data["steps"][0]["verifier"] = {"type": verifier_type, "params": {}}
    # mysql_* 与 python_web 环境不匹配属语义层，不影响结构校验；结构层两通道都应接受
    assert schema_accepts(data)
    assert model_accepts(data)


def test_whitelisted_verifier_types_accepted_by_verifier_model_alone() -> None:
    """直接调用 VerifierDef.model_validate()：四种合法类型均通过。"""
    for verifier_type in ALL_VERIFIER_TYPES:
        verifier = VerifierDef.model_validate({"type": verifier_type, "params": {}})
        assert verifier.type == verifier_type


@pytest.mark.parametrize(
    "bad_type",
    ["eval_actual", "os_command", "Python_Exit_Code_Zero", "", "shell_exec"],
    ids=str,
)
def test_unknown_verifier_type_rejected_by_both_channels(bad_type) -> None:
    data = deep_copy(make_valid_experiment())
    data["steps"][0]["verifier"] = {"type": bad_type, "params": {}}
    assert not schema_accepts(data), f"JSON Schema 应拒绝未知验证器类型 {bad_type!r}"
    with pytest.raises(ValidationError):
        ExperimentDefinition.model_validate(data)


@pytest.mark.parametrize(
    "bad_type",
    ["eval_actual", "os_command", "", "shell_exec"],
    ids=str,
)
def test_unknown_verifier_type_rejected_by_verifier_model_alone(bad_type) -> None:
    """直接调用 VerifierDef.model_validate()：未知类型必须拒绝。"""
    with pytest.raises(ValidationError):
        VerifierDef.model_validate({"type": bad_type, "params": {}})
