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

import logging
import time
import uuid
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.api.deps import get_current_user
from app.core.config import settings
from app.db.session import get_db
from app.models import CodeTask, User
from app.services.sandbox_client import (
    SAFE_UNAVAILABLE_MESSAGE,
    SandboxClient,
    SandboxUnavailable,
    get_sandbox_client,
)

logger = logging.getLogger(__name__)

router = APIRouter()

TERMINAL_STATUSES = {
    "succeeded", "failed", "timeout", "resource_exceeded", "cancelled",
}


class CodeRunIn(BaseModel):
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


@router.post("/run", response_model=CodeRunOut)
def run_code(
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
        submitted = sandbox.submit(code, timeout)
    except SandboxUnavailable:
        _fail_task(db, task, "sandbox_unavailable", "sandbox manager unavailable")
        _raise_unavailable()

    job_id = str(submitted.get("job_id") or "")
    if not job_id:
        _fail_task(db, task, "sandbox_bad_response", "missing job id")
        _raise_unavailable()

    task.status = submitted.get("status") if submitted.get("status") in {
        "queued", "running",
    } else "running"
    db.commit()

    # 轮询：等待终端状态或达到同步等待上限
    started_at = time.monotonic()
    deadline = started_at + settings.sandbox_sync_wait_seconds
    result: dict | None = None
    while True:
        try:
            result = sandbox.get_job(job_id)
        except SandboxUnavailable:
            _fail_task(db, task, "sandbox_unavailable", "sandbox manager unavailable during run")
            _raise_unavailable()

        status = result.get("status")
        if status in TERMINAL_STATUSES:
            break
        if time.monotonic() >= deadline:
            # 超过同步等待上限：取消任务并安全失败，不把未完成任务当成成功
            try:
                sandbox.cancel(job_id)
            except SandboxUnavailable:
                logger.warning("取消超时任务失败: %s", job_id)
            result = {
                "status": "timeout",
                "stdout": "",
                "stderr": "运行超时，任务已被终止。",
                "exit_code": -1,
                "duration_ms": int((time.monotonic() - started_at) * 1000),
            }
            break
        time.sleep(0.2)

    _save_result(db, task, result)
    return _result_to_response(task, result)


@router.get("/tasks/{task_id}", response_model=CodeTaskOut)
def get_task(
    task_id: str,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """查询任务状态：学生只能查看自己的任务；教师可查看必要任务

    无权访问与不存在统一返回 404，避免通过猜测 task_id 探测他人任务。
    """
    task = db.get(CodeTask, task_id)
    if task is None:
        raise HTTPException(404, "任务不存在")
    if task.user_id != current_user.id and current_user.role != "teacher":
        raise HTTPException(404, "任务不存在")

    return CodeTaskOut(
        task_id=task.id,
        status=task.status,
        stdout=task.stdout or "",
        stderr=task.stderr or "",
        exit_code=task.exit_code,
        duration_ms=task.duration_ms,
        error_code=task.error_code,
        error_message=task.error_message,
        timeout_seconds=task.timeout_seconds,
        created_at=task.created_at,
        finished_at=task.finished_at,
    )
