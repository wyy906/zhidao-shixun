"""任务队列：并发上限、排队上限、任务状态与取消（内存态）

注意：管理器重启会丢失任务记录。业务后端查询不存在的 job 会得到 404 →
按“沙箱不可用”安全失败，绝不会把未完成任务当成成功。

队列策略：
  - ThreadPoolExecutor 固定 max_concurrent 个执行线程，不再为每个排队任务创建线程；
  - 排队任务数（尚未开始执行）不得超过 max_pending，超限立即返回 queue_full；
  - 被拒绝的请求不创建任务记录、不启动线程、不创建容器。
"""
from __future__ import annotations

import logging
import threading
import time
import uuid
from concurrent.futures import ThreadPoolExecutor
from typing import Any

from .container_spec import SandboxLimits
from .runner import SandboxError

logger = logging.getLogger(__name__)

JOB_TTL_SECONDS = 3600
JOB_MAX_KEPT = 1000

SAFE_JOB_FAILED_MESSAGE = "任务执行环境内部错误，任务已安全终止。"


class QueueFullError(RuntimeError):
    """排队任务已达到上限"""

    code = "queue_full"


class JobStore:
    def __init__(self, runner: Any, limits: SandboxLimits):
        self._runner = runner
        self._limits = limits
        self._jobs: dict[str, dict] = {}
        self._lock = threading.Lock()
        # 正在执行的线程数固定；排队任务只占队列，不占线程
        self._executor = ThreadPoolExecutor(
            max_workers=limits.max_concurrent,
            thread_name_prefix="zd-sandbox",
        )
        # 仅统计“已提交但尚未开始执行”的任务
        self._pending = 0

    # ------------------------------------------------------------------
    def submit(self, code: str, timeout: int) -> dict:
        with self._lock:
            self._prune_locked()
            if self._pending >= self._limits.max_pending:
                raise QueueFullError("sandbox queue is full")
            self._pending += 1
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
                "capacity_released": False,
            }
            self._jobs[job_id] = job

        try:
            self._executor.submit(self._execute, job, code, timeout)
        except RuntimeError:
            # 执行器已关闭等极端情况：撤回任务与容量占用
            with self._lock:
                self._jobs.pop(job_id, None)
                if not job["capacity_released"]:
                    job["capacity_released"] = True
                    self._pending -= 1
            raise
        return self._public(job)

    def get(self, job_id: str) -> dict | None:
        with self._lock:
            job = self._jobs.get(job_id)
            return self._public(job) if job else None

    def cancel(self, job_id: str) -> dict | None:
        with self._lock:
            job = self._jobs.get(job_id)
            if job is None:
                return None
            job["cancel_event"].set()
            if job["status"] == "queued":
                job["status"] = "cancelled"
                job["exit_code"] = -1
                job["duration_ms"] = 0
                job["stderr"] = "任务已取消。"
                self._release_capacity_locked(job)
            return self._public(job)

    # ------------------------------------------------------------------
    def _release_capacity_locked(self, job: dict) -> None:
        """释放排队容量（幂等），确保取消 / 开始执行 / 拒绝都只释放一次"""
        if not job.get("capacity_released", False):
            job["capacity_released"] = True
            self._pending = max(0, self._pending - 1)

    def _execute(self, job: dict, code: str, timeout: int) -> None:
        with self._lock:
            self._release_capacity_locked(job)
            if job["cancel_event"].is_set() or job["status"] == "cancelled":
                return
            job["status"] = "running"
        try:
            result = self._runner.run_job(
                code, timeout, job["cancel_event"], job["job_id"]
            )
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
            return
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
            return
        self._finish(job, result)

    def _finish(self, job: dict, result: dict) -> None:
        with self._lock:
            job["status"] = result.get("status", "failed")
            job["stdout"] = result.get("stdout", "")
            job["stderr"] = result.get("stderr", "")
            job["exit_code"] = result.get("exit_code")
            job["duration_ms"] = result.get("duration_ms")
            job["error_code"] = result.get("error_code")
            job["error_message"] = result.get("error_message")

    # ------------------------------------------------------------------
    @staticmethod
    def _public(job: dict) -> dict:
        return {
            k: v for k, v in job.items()
            if k not in {"cancel_event", "capacity_released"}
        }

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
