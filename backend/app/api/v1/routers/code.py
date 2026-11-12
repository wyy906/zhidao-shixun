"""网页端代码运行接口（沙箱版）

学生在网页编辑器里写的 Python 代码**不会**在业务后端进程内执行，也不会作为
本机 subprocess 运行。调用链为：

    POST /code/run
      → 业务后端校验身份 / 代码长度 / 超时上限
      → 创建 CodeTask（关联 user_id，状态 queued）
      → 转发给独立 Linux 执行节点上的沙箱管理器
      → 沙箱管理器在一次性 Docker 容器中执行（禁网、只读根文件系统、资源限额）
      → 业务后端轮询结果并返回兼容的 CodeRunOut

安全约定：
  - 沙箱不可用 / 未配置 / 认证失败 → 一律 503，**绝不回退本机执行**；
  - 超时、资源超限、取消都终止整个容器（含子进程）；
  - 学生不能通过请求参数提高超时或其他资源限制；
  - 面向学生的错误信息不包含服务器路径、Docker 细节或密钥。
"""
from __future__ import annotations

import asyncio
import logging
import threading
import time
import uuid
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, ConfigDict
from sqlalchemy.orm import Session

from app.api.deps import get_current_user
from app.core.config import settings
from app.db.session import get_db
from app.models import CodeTask, User
from app.services.sandbox_client import (
    SAFE_UNAVAILABLE_MESSAGE,
    SandboxBadResponse,
    SandboxClient,
    SandboxUnavailable,
    get_sandbox_client,
)

logger = logging.getLogger(__name__)

router = APIRouter()

TERMINAL_STATUSES = {
    "succeeded", "failed", "timeout", "resource_exceeded", "cancelled",
}
PENDING_STATUSES = {"queued", "running"}

SAFE_BUSY_MESSAGE = "当前代码运行请求过多，请稍后重试。"
SAFE_FAILED_MESSAGE = "代码执行失败，请检查代码后重试。"


class ConcurrencyGuard:
    """进程内并发保护：全局 + 每用户上限

    学生提交是长等待请求，如果不限制并发，线程/事件循环会被大量同步等待占满。
    超限直接返回 429，不创建任务、不调用沙箱。
    """

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._global = 0
        self._per_user: dict[int, int] = {}

    def try_acquire(self, user_id: int, global_max: int, per_user_max: int) -> bool:
        with self._lock:
            if self._global >= global_max:
                return False
            if self._per_user.get(user_id, 0) >= per_user_max:
                return False
            self._global += 1
            self._per_user[user_id] = self._per_user.get(user_id, 0) + 1
            return True

    def release(self, user_id: int) -> None:
        with self._lock:
            self._global = max(0, self._global - 1)
            current = self._per_user.get(user_id, 0) - 1
            if current > 0:
                self._per_user[user_id] = current
            else:
                self._per_user.pop(user_id, None)

    def reset(self) -> None:
        with self._lock:
            self._global = 0
            self._per_user.clear()


guard = ConcurrencyGuard()


class CodeRunIn(BaseModel):
    # 禁止学生传入镜像、网络模式、资源限制等额外字段（只能由管理员配置）
    model_config = ConfigDict(extra="forbid")

    code: str
    # 兼容旧前端：仍接受该字段，但会被管理员配置的上限压紧，学生无法提高
    timeout: int = 10


class CodeRunOut(BaseModel):
    stdout: str
    stderr: str
    exit_code: int
    duration_ms: int
    timed_out: bool = False
    # 新增字段（向后兼容）：任务 ID，可用于 GET /code/tasks/{task_id} 复查
    task_id: str | None = None
    status: str = "succeeded"


class CodeTaskOut(BaseModel):
    task_id: str
    status: str
    stdout: str
    stderr: str
    exit_code: int | None = None
    duration_ms: int | None = None
    error_code: str | None = None
    error_message: str | None = None
    timeout_seconds: int
    created_at: datetime | None = None
    finished_at: datetime | None = None


def _clip(text: str, limit: int) -> str:
    """按 UTF-8 字节数截断输出，避免巨量输出拖垮前端"""
    text = text or ""
    raw = text.encode("utf-8", "replace")
    if len(raw) <= limit:
        return text
    return raw[:limit].decode("utf-8", "ignore") + "\n…（输出过长，已截断）"


def _result_to_response(task: CodeTask, result: dict) -> CodeRunOut:
    status = result.get("status") or "failed"
    stdout = _clip(result.get("stdout") or "", settings.code_max_output_bytes)
    stderr = _clip(result.get("stderr") or "", settings.code_max_output_bytes)
    exit_code = result.get("exit_code")
    if not isinstance(exit_code, int):
        exit_code = -1

    if status == "timeout":
        timed_out = True
        if not stderr:
            stderr = "运行超时，任务已被终止。"
    elif status == "resource_exceeded":
        timed_out = False
        if not stderr:
            stderr = "资源使用超过限制（内存/进程/磁盘/输出），任务已被终止。"
    elif status == "cancelled":
        timed_out = False
        stderr = stderr or "任务已取消。"
    elif status == "succeeded":
        timed_out = False
    else:
        timed_out = False
        if not stderr:
            stderr = "代码执行失败。"

    return CodeRunOut(
        stdout=stdout,
        stderr=stderr,
        exit_code=exit_code,
        duration_ms=int(result.get("duration_ms") or 0),
        timed_out=timed_out,
        task_id=task.id,
        status=status,
    )


def _save_result(db: Session, task: CodeTask, result: dict) -> None:
    task.status = result.get("status") or "failed"
    task.stdout = _clip(result.get("stdout") or "", settings.code_max_output_bytes)
    task.stderr = _clip(result.get("stderr") or "", settings.code_max_output_bytes)
    exit_code = result.get("exit_code")
    task.exit_code = exit_code if isinstance(exit_code, int) else -1
    duration_ms = result.get("duration_ms")
    task.duration_ms = duration_ms if isinstance(duration_ms, int) else None
    task.error_code = result.get("error_code")
    task.error_message = (result.get("error_message") or "")[:255] or None
    task.finished_at = datetime.utcnow()
    db.commit()


def _fail_task(db: Session, task: CodeTask, error_code: str, message: str) -> None:
    task.status = "failed"
    task.error_code = error_code
    task.error_message = message[:255]
    task.stderr = SAFE_UNAVAILABLE_MESSAGE
    task.finished_at = datetime.utcnow()
    db.commit()


def _raise_unavailable() -> None:
    raise HTTPException(status_code=503, detail=SAFE_UNAVAILABLE_MESSAGE)


def _validate_job_result(result: dict) -> dict:
    """校验管理器返回的任务结构；畸形数据按“不可用”安全失败"""
    status = result.get("status")
    if status not in TERMINAL_STATUSES and status not in PENDING_STATUSES:
        raise SandboxBadResponse(f"unexpected job status: {status!r}")
    for field in ("stdout", "stderr"):
        value = result.get(field)
        if value is not None and not isinstance(value, str):
            raise SandboxBadResponse(f"unexpected {field} type")
    return result


async def _poll_job(sandbox: SandboxClient, job_id: str) -> dict:
    """异步轮询任务，避免阻塞事件循环"""
    started_at = time.monotonic()
    deadline = started_at + settings.sandbox_sync_wait_seconds
    while True:
        result = _validate_job_result(await sandbox.aget_job(job_id))
        if result.get("status") in TERMINAL_STATUSES:
            return result
        if time.monotonic() >= deadline:
            # 超过同步等待上限：取消任务并安全失败，不把未完成任务当成成功
            try:
                await sandbox.acancel(job_id)
            except SandboxUnavailable:
                logger.warning(
                    "无法确认沙箱任务已取消，可能继续运行到管理器超时: %s", job_id
                )
            return {
                "status": "timeout",
                "stdout": "",
                "stderr": "运行超时，任务已被终止。",
                "exit_code": -1,
                "duration_ms": int((time.monotonic() - started_at) * 1000),
                "error_code": "sync_wait_timeout",
            }
        await asyncio.sleep(0.2)


async def _safe_fail(
    db: Session,
    task: CodeTask,
    sandbox: SandboxClient,
    job_id: str,
    error_code: str,
) -> None:
    """异常收口：尽力取消沙箱任务，并把任务落为安全终态

    数据库写入失败时只记录服务端日志，绝不在响应中假称成功。
    """
    if job_id:
        try:
            await sandbox.acancel(job_id)
        except SandboxUnavailable:
            logger.warning("异常收口时取消沙箱任务失败: %s", job_id)
    try:
        db.rollback()
    except Exception:
        logger.exception("异常收口时数据库回滚失败: %s", task.id)
    try:
        _fail_task(db, task, error_code, f"task aborted: {error_code}")
    except Exception:
        logger.exception("异常收口时任务状态落库失败: %s", task.id)


@router.post("/run", response_model=CodeRunOut)
async def run_code(
    data: CodeRunIn,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
    sandbox: SandboxClient = Depends(get_sandbox_client),
):
    """执行一段 Python 代码（同步兼容接口，内部通过独立沙箱执行）"""
    if not settings.code_execution_enabled:
        # 明确关闭时也按“不可用”处理，不降级
        _raise_unavailable()

    code = (data.code or "").strip()
    if not code:
        raise HTTPException(400, "代码不能为空")

    code_bytes = len(code.encode("utf-8"))
    if code_bytes > settings.code_max_input_bytes:
        raise HTTPException(400, f"代码过长（上限 {settings.code_max_input_bytes} 字节）")

    # 学生不能提高上限：请求值只能向下收紧
    requested = int(data.timeout or 0)
    timeout = max(1, min(requested or settings.code_run_timeout_seconds,
                         settings.code_run_timeout_seconds))

    # 并发保护：超限直接拒绝，不创建任务、不调用沙箱
    if not guard.try_acquire(
        current_user.id,
        settings.code_max_concurrent_requests,
        settings.code_max_concurrent_per_user,
    ):
        raise HTTPException(429, SAFE_BUSY_MESSAGE)

    try:
        task = CodeTask(
            id=uuid.uuid4().hex,
            user_id=current_user.id,
            status="queued",
            code_length=code_bytes,
            timeout_seconds=timeout,
            started_at=datetime.utcnow(),
        )
        db.add(task)
        db.commit()

        try:
            submitted = await sandbox.asubmit(code, timeout)
        except SandboxUnavailable:
            _fail_task(db, task, "sandbox_unavailable", "sandbox manager unavailable")
            _raise_unavailable()

        job_id = str(submitted.get("job_id") or "") if isinstance(submitted, dict) else ""
        if not job_id:
            _fail_task(db, task, "sandbox_bad_response", "missing job id")
            _raise_unavailable()

        task.status = submitted.get("status") if submitted.get("status") in {
            "queued", "running",
        } else "running"
        db.commit()

        try:
            result = await _poll_job(sandbox, job_id)
            _save_result(db, task, result)
        except SandboxUnavailable as exc:
            error_code = (
                "sandbox_bad_response" if isinstance(exc, SandboxBadResponse)
                else "sandbox_unavailable"
            )
            logger.warning("沙箱任务异常收口（%s）: %s", error_code, job_id)
            await _safe_fail(db, task, sandbox, job_id, error_code)
            _raise_unavailable()
        except HTTPException:
            raise
        except Exception:
            logger.exception("代码任务处理异常，任务将落到安全终态: %s", task.id)
            await _safe_fail(db, task, sandbox, job_id, "internal_error")
            _raise_unavailable()

        return _result_to_response(task, result)
    finally:
        guard.release(current_user.id)


def _student_error_message(status: str) -> str | None:
    """学生端固定安全文案；详细内部错误只对教师/管理员可见"""
    if status == "failed":
        return SAFE_FAILED_MESSAGE
    if status in {"timeout", "resource_exceeded", "cancelled"}:
        return "任务已安全终止。"
    return None


@router.get("/tasks/{task_id}", response_model=CodeTaskOut)
def get_task(
    task_id: str,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """查询任务状态：学生只能查看自己的任务；教师可查看必要任务

    无权访问与不存在统一返回 404，避免通过猜测 task_id 探测他人任务。
    学生响应中的 error_message 使用固定安全文案，不返回 Docker / 路径 / 堆栈信息。
    """
    task = db.get(CodeTask, task_id)
    if task is None:
        raise HTTPException(404, "任务不存在")
    if task.user_id != current_user.id and current_user.role != "teacher":
        raise HTTPException(404, "任务不存在")

    is_staff = current_user.role in {"teacher", "admin"}
    return CodeTaskOut(
        task_id=task.id,
        status=task.status,
        stdout=task.stdout or "",
        stderr=task.stderr or "",
        exit_code=task.exit_code,
        duration_ms=task.duration_ms,
        error_code=task.error_code,
        error_message=(task.error_message if is_staff
                       else _student_error_message(task.status)),
        timeout_seconds=task.timeout_seconds,
        created_at=task.created_at,
        finished_at=task.finished_at,
    )
