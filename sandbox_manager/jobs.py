"""任务队列：并发上限、排队上限、任务状态与取消（内存态）

注意：管理器重启会丢失任务记录。业务后端查询不存在的 job 会得到 404 →
按“沙箱不可用”安全失败，绝不会把未完成任务当成成功。

队列策略：
  - 固定 `max_concurrent` 个 daemon 工作线程，排队任务只进内部 deque；
  - 内部排队长度（尚未开始执行）不得超过 `max_pending`，超限立即 queue_full；
  - 取消排队任务会**从内部队列移除**，不会在队列中留下占位项；
  - 被拒绝的请求不创建任务记录、不启动线程、不创建容器；
  - 执行器返回的结果会先做结构校验，畸形结果一律落为 failed/internal_error。
"""
from __future__ import annotations

import logging
import threading
import time
import uuid
from collections import deque
from typing import Any

from .container_spec import SandboxLimits
from .runner import SandboxError

logger = logging.getLogger(__name__)

JOB_TTL_SECONDS = 3600
JOB_MAX_KEPT = 1000

SAFE_JOB_FAILED_MESSAGE = "任务执行环境内部错误，任务已安全终止。"

TERMINAL_STATUSES = {
    "succeeded", "failed", "timeout", "resource_exceeded", "cancelled",
}


class QueueFullError(RuntimeError):
    """排队任务已达到上限"""

    code = "queue_full"


def _validate_result(result: Any) -> dict:
    """校验执行器返回的任务结果，拒绝畸形结构

    严格类型判断（bool 是 int 子类，因此必须用 `type(...) is int`）：
      - status 必须是终态字符串；
      - stdout / stderr 必须是字符串；
      - exit_code / duration_ms 必须是严格 int（duration 非负）或 None；
      - error_code / error_message 必须是字符串或 None。
    """
    if not isinstance(result, dict):
        raise ValueError("job result must be an object")
    status = result.get("status")
    if not isinstance(status, str) or status not in TERMINAL_STATUSES:
        raise ValueError(f"unexpected job status: {status!r}")

    normalized = dict(result)
    for field in ("stdout", "stderr"):
        value = normalized.get(field, "")
        if type(value) is not str:
            raise ValueError(f"{field} must be a string")
        normalized[field] = value

    exit_code = normalized.get("exit_code")
    if exit_code is not None and type(exit_code) is not int:
        raise ValueError("exit_code must be an integer or null")

    duration = normalized.get("duration_ms")
    if duration is not None and (type(duration) is not int or duration < 0):
        raise ValueError("duration_ms must be a non-negative integer or null")

    for field in ("error_code", "error_message"):
        value = normalized.get(field)
        if value is not None and type(value) is not str:
            raise ValueError(f"{field} must be a string or null")

    if status != "succeeded" and not normalized.get("stderr"):
        normalized["stderr"] = SAFE_JOB_FAILED_MESSAGE
    return normalized


class JobStore:
    def __init__(self, runner: Any, limits: SandboxLimits):
        self._runner = runner
        self._limits = limits
        self._jobs: dict[str, dict] = {}
        # 内部待执行队列：长度即排队任务数，取消时直接移除，不会累积占位项
        self._queue: deque[tuple[dict, str, int]] = deque()
        self._lock = threading.Lock()
        self._cv = threading.Condition(self._lock)
        self._closed = False
        self._workers = [
            threading.Thread(target=self._worker, name=f"zd-sandbox-{i}", daemon=True)
            for i in range(limits.max_concurrent)
        ]
        for worker in self._workers:
            worker.start()

    # ------------------------------------------------------------------
    def submit(self, code: str, timeout: int) -> dict:
        with self._cv:
            self._prune_locked()
            if len(self._queue) >= self._limits.max_pending:
                raise QueueFullError("sandbox queue is full")
            job_id = uuid.uuid4().hex
            job = {
                "job_id": job_id,
                "status": "queued",
                "stdout": "",
                "stderr": "",
                "exit_code": None,
                "duration_ms": None,
                "error_code": None,
                "error_message": None,
                "created_at": time.time(),
                "cancel_event": threading.Event(),
            }
            self._jobs[job_id] = job
            self._queue.append((job, code, timeout))
            self._cv.notify()
        return self._public(job)

    def get(self, job_id: str) -> dict | None:
        with self._lock:
            job = self._jobs.get(job_id)
            return self._public(job) if job else None

    def cancel(self, job_id: str) -> dict | None:
        with self._cv:
            job = self._jobs.get(job_id)
            if job is None:
                return None
            job["cancel_event"].set()
            if job["status"] == "queued":
                # 真正从内部队列移除，释放排队容量
                self._queue = deque(item for item in self._queue if item[0] is not job)
                job["status"] = "cancelled"
                job["exit_code"] = -1
                job["duration_ms"] = 0
                job["stderr"] = "任务已取消。"
            return self._public(job)

    def close(self) -> None:
        """停止工作线程（测试/进程退出时使用）"""
        with self._cv:
            self._closed = True
            self._cv.notify_all()

    # ------------------------------------------------------------------
    def _worker(self) -> None:
        while True:
            with self._cv:
                while not self._queue and not self._closed:
                    self._cv.wait()
                if self._closed:
                    return
                job, code, timeout = self._queue.popleft()
                if job["cancel_event"].is_set():
                    continue
                job["status"] = "running"
            self._run(job, code, timeout)

    def _run(self, job: dict, code: str, timeout: int) -> None:
        try:
            result = self._runner.run_job(
                code, timeout, job["cancel_event"], job["job_id"]
            )
            self._finish(job, _validate_result(result))
        except SandboxError as exc:
            # 内部细节只写服务端日志，不通过接口返回
            logger.warning("沙箱任务失败 %s: %s: %s", job["job_id"], exc.code, exc)
            self._finish(job, {
                "status": "failed",
                "stdout": "",
                "stderr": SAFE_JOB_FAILED_MESSAGE,
                "exit_code": -1,
                "duration_ms": None,
                "error_code": exc.code,
                "error_message": SAFE_JOB_FAILED_MESSAGE,
            })
        except ValueError as exc:
            logger.error("执行器返回畸形结果 %s: %s", job["job_id"], exc)
            self._finish(job, {
                "status": "failed",
                "stdout": "",
                "stderr": SAFE_JOB_FAILED_MESSAGE,
                "exit_code": -1,
                "duration_ms": None,
                "error_code": "internal_error",
                "error_message": SAFE_JOB_FAILED_MESSAGE,
            })
        except Exception:  # 防御性兜底
            logger.exception("沙箱任务异常 %s", job["job_id"])
            self._finish(job, {
                "status": "failed",
                "stdout": "",
                "stderr": SAFE_JOB_FAILED_MESSAGE,
                "exit_code": -1,
                "duration_ms": None,
                "error_code": "internal_error",
                "error_message": SAFE_JOB_FAILED_MESSAGE,
            })

    def _finish(self, job: dict, result: dict) -> None:
        with self._lock:
            job["status"] = result["status"]
            job["stdout"] = result["stdout"]
            job["stderr"] = result["stderr"]
            job["exit_code"] = result.get("exit_code")
            job["duration_ms"] = result.get("duration_ms")
            job["error_code"] = result.get("error_code")
            job["error_message"] = result.get("error_message")

    # ------------------------------------------------------------------
    @staticmethod
    def _public(job: dict) -> dict:
        return {k: v for k, v in job.items() if k != "cancel_event"}

    def _prune_locked(self) -> None:
        now = time.time()
        expired = [
            jid for jid, job in self._jobs.items()
            if job["status"] not in {"queued", "running"}
            and now - job["created_at"] > JOB_TTL_SECONDS
        ]
        for jid in expired:
            self._jobs.pop(jid, None)
        if len(self._jobs) > JOB_MAX_KEPT:
            finished = sorted(
                (jid for jid, job in self._jobs.items()
                 if job["status"] not in {"queued", "running"}),
                key=lambda jid: self._jobs[jid]["created_at"],
            )
            for jid in finished[: len(self._jobs) - JOB_MAX_KEPT]:
                self._jobs.pop(jid, None)
