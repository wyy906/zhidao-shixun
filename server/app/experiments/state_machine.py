"""步骤状态转换规则（纯函数领域规则，V2-07 前不涉及 AI）。

接口分层（第三轮复审后明确）：
- 私有低层原语 `_transition()`：仅做 TRANSITIONS 表级合法性检查，不感知实验定义与依赖；
  仅供本模块内部与纯函数单测使用。
- 四个公开受保护业务入口（引擎与其他调用方的唯一合法途径，均校验完整快照并返回新快照）：
  - start_step(definition, states, step_id)：开始执行（依赖检查 + 状态机）；
  - refresh_ready_steps(definition, states)：解除依赖全部 PASSED 的 BLOCKED 步骤；
  - apply_skip_propagation(definition, states, skipped_step_id)：跳过并原子传播依赖失效；
  - apply_verification_result(definition, states, step_id, verify_outcome)：应用验证结果
    （passed/failed 作用于 IN_PROGRESS；uncertain 不推进）。

业务规则：
- 合法转换表见 TRANSITIONS；passed 与 skipped 是终态，不可再转换。
- 进入 passed / failed 必须携带对应的验证结果；uncertain 永不推进步骤。
- 禁止通过直接改状态文本把步骤标记为 passed。
- 依赖未通过的步骤初始即为 blocked；依赖只有全部 passed 才能开始（skipped 的依赖不视为通过）。
- skipped 的步骤会阻塞其全部直接/间接下游（不能自动视为通过）。
- 所有入口对状态快照做完整性校验：键集必须与实验定义完全一致、值必须是 StepStatus
  成员；非法快照一律拒绝（fail-closed），绝不静默修正。
- 传播操作是原子的：任何下游状态转换非法时整体拒绝，不产生部分修改。
"""

from zhidao_contracts import StepStatus, VerifyOutcome

from app.experiments.models import ExperimentDefinition, StepDefinition

# 当前状态 → 允许的目标状态集合（纯状态机层面；passed/failed 另需验证结果佐证）。
# pending/failed → blocked 用于依赖失效传播（apply_skip_propagation），
# 必须经私有 _transition() 执行（或更高层的公开业务入口），不允许直接改状态字典绕过。
TRANSITIONS: dict[StepStatus, frozenset[StepStatus]] = {
    StepStatus.PENDING: frozenset({StepStatus.IN_PROGRESS, StepStatus.SKIPPED, StepStatus.BLOCKED}),
    StepStatus.BLOCKED: frozenset({StepStatus.PENDING, StepStatus.SKIPPED}),
    StepStatus.IN_PROGRESS: frozenset({StepStatus.PASSED, StepStatus.FAILED, StepStatus.SKIPPED}),
    StepStatus.FAILED: frozenset({StepStatus.IN_PROGRESS, StepStatus.SKIPPED, StepStatus.BLOCKED}),
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


class InvalidStateSnapshot(Exception):
    """状态快照与实验定义不一致（键集不匹配或值非法）。拒绝处理，不静默修正。"""


class DependencyNotSatisfied(Exception):
    """受保护入口的依赖检查未通过。"""

    def __init__(self, step_id: str, unmet: list[str], unmet_states: dict[str, str]):
        detail = "、".join(f"{dep}={unmet_states[dep]}" for dep in unmet)
        super().__init__(f"步骤 {step_id} 的依赖未全部通过：{detail}")
        self.step_id = step_id
        self.unmet = unmet
        self.unmet_states = unmet_states


def _validate_snapshot(definition: ExperimentDefinition, states: dict[str, StepStatus]) -> None:
    """快照完整性校验：键集必须与实验定义完全一致，值必须是 StepStatus 成员。"""
    expected_ids = set(definition.step_map)
    actual_ids = set(states)
    if actual_ids != expected_ids:
        missing = sorted(expected_ids - actual_ids)
        extra = sorted(actual_ids - expected_ids)
        raise InvalidStateSnapshot(
            f"状态快照与实验定义 {definition.experiment_id} 不一致"
            f"（缺少：{missing or '无'}；多余：{extra or '无'}）"
        )
    bad_values = [key for key, value in states.items() if not isinstance(value, StepStatus)]
    if bad_values:
        raise InvalidStateSnapshot(f"状态快照包含非法状态值：{sorted(bad_values)}")


def can_transition(current: StepStatus, target: StepStatus) -> bool:
    """纯状态机层面是否允许（不含验证结果要求）。"""
    return target in TRANSITIONS[current]


def _transition(
    current: StepStatus,
    target: StepStatus,
    *,
    verify_outcome: VerifyOutcome | None = None,
) -> StepStatus:
    """低层转换原语（私有）：仅做表级合法性检查，不感知实验定义与依赖。

    引擎与其他调用方不得使用本函数构造业务流程；必须使用本模块的公开受保护入口
    （start_step / refresh_ready_steps / apply_skip_propagation /
    apply_verification_result），否则无法保证依赖检查与快照完整性。
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


def refresh_ready_steps(
    definition: ExperimentDefinition,
    states: dict[str, StepStatus],
) -> dict[str, StepStatus]:
    """受保护入口：解除已就绪的 BLOCKED 步骤。

    仅当步骤当前为 BLOCKED 且其全部依赖均为 PASSED 时，经状态机（blocked→pending）
    解除为 PENDING。依赖为 skipped/failed/pending/blocked 的步骤不放行。
    非法快照整体拒绝；返回新字典，不修改入参。
    """
    _validate_snapshot(definition, states)
    new_states = dict(states)
    for step in definition.steps:
        if new_states[step.step_id] is StepStatus.BLOCKED and can_start(step, new_states):
            new_states[step.step_id] = _transition(
                new_states[step.step_id], StepStatus.PENDING
            )
    return new_states


def start_step(
    definition: ExperimentDefinition,
    states: dict[str, StepStatus],
    step_id: str,
) -> dict[str, StepStatus]:
    """受保护入口：开始执行一个步骤（唯一的 pending→in_progress 合法途径）。

    - 校验快照完整性（非法快照拒绝）；
    - 步骤必须存在于实验定义中；
    - BLOCKED 步骤：依赖全部 PASSED 时先解除（blocked→pending）再开始，两步均经状态机；
    - 任何依赖为 skipped/failed/pending/blocked：拒绝并指出未满足项；
    - 返回新状态字典，不修改入参。
    """
    _validate_snapshot(definition, states)
    if step_id not in definition.step_map:
        raise InvalidStateSnapshot(f"步骤 {step_id} 不在实验 {definition.experiment_id} 中")

    step = definition.get_step(step_id)
    current = states[step_id]
    unmet = [dep for dep in step.depends_on if states[dep] is not StepStatus.PASSED]
    if unmet:
        raise DependencyNotSatisfied(
            step_id, unmet, {dep: states[dep].value for dep in unmet}
        )

    new_states = dict(states)
    if current is StepStatus.BLOCKED:
        new_states[step_id] = _transition(current, StepStatus.PENDING)
        current = new_states[step_id]
    new_states[step_id] = _transition(current, StepStatus.IN_PROGRESS)
    return new_states


def dependents_of(definition: ExperimentDefinition, step_id: str) -> list[str]:
    """直接依赖 step_id 的步骤（即 step_id 的下游一步）。"""
    return [step.step_id for step in definition.steps if step_id in step.depends_on]


def apply_skip_propagation(
    definition: ExperimentDefinition,
    states: dict[str, StepStatus],
    skipped_step_id: str,
) -> dict[str, StepStatus]:
    """受保护入口：跳过一个步骤并传播依赖失效。

    规则：
    - 目标步骤已处于终态（passed/skipped）→ 拒绝（终态不可再转换，不可重复跳过）；
    - 快照非法 → 整体拒绝；
    - 直接/间接下游中未到达终态的步骤经状态机（pending/blocked/failed→blocked）置为
      blocked；处于 in_progress 的下游无法合法置为 blocked → 整体拒绝（原子性，
      不产生部分修改）；已是终态（passed/skipped）的下游不受影响、不被破坏；
    - 跳过不等于通过：下游永远不会因跳过而自动 passed。
    返回新状态字典（不修改入参）。
    """
    _validate_snapshot(definition, states)
    current = states.get(skipped_step_id)
    if current is None:
        raise InvalidStateSnapshot(f"步骤 {skipped_step_id} 不在实验 {definition.experiment_id} 中")
    if current in (StepStatus.PASSED, StepStatus.SKIPPED):
        raise IllegalTransition(
            current, StepStatus.SKIPPED, "终态步骤不能再被跳过（passed/skipped 均为终态）"
        )

    # 先计算全部需要置为 blocked 的下游，再统一应用（原子性：先全部校验，无异常才写入）
    new_states = dict(states)
    new_states[skipped_step_id] = _transition(current, StepStatus.SKIPPED)

    pending_visit = [skipped_step_id]
    visited: set[str] = set()
    to_block: list[str] = []
    while pending_visit:
        node = pending_visit.pop()
        for dependent in dependents_of(definition, node):
            if dependent in visited:
                continue
            visited.add(dependent)
            dependent_state = new_states[dependent]
            if dependent_state is StepStatus.IN_PROGRESS:
                raise IllegalTransition(
                    dependent_state,
                    StepStatus.BLOCKED,
                    f"下游步骤 {dependent} 正在执行，不能被依赖失效传播改为 blocked；"
                    "请先完成、失败或跳过该步骤后重试",
                )
            pending_visit.append(dependent)
            if dependent_state not in (StepStatus.PASSED, StepStatus.SKIPPED):
                to_block.append(dependent)

    for step_id in to_block:
        if new_states[step_id] is not StepStatus.BLOCKED:
            new_states[step_id] = _transition(new_states[step_id], StepStatus.BLOCKED)
    return new_states


def apply_verification_result(
    definition: ExperimentDefinition,
    states: dict[str, StepStatus],
    step_id: str,
    verify_outcome: VerifyOutcome,
) -> dict[str, StepStatus]:
    """受保护入口：把一个验证结果应用到指定步骤（passed/failed 推进，uncertain 不推进）。

    规则：
    - 快照必须完整合法；步骤必须存在于实验定义中；
    - PASSED / FAILED：当前步骤必须为 IN_PROGRESS（未开始或已结束的步骤不接受验证结果），
      并经状态机转换为对应终态；
    - UNCERTAIN：不改变状态、不推进步骤（返回原快照的副本）；
    - 始终返回新状态快照，不修改入参。
    """
    _validate_snapshot(definition, states)
    if step_id not in definition.step_map:
        raise InvalidStateSnapshot(f"步骤 {step_id} 不在实验 {definition.experiment_id} 中")

    current = states[step_id]

    if verify_outcome is VerifyOutcome.UNCERTAIN:
        return dict(states)  # uncertain 不推进：返回原快照副本

    target = StepStatus.PASSED if verify_outcome is VerifyOutcome.PASSED else StepStatus.FAILED
    if current is not StepStatus.IN_PROGRESS:
        raise IllegalTransition(
            current,
            target,
            "验证结果只能作用于正在执行的步骤（当前状态必须为 IN_PROGRESS）",
        )

    new_states = dict(states)
    new_states[step_id] = _transition(current, target, verify_outcome=verify_outcome)
    return new_states
