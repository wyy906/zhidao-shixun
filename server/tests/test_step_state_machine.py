"""步骤状态转换规则测试：转换表、验证结果驱动、uncertain 不推进、初始状态、跳过传播。"""

import sys
from pathlib import Path

import pytest
from zhidao_contracts import StepStatus, VerifyOutcome

from app.experiments.loader import load_experiment_dict
from app.experiments.state_machine import (
    TRANSITIONS,
    IllegalTransition,
    apply_skip_propagation,
    can_start,
    can_transition,
    compute_initial_states,
    transition,
)

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from helpers_experiment import deep_copy, make_step, make_valid_experiment  # noqa: E402


def _definition():
    return load_experiment_dict(deep_copy(make_valid_experiment()))


def test_transition_table_is_total_and_terminal() -> None:
    assert set(TRANSITIONS) == set(StepStatus)
    # 终态不可再转换
    assert TRANSITIONS[StepStatus.PASSED] == frozenset()
    assert TRANSITIONS[StepStatus.SKIPPED] == frozenset()


def test_all_legal_transitions_succeed() -> None:
    legal = [
        (StepStatus.PENDING, StepStatus.IN_PROGRESS, None),
        (StepStatus.PENDING, StepStatus.SKIPPED, None),
        (StepStatus.BLOCKED, StepStatus.PENDING, None),
        (StepStatus.BLOCKED, StepStatus.SKIPPED, None),
        (StepStatus.IN_PROGRESS, StepStatus.PASSED, VerifyOutcome.PASSED),
        (StepStatus.IN_PROGRESS, StepStatus.FAILED, VerifyOutcome.FAILED),
        (StepStatus.IN_PROGRESS, StepStatus.SKIPPED, None),
        (StepStatus.FAILED, StepStatus.IN_PROGRESS, None),
        (StepStatus.FAILED, StepStatus.SKIPPED, None),
    ]
    for current, target, outcome in legal:
        assert transition(current, target, verify_outcome=outcome) is target


def test_all_illegal_transitions_rejected() -> None:
    illegal = [
        (StepStatus.PASSED, StepStatus.IN_PROGRESS, None),
        (StepStatus.PASSED, StepStatus.FAILED, VerifyOutcome.FAILED),
        (StepStatus.SKIPPED, StepStatus.PENDING, None),
        (StepStatus.PENDING, StepStatus.PASSED, VerifyOutcome.PASSED),  # 跳过 in_progress 直接通过
        (StepStatus.BLOCKED, StepStatus.IN_PROGRESS, None),
        (StepStatus.FAILED, StepStatus.PASSED, VerifyOutcome.PASSED),
        (StepStatus.PENDING, StepStatus.BLOCKED, None),
    ]
    for current, target, outcome in illegal:
        with pytest.raises(IllegalTransition):
            transition(current, target, verify_outcome=outcome)


def test_passed_requires_passed_outcome() -> None:
    for outcome in (None, VerifyOutcome.FAILED, VerifyOutcome.UNCERTAIN):
        with pytest.raises(IllegalTransition):
            transition(StepStatus.IN_PROGRESS, StepStatus.PASSED, verify_outcome=outcome)


def test_failed_requires_failed_outcome() -> None:
    for outcome in (None, VerifyOutcome.PASSED):
        with pytest.raises(IllegalTransition):
            transition(StepStatus.IN_PROGRESS, StepStatus.FAILED, verify_outcome=outcome)


def test_uncertain_never_advances() -> None:
    for target in (StepStatus.PASSED, StepStatus.FAILED, StepStatus.IN_PROGRESS, StepStatus.SKIPPED):
        with pytest.raises(IllegalTransition):
            transition(StepStatus.IN_PROGRESS, target, verify_outcome=VerifyOutcome.UNCERTAIN)


def test_can_transition_pure_table() -> None:
    assert can_transition(StepStatus.PENDING, StepStatus.IN_PROGRESS)
    assert not can_transition(StepStatus.PENDING, StepStatus.PASSED)
    assert not can_transition(StepStatus.PASSED, StepStatus.PASSED)


def test_initial_states_and_can_start() -> None:
    definition = _definition()  # s2 depends on s1
    states = compute_initial_states(definition)
    assert states == {"s1": StepStatus.PENDING, "s2": StepStatus.BLOCKED}
    assert can_start(definition.get_step("s1"), states)
    assert not can_start(definition.get_step("s2"), states)

    # s1 通过后 s2 可开始
    states2 = dict(states)
    states2["s1"] = StepStatus.PASSED
    assert can_start(definition.get_step("s2"), states2)


def test_skipped_dependency_does_not_satisfy_downstream() -> None:
    definition = _definition()
    states = {"s1": StepStatus.SKIPPED, "s2": StepStatus.BLOCKED}
    assert not can_start(definition.get_step("s2"), states)


def test_skip_propagation_blocks_downstream() -> None:
    data = deep_copy(make_valid_experiment())
    data["steps"] = [
        make_step("root"),
        make_step("mid", depends_on=["root"]),
        make_step("leaf", depends_on=["mid"]),
    ]
    definition = load_experiment_dict(data)
    states = {"root": StepStatus.PENDING, "mid": StepStatus.BLOCKED, "leaf": StepStatus.BLOCKED}

    new_states = apply_skip_propagation(definition, states, "root")
    assert new_states["root"] is StepStatus.SKIPPED
    assert new_states["mid"] is StepStatus.BLOCKED
    assert new_states["leaf"] is StepStatus.BLOCKED
    # 下游不能自动视为通过
    assert new_states["leaf"] is not StepStatus.PASSED
    # 原字典不被修改
    assert states["root"] is StepStatus.PENDING


def test_skip_propagation_spares_terminal_states() -> None:
    data = deep_copy(make_valid_experiment())
    data["steps"] = [make_step("root"), make_step("mid", depends_on=["root"])]
    definition = load_experiment_dict(data)
    states = {"root": StepStatus.PENDING, "mid": StepStatus.PASSED}
    new_states = apply_skip_propagation(definition, states, "root")
    assert new_states["mid"] is StepStatus.PASSED  # 已终态不受影响
