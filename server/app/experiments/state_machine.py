"""步骤状态转换规则（纯函数领域规则，V2-07 前不涉及 AI）。

规则（AI_COLLABORATION.md §7 V2-03 第 4 条）：
- 合法转换表见 TRANSITIONS；passed 与 skipped 是终态，不可再转换。
- 进入 passed / failed 必须携带对应的验证结果；uncertain 永不推进步骤。
- 禁止通过直接改状态文本把步骤标记为 passed——本模块是唯一合法入口，且强制验证结果驱动。
- 依赖未通过的步骤初始即为 blocked；依赖只有全部 passed 才能开始（skipped 的依赖不视为通过）。
- skipped 的步骤会阻塞其全部直接/间接下游（不能自动视为通过）。
"""

from zhidao_contracts import StepStatus, VerifyOutcome

from app.experiments.models import ExperimentDefinition, StepDefinition

# 当前状态 → 允许的目标状态集合（纯状态机层面；passed/failed 另需验证结果佐证）
TRANSITIONS: dict[StepStatus, frozenset[StepStatus]] = {
    StepStatus.PENDING: frozenset({StepStatus.IN_PROGRESS, StepStatus.SKIPPED}),
    StepStatus.BLOCKED: frozenset({StepStatus.PENDING, StepStatus.SKIPPED}),
    StepStatus.IN_PROGRESS: frozenset({StepStatus.PASSED, StepStatus.FAILED, StepStatus.SKIPPED}),
    StepStatus.FAILED: frozenset({StepStatus.IN_PROGRESS, StepStatus.SKIPPED}),
    StepStatus.PASSED: frozenset(),  # 终态
    StepStatus.SKIPPED: frozenset(),  # 终态
}


class IllegalTransition(Exception):
    """非法状态转换。"""

    def __init__(self, current: StepStatus, target: StepStatus, reason: str):
        super().__init__(f"不允许从 {current.value} 转换到 {target.value}：{reason}")
        self.current = current
        self.target = target
        self.reason = reason


def can_transition(current: StepStatus, target: StepStatus) -> bool:
    """纯状态机层面是否允许（不含验证结果要求）。"""
    return target in TRANSITIONS[current]


def transition(
    current: StepStatus,
    target: StepStatus,
    *,
    verify_outcome: VerifyOutcome | None = None,
) -> StepStatus:
    """执行状态转换；非法时抛 IllegalTransition。

    - target 为 passed：必须 verify_outcome == passed；
    - target 为 failed：必须 verify_outcome == failed；
    - verify_outcome 为 uncertain：无论 target 是什么都不允许推进；
    - 其余转换按 TRANSITIONS 表判定。
    """
    if verify_outcome is VerifyOutcome.UNCERTAIN:
        raise IllegalTransition(current, target, "验证结果为 uncertain，不能推进步骤")
    if target is StepStatus.PASSED and verify_outcome is not VerifyOutcome.PASSED:
        raise IllegalTransition(current, target, "passed 必须由验证结果（passed）驱动，不能直接标记")
    if target is StepStatus.FAILED and verify_outcome is not VerifyOutcome.FAILED:
        raise IllegalTransition(current, target, "failed 必须由验证结果（failed）驱动，不能直接标记")
    if not can_transition(current, target):
        raise IllegalTransition(current, target, "不在合法转换表中")
    return target


def compute_initial_states(definition: ExperimentDefinition) -> dict[str, StepStatus]:
    """初始状态：无依赖 → pending；有依赖（未验证通过）→ blocked。"""
    return {
        step.step_id: StepStatus.PENDING if not step.depends_on else StepStatus.BLOCKED
        for step in definition.steps
    }


def can_start(step: StepDefinition, states: dict[str, StepStatus]) -> bool:
    """能否开始执行：全部依赖均为 passed（skipped 的依赖不视为通过，下游保持阻塞）。"""
    return all(states.get(dep) is StepStatus.PASSED for dep in step.depends_on)


def dependents_of(definition: ExperimentDefinition, step_id: str) -> list[str]:
    """直接依赖 step_id 的步骤（即 step_id 的下游一步）。"""
    return [step.step_id for step in definition.steps if step_id in step.depends_on]


def apply_skip_propagation(
    definition: ExperimentDefinition,
    states: dict[str, StepStatus],
    skipped_step_id: str,
) -> dict[str, StepStatus]:
    """将 skipped_step_id 置为 skipped，并把它全部直接/间接下游中「未到达终态」的步骤置为 blocked。

    规则：跳过不等于通过——下游不会自动 passed。已是终态（passed/skipped）的步骤不受影响。
    返回新的状态字典（不修改入参）。
    """
    new_states = dict(states)
    new_states[skipped_step_id] = StepStatus.SKIPPED

    pending_block = [skipped_step_id]
    blocked: set[str] = set()
    while pending_block:
        current = pending_block.pop()
        for dependent in dependents_of(definition, current):
            if new_states.get(dependent) not in (StepStatus.PASSED, StepStatus.SKIPPED):
                if dependent not in blocked:
                    blocked.add(dependent)
                    pending_block.append(dependent)
    for step_id in blocked:
        new_states[step_id] = StepStatus.BLOCKED
    return new_states
