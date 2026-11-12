"""步骤依赖图测试：拓扑排序、环检测（含环路径）、存在性校验。"""

import sys
from pathlib import Path

import pytest

from app.experiments.dependency import (
    DependencyError,
    build_graph,
    topological_order,
    validate_dependencies,
)
from app.experiments.errors import ExperimentValidationError
from app.experiments.models import StepDefinition

sys.path.insert(0, str(Path(__file__).resolve().parent))
from helpers_experiment import deep_copy, make_step, make_valid_experiment  # noqa: E402

from app.experiments.loader import load_experiment_dict  # noqa: E402


def _steps_from(data) -> list:
    return load_experiment_dict(data).steps


def _model_steps(*steps: dict) -> list:
    return [StepDefinition.model_validate(step) for step in steps]


def test_build_graph() -> None:
    steps = _steps_from(deep_copy(make_valid_experiment()))
    assert build_graph(steps) == {"s1": [], "s2": ["s1"]}


def test_topological_order_respects_dependencies() -> None:
    steps = _steps_from(deep_copy(make_valid_experiment()))
    assert topological_order(steps) == ["s1", "s2"]


def test_diamond_graph_order() -> None:
    data = deep_copy(make_valid_experiment())
    data["steps"] = [
        make_step("root"),
        make_step("left", depends_on=["root"]),
        make_step("right", depends_on=["root"]),
        make_step("sink", depends_on=["left", "right"]),
    ]
    order = topological_order(_steps_from(data))
    assert order.index("root") < order.index("left")
    assert order.index("root") < order.index("right")
    assert order.index("left") < order.index("sink")
    assert order.index("right") < order.index("sink")


@pytest.mark.parametrize(
    "deps_by_step, expect_cycle",
    [
        ({"s1": ["s1"]}, True),  # 自依赖
        ({"s1": [], "s2": ["s1", "s2"]}, True),  # 自依赖混合
    ],
)
def test_self_cycles(deps_by_step, expect_cycle) -> None:
    data = deep_copy(make_valid_experiment())
    data["steps"] = [make_step(sid, depends_on=deps) for sid, deps in deps_by_step.items()]
    with pytest.raises((ExperimentValidationError, DependencyError)):
        load_experiment_dict(data)
        validate_dependencies(_steps_from(data))


def test_two_node_cycle_detected() -> None:
    steps = _model_steps(
        make_step("a", depends_on=["b"]),
        make_step("b", depends_on=["a"]),
    )
    with pytest.raises(DependencyError) as excinfo:
        validate_dependencies(steps)
    assert "循环依赖" in str(excinfo.value)


def test_unknown_dependency_raises() -> None:
    steps = _model_steps(make_step("a", depends_on=["nope"]))
    with pytest.raises(DependencyError) as excinfo:
        validate_dependencies(steps)
    assert "不存在" in str(excinfo.value)
