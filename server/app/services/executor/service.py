"""Docker 隔离执行服务核心（V2-04B 阶段 B）。

职责：把一次 ExecutionTask 变成结构化 ExecutionOutcome。
- Docker Engine 不可用 → DOCKER_UNAVAILABLE，fail-closed，绝不回退宿主机执行；
- 镜像 digest 未锁定或与批准值不符 → fail-closed（executor_image_lock.json
  approval_status=pending 时本服务拒绝一切执行）；
- 代码经命令向量传入容器（["python","-I","-u","-c",code]），无 shell 拼接、
  无宿主机临时文件、无 bind mount；
- 输出截断与超时判定集中在本层；
- 不把 Docker 异常伪装成 Python 运行异常，不把超时伪装成普通退出码。
"""

import time

from app.services.executor.base import (
    DockerSandboxConfig,
    DockerUnavailableError,
    ExecutorError,
)
from app.services.executor.driver import ContainerDriver, ContainerSpec
from app.services.executor.models import ExecutionOutcome, ExecutionTask, FailureKind


class SandboxExecutionService:
    """面向任务模型的执行服务。driver 可注入（单元测试用 Fake 实现）。"""

    def __init__(
        self,
        driver: ContainerDriver,
        config: DockerSandboxConfig | None = None,
        expected_digest: str | None = None,
    ) -> None:
        self._driver = driver
        self._config = config or DockerSandboxConfig()
        self._expected_digest = expected_digest

    def execute(self, task: ExecutionTask) -> ExecutionOutcome:
        started = time.perf_counter()
        outcome = self._execute_inner(task)
        duration_ms = int((time.perf_counter() - started) * 1000)
        return ExecutionOutcome(
            task=outcome.task,
            status=outcome.status,
            result=outcome.result,
            failure_kind=outcome.failure_kind,
            failure_detail=outcome.failure_detail,
            container_id=outcome.container_id,
            duration_ms=duration_ms,
        )

    def _execute_inner(self, task: ExecutionTask) -> ExecutionOutcome:
        # 1) Engine 探测：不可用即 fail-closed。
        engine = self._driver.engine_info()
        if not engine:
            return self._error(
                task,
                FailureKind.DOCKER_UNAVAILABLE,
                "Docker Engine 不可用或连接失败；按 D-1 决策不提供宿主机回退执行。",
            )

        # 2) 镜像 digest 门禁：未锁定即拒绝（镜像锁定文件当前 pending/null）。
        if not self._expected_digest:
            return self._error(
                task,
                FailureKind.IMAGE_DIGEST_NOT_LOCKED,
                "执行镜像 digest 未锁定（executor_image_lock.json approval_status=pending）"
                "；fail-closed，拒绝一切执行。",
            )
        actual = self._driver.image_digest(self._config.image)
        if actual is None:
            return self._error(
                task,
                FailureKind.IMAGE_NOT_FOUND,
                f"镜像 {self._config.image} 不存在或无 RepoDigest。",
            )
        if actual != self._expected_digest:
            return self._error(
                task,
                FailureKind.IMAGE_DIGEST_MISMATCH,
                f"镜像 digest 与批准值不符：actual={actual} expected={self._expected_digest}。",
            )

        # 3) 构建固定安全参数的容器规格并执行。
        spec = self._build_spec(task)
        try:
            run = self._driver.run(spec)
        except ExecutorError as exc:
            return self._error(task, FailureKind.EXECUTION_INTERNAL_ERROR, f"执行器错误：{exc}")
        except Exception as exc:  # noqa: BLE001
            return self._error(
                task,
                FailureKind.EXECUTION_INTERNAL_ERROR,
                f"容器运行异常（不伪装成 Python 运行结果）：{exc!r}",
            )

        # 4) 输出截断与解码。
        limit = self._config.max_output_bytes
        stdout_b = run.stdout[:limit]
        stderr_b = run.stderr[:limit]
        truncated = len(run.stdout) > limit or len(run.stderr) > limit
        result = _make_result(
            exit_code=run.exit_code,
            stdout_bytes=stdout_b,
            stderr_bytes=stderr_b,
            timed_out=run.timed_out,
            truncated=truncated,
        )
        if run.timed_out:
            return ExecutionOutcome(
                task=task, status="timeout", result=result,
                container_id=run.container_id,
            )
        return ExecutionOutcome(
            task=task, status="completed", result=result,
            container_id=run.container_id,
        )

    def _build_spec(self, task: ExecutionTask) -> ContainerSpec:
        """由服务端固定生成容器规格；用户请求只提供 code，无任何容器参数注入面。"""
        return ContainerSpec(
            image_ref=self._config.image,
            command=("python", "-I", "-u", "-c", task.request.code),
            user=self._config.non_root_user,
            timeout_seconds=task.request.timeout_seconds,
            mem_limit=self._config.mem_limit,
            cpus=self._config.cpus,
            pids_limit=self._config.pids_limit,
        )

    @staticmethod
    def _error(task: ExecutionTask, kind: FailureKind, detail: str) -> ExecutionOutcome:
        return ExecutionOutcome(task=task, status="error", failure_kind=kind, failure_detail=detail)


def _make_result(exit_code: int | None, stdout_bytes: bytes, stderr_bytes: bytes,
                 timed_out: bool, truncated: bool):
    from app.services.executor.base import ExecutionResult

    return ExecutionResult(
        exit_code=exit_code,
        stdout=stdout_bytes.decode("utf-8", errors="replace"),
        stderr=stderr_bytes.decode("utf-8", errors="replace"),
        timed_out=timed_out,
        truncated=truncated,
    )
