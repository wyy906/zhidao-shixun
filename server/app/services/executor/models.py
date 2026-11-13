"""执行器核心数据模型（V2-04B 阶段 B）。

- ExecutionTask：把一次执行请求与用户/实验/任务关联，便于执行记录追溯。
- ExecutionOutcome：结构化执行结论。status 三态 completed/timeout/error；
  Docker 层异常绝不能伪装成 Python 运行异常，实验验证结果另由验证器判定，
  与执行结果严格分离（阶段 B 任务书 §5）。
"""

from dataclasses import dataclass
from enum import Enum
from typing import Literal

from app.services.executor.base import (
    ExecutionRequest,
    ExecutionResult,
    UnsafeExecutionRequest,
)


class FailureKind(str, Enum):
    """执行失败分类（不与 Python 运行失败混淆——后者只是 exit_code != 0 的 completed）。"""

    DOCKER_UNAVAILABLE = "docker_unavailable"
    IMAGE_DIGEST_NOT_LOCKED = "image_digest_not_locked"
    IMAGE_DIGEST_MISMATCH = "image_digest_mismatch"
    IMAGE_NOT_FOUND = "image_not_found"
    CONTAINER_CREATE_FAILED = "container_create_failed"
    CONTAINER_START_FAILED = "container_start_failed"
    EXECUTION_INTERNAL_ERROR = "execution_internal_error"


@dataclass(frozen=True)
class ExecutionTask:
    """一次受控执行任务（用户/实验/任务关联）。"""

    user_id: str
    experiment_id: str
    task_id: str
    request: ExecutionRequest

    def __post_init__(self) -> None:
        if not self.user_id.strip():
            raise UnsafeExecutionRequest("user_id 不能为空")
        if not self.experiment_id.strip():
            raise UnsafeExecutionRequest("experiment_id 不能为空")
        if not self.task_id.strip():
            raise UnsafeExecutionRequest("task_id 不能为空")


@dataclass(frozen=True)
class ExecutionOutcome:
    """结构化执行结论。

    - completed：容器生命周期正常结束，exit_code/stdout/stderr 可信
      （exit_code != 0 表示 Python 层失败，不是执行器错误）。
    - timeout：超时被终止。timed_out=True 且 exit_code 可能为 None，
      绝不伪装成普通非零退出码。
    - error：执行器/基础设施失败（Docker 层），result 必为 None，
      绝不伪装成 Python 运行结果。
    """

    task: ExecutionTask
    status: Literal["completed", "timeout", "error"]
    result: ExecutionResult | None = None
    failure_kind: FailureKind | None = None
    failure_detail: str = ""
    container_id: str | None = None
    duration_ms: int | None = None

    def __post_init__(self) -> None:
        if self.status == "completed":
            if self.result is None or self.result.timed_out:
                raise ValueError("completed 必须携带未超时的 result")
            if self.failure_kind is not None:
                raise ValueError("completed 不得携带 failure_kind")
        elif self.status == "timeout":
            if self.result is None or not self.result.timed_out:
                raise ValueError("timeout 必须携带 timed_out=True 的 result")
            if self.failure_kind is not None:
                raise ValueError("timeout 不得携带 failure_kind")
        else:
            if self.result is not None:
                raise ValueError("error 不得携带 result（不得伪装成运行结果）")
            if self.failure_kind is None:
                raise ValueError("error 必须携带 failure_kind")
