"""步骤状态转换规则测试：转换表、验证结果驱动、终态保护、受保护入口、快照校验、跳过传播。"""

import sys
from pathlib import Path

import pytest
from zhidao_contracts import StepStatus, VerifyOutcome

from app.experiments.loader import load_experiment_dict
from app.experiments.state_machine import (
    TRANSITIONS,
    DependencyNotSatisfied,
    IllegalTransition,
    InvalidStateSnapshot,
    apply_skip_propagation,
    can_start,
    can_transition,
    compute_initial_states,
    refresh_ready_steps,
    start_step,
    transition,
)

import sys as _sys

_sys.path.insert(0, str(Path(__file__).resolve().parent))
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
        (StepStatus.PENDING, StepStatus.BLOCKED, None),  # 依赖失效传播（V2-03 审查修复新增）
        (StepStatus.BLOCKED, StepStatus.PENDING, None),
        (StepStatus.BLOCKED, StepStatus.SKIPPED, None),
        (StepStatus.IN_PROGRESS, StepStatus.PASSED, VerifyOutcome.PASSED),
        (StepStatus.IN_PROGRESS, StepStatus.FAILED, VerifyOutcome.FAILED),
        (StepStatus.IN_PROGRESS, StepStatus.SKIPPED, None),
        (StepStatus.FAILED, StepStatus.IN_PROGRESS, None),
        (StepStatus.FAILED, StepStatus.SKIPPED, None),
        (StepStatus.FAILED, StepStatus.BLOCKED, None),  # 依赖失效传播（V2-03 审查修复新增）
    ]
    for current, target, outcome in legal:
        assert transition(current, target, verify_outcome=outcome) is target


def test_all_illegal_transitions_rejected() -> None:
    illegal = [
        (StepStatus.PASSED, StepStatus.IN_PROGRESS, None),
        (StepStatus.PASSED, StepStatus.FAILED, VerifyOutcome.FAILED),
        (StepStatus.PASSED, StepStatus.SKIPPED, None),
        (StepStatus.SKIPPED, StepStatus.PENDING, None),
        (StepStatus.PENDING, StepStatus.PASSED, VerifyOutcome.PASSED),  # 跳过 in_progress 直接通过
        (StepStatus.BLOCKED, StepStatus.IN_PROGRESS, None),
        (StepStatus.IN_PROGRESS, StepStatus.BLOCKED, None),  # 执行中不能被外部拉回（审查修复）
        (StepStatus.FAILED, StepStatus.PASSED, VerifyOutcome.PASSED),
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


# ---------- 问题 1：终态保护 ----------


def _three_step_definition():
    data = deep_copy(make_valid_experiment())
    data["steps"] = [
        make_step("root"),
        make_step("mid", depends_on=["root"]),
        make_step("leaf", depends_on=["mid"]),
    ]
    return load_experiment_dict(data)


def test_skip_propagation_refuses_passed_target() -> None:
    definition = _three_step_definition()
    states = {"root": StepStatus.PASSED, "mid": StepStatus.BLOCKED, "leaf": StepStatus.BLOCKED}
    with pytest.raises(IllegalTransition, match="终态"):
        apply_skip_propagation(definition, states, "root")
    # 原快照未被破坏
    assert states["root"] is StepStatus.PASSED


def test_skip_propagation_refuses_already_skipped_target() -> None:
    definition = _three_step_definition()
    states = {"root": StepStatus.SKIPPED, "mid": StepStatus.BLOCKED, "leaf": StepStatus.BLOCKED}
    with pytest.raises(IllegalTransition, match="终态"):
        apply_skip_propagation(definition, states, "root")
    assert states["root"] is StepStatus.SKIPPED


# ---------- 问题 2：跳过传播不能绕过状态机 / 快照校验 / 原子性 ----------


def test_skip_propagation_rejects_snapshot_missing_step() -> None:
    definition = _three_step_definition()
    with pytest.raises(InvalidStateSnapshot, match="不一致"):
        apply_skip_propagation(definition, {"root": StepStatus.PENDING, "mid": StepStatus.BLOCKED}, "root")


def test_skip_propagation_rejects_snapshot_with_extra_step() -> None:
    definition = _three_step_definition()
    states = {
        "root": StepStatus.PENDING,
        "mid": StepStatus.BLOCKED,
        "leaf": StepStatus.BLOCKED,
        "ghost": StepStatus.PENDING,
    }
    with pytest.raises(InvalidStateSnapshot, match="多余"):
        apply_skip_propagation(definition, states, "root")


def test_skip_propagation_rejects_non_enum_values() -> None:
    definition = _three_step_definition()
    states = {"root": StepStatus.PENDING, "mid": "blocked", "leaf": StepStatus.BLOCKED}
    with pytest.raises(InvalidStateSnapshot, match="非法状态值"):
        apply_skip_propagation(definition, states, "root")


def test_skip_propagation_rejects_in_progress_downstream_atomically() -> None:
    """下游正在执行时传播整体失败（fail-closed），不产生部分修改。"""
    definition = _three_step_definition()
    states = {
        "root": StepStatus.PENDING,
        "mid": StepStatus.IN_PROGRESS,  # 无法经状态机置为 blocked
        "leaf": StepStatus.BLOCKED,
    }
    with pytest.raises(IllegalTransition, match="mid"):
        apply_skip_propagation(definition, states, "root")
    # 原子性：原快照完全未被修改
    assert states["root"] is StepStatus.PENDING
    assert states["mid"] is StepStatus.IN_PROGRESS


def test_skip_propagation_keeps_passed_downstream_and_blocks_below() -> None:
    """passed 下游保留（终态保护），但其下游仍因依赖链失效被阻塞。"""
    data = deep_copy(make_valid_experiment())
    data["steps"] = [
        make_step("root"),
        make_step("mid", depends_on=["root"]),
        make_step("leaf", depends_on=["mid", "root"]),
    ]
    definition = load_experiment_dict(data)
    states = {
        "root": StepStatus.PENDING,
        "mid": StepStatus.PASSED,
        "leaf": StepStatus.PENDING,
    }
    new_states = apply_skip_propagation(definition, states, "root")
    assert new_states["root"] is StepStatus.SKIPPED
    assert new_states["mid"] is StepStatus.PASSED  # 终态不被破坏
    assert new_states["leaf"] is StepStatus.BLOCKED  # 依赖失效传播到达更下游


def test_skip_propagation_changes_pending_and_failed_downstream_via_state_machine() -> None:
    data = deep_copy(make_valid_experiment())
    data["steps"] = [
        make_step("root"),
        make_step("pending_child", depends_on=["root"]),
        make_step("failed_child", depends_on=["root"]),
        make_step("blocked_child", depends_on=["root"]),
    ]
    definition = load_experiment_dict(data)
    states = {
        "root": StepStatus.PENDING,
        "pending_child": StepStatus.PENDING,
        "failed_child": StepStatus.FAILED,
        "blocked_child": StepStatus.BLOCKED,
    }
    new_states = apply_skip_propagation(definition, states, "root")
    assert new_states["root"] is StepStatus.SKIPPED
    assert new_states["pending_child"] is StepStatus.BLOCKED
    assert new_states["failed_child"] is StepStatus.BLOCKED
    assert new_states["blocked_child"] is StepStatus.BLOCKED


# ---------- 问题 3：受保护操作入口 ----------


def test_refresh_ready_steps_only_unlocks_with_all_deps_passed() -> None:
    definition = _three_step_definition()  # mid/leaf blocked（依赖 root）
    states = {"root": StepStatus.PASSED, "mid": StepStatus.BLOCKED, "leaf": StepStatus.BLOCKED}
    new_states = refresh_ready_steps(definition, states)
    assert new_states["mid"] is StepStatus.PENDING  # 依赖 root=passed → 解除
    assert new_states["leaf"] is StepStatus.BLOCKED  # 依赖 mid≠passed → 不放行


@pytest.mark.parametrize(
    "dep_state",
    [StepStatus.SKIPPED, StepStatus.FAILED, StepStatus.PENDING, StepStatus.BLOCKED],
)
def test_refresh_ready_steps_refuses_non_passed_dependency(dep_state) -> None:
    definition = _three_step_definition()
    states = {"root": dep_state, "mid": StepStatus.BLOCKED, "leaf": StepStatus.BLOCKED}
    new_states = refresh_ready_steps(definition, states)
    assert new_states["mid"] is StepStatus.BLOCKED  # 非 passed 依赖不放行


def test_start_step_rejects_unsatisfied_dependency_types() -> None:
    definition = _three_step_definition()
    for dep_state in (StepStatus.SKIPPED, StepStatus.FAILED, StepStatus.PENDING, StepStatus.BLOCKED):
        states = {"root": dep_state, "mid": StepStatus.BLOCKED, "leaf": StepStatus.BLOCKED}
        with pytest.raises(DependencyNotSatisfied, match="root"):
            start_step(definition, states, "mid")


def test_start_step_unlocks_blocked_step_with_satisfied_deps() -> None:
    """blocked + 依赖全部 passed → 受保护入口直接解除并开始（两步均经状态机）。"""
    definition = _three_step_definition()
    states = {"root": StepStatus.PASSED, "mid": StepStatus.BLOCKED, "leaf": StepStatus.BLOCKED}
    new_states = start_step(definition, states, "mid")
    assert new_states["mid"] is StepStatus.IN_PROGRESS
    assert states["mid"] is StepStatus.BLOCKED  # 原快照不变


def test_start_step_works_for_pending_step_without_deps() -> None:
    definition = _three_step_definition()
    states = {"root": StepStatus.PENDING, "mid": StepStatus.BLOCKED, "leaf": StepStatus.BLOCKED}
    new_states = start_step(definition, states, "root")
    assert new_states["root"] is StepStatus.IN_PROGRESS


def test_start_step_rejects_unknown_step_and_bad_snapshot() -> None:
    definition = _three_step_definition()
    states = {"root": StepStatus.PENDING, "mid": StepStatus.BLOCKED, "leaf": StepStatus.BLOCKED}
    with pytest.raises(InvalidStateSnapshot, match="不在实验"):
        start_step(definition, states, "nope")
    with pytest.raises(InvalidStateSnapshot):
        start_step(definition, {"root": StepStatus.PENDING}, "root")


def test_full_flow_refresh_then_start_then_pass_unlocks_downstream() -> None:
    """组合流：blocked → refresh → start → verify passed → refresh 解除下游。"""
    definition = _three_step_definition()
    states = compute_initial_states(definition)
    assert states == {"root": StepStatus.PENDING, "mid": StepStatus.BLOCKED, "leaf": StepStatus.BLOCKED}

    states = start_step(definition, states, "root")
    # 验证结果驱动 root → passed（经状态机校验后写入快照）
    transition(states["root"], StepStatus.PASSED, verify_outcome=VerifyOutcome.PASSED)
    states = states | {"root": StepStatus.PASSED}
    states = refresh_ready_steps(definition, states)
    assert states["mid"] is StepStatus.PENDING

    states = start_step(definition, states, "mid")
    assert states["mid"] is StepStatus.IN_PROGRESS
    # mid 失败 → leaf 无法开始
    states = states | {"mid": transition(states["mid"], StepStatus.FAILED, verify_outcome=VerifyOutcome.FAILED)}
    with pytest.raises(DependencyNotSatisfied):
        start_step(definition, states, "leaf")
