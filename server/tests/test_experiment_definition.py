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
    assert "1.0" in message


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
