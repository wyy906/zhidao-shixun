"""加载器语义校验测试：错误必须可定位（文件 + 字段路径 + 原因）。"""

import json
import sys
from pathlib import Path

import pytest

from app.experiments.errors import ExperimentValidationError
from app.experiments.loader import load_experiment_dict, load_experiment_file

sys.path.insert(0, str(Path(__file__).resolve().parent))
from helpers_experiment import deep_copy, make_step, make_valid_experiment  # noqa: E402


def test_adapter_environment_mismatch_rejected() -> None:
    data = deep_copy(make_valid_experiment())
    data["environment"] = "mysql_workbench"  # adapter 仍是 python_web
    with pytest.raises(ExperimentValidationError) as excinfo:
        load_experiment_dict(data)
    issue = excinfo.value.issues[0]
    assert issue.path == "adapter.adapter_id"
    assert issue.category == "semantic"


def test_duplicate_step_id_rejected() -> None:
    data = deep_copy(make_valid_experiment())
    data["steps"] = [make_step("s1"), make_step("s1")]
    with pytest.raises(ExperimentValidationError) as excinfo:
        load_experiment_dict(data)
    assert any("步骤 ID 重复" in i.message for i in excinfo.value.issues)


def test_unknown_dependency_rejected() -> None:
    data = deep_copy(make_valid_experiment())
    data["steps"][1]["depends_on"] = ["ghost"]
    with pytest.raises(ExperimentValidationError) as excinfo:
        load_experiment_dict(data)
    assert any("ghost" in i.message and "不存在" in i.message for i in excinfo.value.issues)


def test_self_dependency_rejected() -> None:
    data = deep_copy(make_valid_experiment())
    data["steps"][0]["depends_on"] = ["s1"]
    with pytest.raises(ExperimentValidationError) as excinfo:
        load_experiment_dict(data)
    assert any("循环依赖" in i.message for i in excinfo.value.issues)


def test_three_step_cycle_rejected_with_path() -> None:
    data = deep_copy(make_valid_experiment())
    data["steps"] = [
        make_step("a", depends_on=["c"]),
        make_step("b", depends_on=["a"]),
        make_step("c", depends_on=["b"]),
    ]
    with pytest.raises(ExperimentValidationError) as excinfo:
        load_experiment_dict(data)
    joined = "\n".join(i.message for i in excinfo.value.issues)
    assert "循环依赖" in joined
    assert "a" in joined and "c" in joined


def test_unknown_verifier_type_rejected() -> None:
    data = deep_copy(make_valid_experiment())
    data["steps"][0]["verifier"] = {"type": "eval_actual", "params": {"code": "import os"}}
    with pytest.raises(ExperimentValidationError) as excinfo:
        load_experiment_dict(data)
    joined = "\n".join(i.message for i in excinfo.value.issues)
    # Schema 层枚举白名单直接拦截：未知类型与其携带的任何内容都不会成为可执行验证器
    assert "eval_actual" in joined
    assert "is not one of" in joined or "不在白名单" in joined


def test_verifier_param_errors_rejected() -> None:
    data = deep_copy(make_valid_experiment())
    data["steps"][1]["verifier"] = {"type": "python_stdout_contains", "params": {"text": ""}}  # 空文本
    with pytest.raises(ExperimentValidationError) as excinfo:
        load_experiment_dict(data)
    joined = "\n".join(i.message for i in excinfo.value.issues)
    assert "text" in joined
    assert excinfo.value.issues[0].path == "steps[1].verifier.type"


def test_verifier_environment_mismatch_rejected() -> None:
    data = deep_copy(make_valid_experiment())
    data["steps"][0]["verifier"] = {"type": "mysql_table_state", "params": {"table": "t1", "expect": "有 3 行"}}
    with pytest.raises(ExperimentValidationError) as excinfo:
        load_experiment_dict(data)
    joined = "\n".join(i.message for i in excinfo.value.issues)
    assert "不支持环境 python_web" in joined


def test_reserved_verifier_loads_but_marked_unsupported() -> None:
    data = deep_copy(make_valid_experiment())
    data["steps"][0]["verifier"] = {"type": "mysql_query_result", "params": {"query_description": "x", "expect": "y"}}
    # mysql_query_result 不支持 python_web 环境 → 应拒绝
    with pytest.raises(ExperimentValidationError):
        load_experiment_dict(data)

    # 放到正确的环境中则可以结构化表达，但 supported=False
    data["environment"] = "mysql_workbench"
    data["adapter"] = {"adapter_id": "mysql_workbench", "capabilities": []}
    data["steps"] = [make_step("open", verifier={"type": "mysql_query_result", "params": {"query_description": "x", "expect": "y"}})]
    definition = load_experiment_dict(data)
    assert definition.steps[0].verifier.supported is False


def test_file_loading_reports_file_and_reason(tmp_path) -> None:
    good = tmp_path / "good.json"
    good.write_text(json.dumps(make_valid_experiment(), ensure_ascii=False), encoding="utf-8")
    definition = load_experiment_file(good)
    assert definition.experiment_id == "py-web-demo"

    bad = tmp_path / "bad.json"
    bad.write_text("{ not valid json", encoding="utf-8")
    with pytest.raises(ExperimentValidationError) as excinfo:
        load_experiment_file(bad)
    issue = excinfo.value.issues[0]
    assert issue.category == "file"
    assert str(bad) in (issue.file or "")
    assert "JSON" in issue.message

    missing = tmp_path / "missing.json"
    with pytest.raises(ExperimentValidationError) as excinfo:
        load_experiment_file(missing)
    assert "文件不存在" in str(excinfo.value)


def test_schema_issue_includes_field_path_and_file(tmp_path) -> None:
    bad = tmp_path / "bad2.json"
    data = deep_copy(make_valid_experiment())
    data["steps"][0]["unexpected"] = True
    bad.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
    with pytest.raises(ExperimentValidationError) as excinfo:
        load_experiment_file(bad)
    issue = excinfo.value.issues[0]
    assert "steps[0]" in issue.path
    assert issue.category == "schema"
