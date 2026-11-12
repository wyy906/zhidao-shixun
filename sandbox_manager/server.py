"""沙箱管理器 HTTP 接口（运行在独立 Linux 执行节点）

所有接口都要求 `X-Sandbox-Token` 管理令牌；生产环境还应启用内网 TLS，
强烈建议双向 TLS（见 SANDBOX_DEPLOYMENT.md）。

接口：
  GET    /health          就绪检查（Docker / 固定镜像 / 运行时 / 资源限制）
  POST   /v1/jobs         提交任务（202 + job_id）
  GET    /v1/jobs/{id}    查询任务
  DELETE /v1/jobs/{id}    取消任务（运行中的容器会被强制终止）
"""
from __future__ import annotations

import logging
import secrets
from contextlib import asynccontextmanager

from fastapi import Depends, FastAPI, Header, HTTPException
from pydantic import BaseModel, ConfigDict

from .config import ManagerConfig
from .container_spec import SandboxLimits
from .jobs import JobStore
from .runner import DockerRunner, SandboxError

logger = logging.getLogger(__name__)


class JobIn(BaseModel):
    # 禁止学生/调用方传入额外字段（镜像、网络模式、资源限制等一律不可覆盖）
    model_config = ConfigDict(extra="forbid")

    code: str
    timeout: int = 10


def create_app(runner=None, config: ManagerConfig | None = None) -> FastAPI:
    cfg = config or ManagerConfig.from_env()
    cfg.validate()
    exec_runner = runner or DockerRunner(cfg)
    if hasattr(exec_runner, "limits"):
        limits = exec_runner.limits()
    else:
        limits = SandboxLimits(
            cpu_cores=cfg.cpu_cores,
            memory_mb=cfg.memory_mb,
            timeout_seconds=cfg.timeout_seconds,
            pids_limit=cfg.pids_limit,
            disk_mb=cfg.disk_mb,
            output_bytes=cfg.output_bytes,
            input_bytes=cfg.input_bytes,
            max_concurrent=cfg.max_concurrent,
        )
    jobs = JobStore(exec_runner, limits)

    @asynccontextmanager
    async def lifespan(_app: FastAPI):
        # 启动清理失败（Docker 不可用 / 容器删除失败）时拒绝进入可服务状态：
        # 抛出异常让进程启动失败，绝不会带着未知残留容器继续接受任务。
        cleanup = getattr(exec_runner, "cleanup_stale_containers", None)
        if callable(cleanup):
            try:
                cleanup()
            except Exception as exc:
                code = getattr(exc, "code", "cleanup_failed")
                logger.error("启动清理残留容器失败，拒绝提供服务: %s", code)
                raise RuntimeError(
                    f"sandbox startup cleanup failed: {code}"
                ) from exc
        yield

    app = FastAPI(title="zd-sandbox-manager", version="0.1.0", lifespan=lifespan)
    app.state.config = cfg
    app.state.runner = exec_runner
    app.state.jobs = jobs

    def require_token(x_sandbox_token: str = Header(default="")) -> None:
        if not cfg.token:
            raise HTTPException(503, {"status": "misconfigured", "error": "token_not_configured"})
        if not secrets.compare_digest(x_sandbox_token, cfg.token):
            raise HTTPException(401, "unauthorized")

    auth = Depends(require_token)

    def _unavailable(exc: SandboxError) -> HTTPException:
        # 只回传错误码，不回传宿主机路径 / Docker 细节
        return HTTPException(503, {"status": "unavailable", "error": exc.code})

    @app.get("/health")
    def health(_: None = auth) -> dict:
        try:
            info = exec_runner.check_ready()
        except SandboxError as exc:
            raise _unavailable(exc)
        return {"status": "ok", **info}

    @app.post("/v1/jobs", status_code=202)
    def submit_job(data: JobIn, _: None = auth) -> dict:
        code = data.code or ""
        if not code.strip():
            raise HTTPException(400, "code is empty")
        if len(code.encode("utf-8")) > cfg.input_bytes:
            raise HTTPException(400, "code too large")
        timeout = max(1, min(int(data.timeout or cfg.timeout_seconds), cfg.timeout_seconds))
        try:
            exec_runner.check_ready()
        except SandboxError as exc:
            raise _unavailable(exc)
        return jobs.submit(code, timeout)

    @app.get("/v1/jobs/{job_id}")
    def get_job(job_id: str, _: None = auth) -> dict:
        job = jobs.get(job_id)
        if job is None:
            raise HTTPException(404, "job not found")
        return job

    @app.delete("/v1/jobs/{job_id}")
    def cancel_job(job_id: str, _: None = auth) -> dict:
        job = jobs.cancel(job_id)
        if job is None:
            raise HTTPException(404, "job not found")
        return job

    return app
