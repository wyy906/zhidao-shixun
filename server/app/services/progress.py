"""步骤进度服务（V2-04E1）：把运行结果接入验证器判定与状态机推进。

核心闭环（真实产品语义，不伪装）：
- 学生提交某步骤代码 → 经执行服务真实运行 → 用该步骤的验证器（白名单受控实现）
  对真实运行结果求值（passed/failed/uncertain 三态）→ 经状态机受保护入口推进；
- uncertain（超时、验证器未实现、求值异常等）永不推进步骤；
- 基础设施失败（Docker 未就绪等）直接以明确错误抛出，状态不变；
- 会话为进程内存态（开发/受控测试模式；服务重启即重置，如实标注，不冒充持久化）。
"""

from app.core.errors import AppError
from app.experiments.models import ExperimentDefinition
from app.experiments.state_machine import (
    DependencyNotSatisfied,
    IllegalTransition,
    compute_initial_states,
    refresh_ready_steps,
    start_step,
    apply_verification_result,
)
from app.experiments.verifiers.registry import evaluate_verifier
from app.services.executor.client import ExecutionSubmission
from zhidao_contracts import StepStatus

from app.api.v1.executions import DEV_USER_ID, submit_execution


class StepProgressService:
    """实验步骤进度会话（按 experiment_id 隔离；开发模式单用户）。"""

    def __init__(self) -> None:
        self._sessions: dict[str, dict[str, StepStatus]] = {}

    def states_view(self, definition: ExperimentDefinition) -> dict[str, str]:
        """当前状态视图（无会话时返回初始状态视图，不落存储）。"""
        states = self._sessions.get(definition.experiment_id)
        if states is None:
            states = compute_initial_states(definition)
        return {step_id: status.value for step_id, status in states.items()}

    def reset(self, definition: ExperimentDefinition) -> dict[str, str]:
        self._sessions.pop(definition.experiment_id, None)
        return self.states_view(definition)

    def submit_step(
        self,
        definition: ExperimentDefinition,
        step_id: str,
        code: str,
        task_id: str,
        client,
        timeout_seconds: int = 10,
    ) -> dict:
        """运行指定步骤代码并用其验证器判定、推进状态。"""
        if step_id not in definition.step_map:
            raise AppError(
                code="step_not_found",
                message=f"步骤 {step_id} 不在实验 {definition.experiment_id} 中。",
                status_code=404,
            )
        step = definition.get_step(step_id)

        # 1. 真实运行（基础设施失败/未就绪 → 明确错误，状态不变）
        payload = submit_execution(
            client,
            ExecutionSubmission(
                user_id=DEV_USER_ID,
                experiment_id=definition.experiment_id,
                task_id=task_id,
                language="python",
                code=code,
                timeout_seconds=timeout_seconds,
            ),
        )
        run_result = {
            "execution_id": payload.get("record_id"),
            "status": payload.get("status"),
            "exit_code": payload.get("exit_code"),
            "stdout": payload.get("stdout", ""),
            "stderr": payload.get("stderr", ""),
            "timed_out": bool(payload.get("timed_out")),
            "truncated": bool(payload.get("truncated")),
            "duration_ms": payload.get("duration_ms"),
        }

        # 2. 验证器判定（白名单受控实现；uncertain 永不推进）
        actual = {"exit_code": payload.get("exit_code"), "stdout": payload.get("stdout", "")}
        verify = evaluate_verifier(
            step.verifier.type, step.verifier.params, actual, step_id=step_id
        )

        states = self._sessions.get(definition.experiment_id)
        if states is None:
            states = compute_initial_states(definition)

        if verify.outcome.value == "uncertain":
            # 不推进：如实返回当前状态与判定反馈
            return self._response(definition, states, step_id, run_result, verify, progressed=False)

        # 3. 状态机受保护入口推进
        current = states[step_id]
        if current is StepStatus.IN_PROGRESS:
            new_states = dict(states)
        else:
            try:
                new_states = start_step(definition, states, step_id)
            except DependencyNotSatisfied as exc:
                raise AppError(
                    code="dependencies_not_satisfied",
                    message=str(exc),
                    status_code=409,
                ) from exc
            except IllegalTransition as exc:
                raise AppError(
                    code="step_already_terminal",
                    message=str(exc),
                    status_code=409,
                ) from exc
        try:
            new_states = apply_verification_result(definition, new_states, step_id, verify.outcome)
            new_states = refresh_ready_steps(definition, new_states)
        except IllegalTransition as exc:
            raise AppError(
                code="step_already_terminal",
                message=str(exc),
                status_code=409,
            ) from exc

        self._sessions[definition.experiment_id] = new_states
        return self._response(definition, new_states, step_id, run_result, verify, progressed=True)

    def _response(
        self,
        definition: ExperimentDefinition,
        states: dict[str, StepStatus],
        step_id: str,
        run_result: dict,
        verify,
        *,
        progressed: bool,
    ) -> dict:
        return {
            "run": run_result,
            "verify": {
                "outcome": verify.outcome.value,
                "confidence": verify.confidence,
                "feedback": verify.feedback,
                "evidence": verify.evidence,
            },
            "step_status": states[step_id].value,
            "states": {sid: status.value for sid, status in states.items()},
            "progressed": progressed,
            "note": "进度为进程内存态，服务重启后重置（开发/受控测试模式）",
        }
