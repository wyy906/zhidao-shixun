"""实验定义模型与 Schema 结构约束测试（缺字段 / 类型错误 / 未知字段 / 版本 / 超长）。"""

import json
import sys
from pathlib import Path

import jsonschema
import pytest

from app.experiments.errors import ExperimentValidationError
from app.experiments.loader import load_experiment_dict

sys.path.insert(0, str(Path(__file__).resolve().parent))
from helpers_experiment import deep_copy, make_valid_experiment  # noqa: E402

SCHEMA_FILE = (Path(__file__).resolve().parents[2] / "experiments" / "schema" / "experiment_definition.schema.json")


def test_schema_file_exists_and_is_valid_draft2020() -> None:
    schema = json.loads(SCHEMA_FILE.read_text(encoding="utf-8"))
    validator = jsonschema.validators.validator_for(schema)
    assert validator is jsonschema.Draft202012Validator
    jsonschema.Draft202012Validator.check_schema(schema)  # Schema 本身合法


def test_valid_definition_passes_pydantic_and_schema() -> None:
    definition = load_experiment_dict(deep_copy(make_valid_experiment()))
    assert definition.experiment_id == "py-web-demo"
    assert definition.environment == "python_web"
    assert [s.step_id for s in definition.steps] == ["s1", "s2"]


def test_mysql_workbench_experiment_is_expressible() -> None:
    data = deep_copy(make_valid_experiment())
    data["experiment_id"] = "mysql-demo"
    data["environment"] = "mysql_workbench"
    data["adapter"] = {"adapter_id": "mysql_workbench", "capabilities": ["read_query_result"]}
    data["steps"] = [
        {
            "step_id": "open",
            "title": "打开查询窗口",
            "learning_goal": "熟悉 MySQL Workbench 查询窗口",
            "student_action": "打开 MySQL Workbench 并新建 SQL 标签页",
            "expected_state": {"description": "出现空白查询编辑窗口"},
            "verifier": {"type": "mysql_query_result", "params": {"query_description": "确认连接成功", "expect": "返回 1 行"}},
            "depends_on": [],
            "common_errors": ["服务未启动"],
            "recovery_hints": ["启动 MySQL 服务"],
            "guide_hint": 2,
        }
    ]
    definition = load_experiment_dict(data)
    assert definition.environment == "mysql_workbench"
    assert definition.steps[0].verifier.supported is False  # reserved：可表达、不可执行


@pytest.mark.parametrize(
    "mutate, path_fragment",
    [
        (lambda d: d.pop("title"), "title"),  # 缺字段
        (lambda d: d.pop("steps"), "steps"),  # 缺步骤
        (lambda d: d.update(title=123), "title"),  # 类型错误
        (lambda d: d.update(environment="vscode"), "environment"),  # 非法枚举
        (lambda d: d.update(experiment_id="BAD ID"), "experiment_id"),  # 非法 ID
        (lambda d: d.update(unknown_field=1), "<root>"),  # 未知字段
    ],
)
def test_schema_level_rejections(mutate, path_fragment) -> None:
    data = deep_copy(make_valid_experiment())
    mutate(data)
    with pytest.raises(ExperimentValidationError) as excinfo:
        load_experiment_dict(data)
    joined = "\n".join(str(i) for i in excinfo.value.issues)
    assert path_fragment in joined or "<root>" in joined


def test_unknown_schema_version_rejected() -> None:
    data = deep_copy(make_valid_experiment())
    data["schema_version"] = "9.9"
    with pytest.raises(ExperimentValidationError) as excinfo:
        load_experiment_dict(data)
    message = str(excinfo.value)
    assert "schema_version" in message
    assert "1.1" in message


def test_old_schema_version_1_0_rejected_with_upgrade_hint() -> None:
    """1.0 → 1.1 后，旧版本文件必须得到明确升级提示，不得尽力解析。"""
    data = deep_copy(make_valid_experiment())
    data["schema_version"] = "1.0"
    with pytest.raises(ExperimentValidationError) as excinfo:
        load_experiment_dict(data)
    message = str(excinfo.value)
    assert "schema_version" in message
    assert "1.1" in message


# ---------- 问题 4：preconditions 字段（操作前置条件，独立于 depends_on） ----------


def test_preconditions_roundtrip() -> None:
    data = deep_copy(make_valid_experiment())
    data["steps"][0]["preconditions"] = ["已启动本地 MySQL 服务", "示例数据库已导入"]
    definition = load_experiment_dict(data)
    assert definition.steps[0].preconditions == ["已启动本地 MySQL 服务", "示例数据库已导入"]
    # preconditions 不参与依赖计算：depends_on 仍为空
    assert definition.steps[0].depends_on == []


def test_preconditions_optional_by_default() -> None:
    data = deep_copy(make_valid_experiment())
    del data["steps"][0]["preconditions"]  # 1.1 中为可选字段
    definition = load_experiment_dict(data)
    assert definition.steps[0].preconditions == []


@pytest.mark.parametrize(
    "bad_value",
    [
        ["x" * 301],  # 单项超长（>300）
        [""],  # 空字符串
        [123],  # 非字符串
    ],
)
def test_preconditions_invalid_items_rejected(bad_value) -> None:
    data = deep_copy(make_valid_experiment())
    data["steps"][0]["preconditions"] = bad_value
    with pytest.raises(ExperimentValidationError):
        load_experiment_dict(data)


def test_preconditions_over_item_limit_rejected() -> None:
    data = deep_copy(make_valid_experiment())
    data["steps"][0]["preconditions"] = [f"条件{i}" for i in range(11)]  # maxItems 10
    with pytest.raises(ExperimentValidationError):
        load_experiment_dict(data)


def test_preconditions_mirrors_between_schema_and_model() -> None:
    """镜像一致性：同一份非法数据在 Schema 门与模型门都被拒绝（两道门约束一致）。"""
    import json as _json

    import jsonschema as _jsonschema

    data = deep_copy(make_valid_experiment())
    data["steps"][0]["preconditions"] = ["x" * 301]
    with pytest.raises(ExperimentValidationError):
        load_experiment_dict(data)  # loader 任意一道门拒绝即通过
    schema = _json.loads(SCHEMA_FILE.read_text(encoding="utf-8"))
    errors = list(_jsonschema.validators.validator_for(schema)(schema).iter_errors(data))
    assert any("preconditions" in str(list(e.absolute_path)) for e in errors)


def test_overlong_input_rejected() -> None:
    data = deep_copy(make_valid_experiment())
    data["title"] = "长" * 200  # 上限 120
    with pytest.raises(ExperimentValidationError):
        load_experiment_dict(data)


def test_step_count_limits_enforced() -> None:
    data = deep_copy(make_valid_experiment())
    data["steps"] = []  # minItems 1
    with pytest.raises(ExperimentValidationError):
        load_experiment_dict(data)
