"""任务队列：并发上限、任务状态与取消（内存态）

注意：管理器重启会丢失任务记录。业务后端查询不存在的 job 会得到 404 →
按“沙箱不可用”安全失败，绝不会把未完成任务当成成功。
"""
from __future__ import annotations

import logging
import threading
import time
import uuid
from typing import Any

from .container_spec import SandboxLimits
from .runner import SandboxError

logger = logging.getLogger(__name__)

JOB_TTL_SECONDS = 3600
JOB_MAX_KEPT = 1000


class JobStore:
    def __init__(self, runner: Any, limits: SandboxLimits):
        self._runner = runner
        self._limits = limits
        self._jobs: dict[str, dict] = {}
        self._lock = threading.Lock()
        # 同时执行任务上限（排队中的任务占用线程但不占 CPU）
        self._slots = threading.BoundedSemaphore(limits.max_concurrent)

    # ------------------------------------------------------------------
    def submit(self, code: str, timeout: int) -> dict:
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
        with self._lock:
            self._prune_locked()
            self._jobs[job_id] = job
        threading.Thread(
            target=self._execute, args=(job, code, timeout), daemon=True
        ).start()
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
            return self._public(job)

    # ------------------------------------------------------------------
    def _execute(self, job: dict, code: str, timeout: int) -> None:
        with self._slots:
            if job["cancel_event"].is_set():
                return  # 排队期间已被取消
            with self._lock:
                job["status"] = "running"
            try:
                result = self._runner.run_job(code, timeout, job["cancel_event"])
            except SandboxError as exc:
                logger.warning("沙箱任务失败 %s: %s", job["job_id"], exc.code)
                self._finish(job, {
                    "status": "failed",
                    "stdout": "",
                    "stderr": "代码执行环境内部错误，任务已安全终止。",
                    "exit_code": -1,
                    "duration_ms": None,
                    "error_code": exc.code,
                    "error_message": str(exc),
                })
                return
            except Exception as exc:  # 防御性兜底
                logger.exception("沙箱任务异常 %s", job["job_id"])
                self._finish(job, {
                    "status": "failed",
                    "stdout": "",
                    "stderr": "代码执行环境内部错误，任务已安全终止。",
                    "exit_code": -1,
                    "duration_ms": None,
                    "error_code": "internal_error",
                    "error_message": str(exc)[:255],
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
