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

import secrets

from fastapi import Depends, FastAPI, Header, HTTPException
from pydantic import BaseModel

from .config import ManagerConfig
from .container_spec import SandboxLimits
from .jobs import JobStore
from .runner import DockerRunner, SandboxError


class JobIn(BaseModel):
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

    app = FastAPI(title="zd-sandbox-manager", version="0.1.0")
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
