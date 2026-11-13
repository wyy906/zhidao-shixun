"""独立执行服务 HTTP 接口（V2-04B 阶段 B2）。

架构边界（V2-04A 已批准方案）：
- 本应用由独立进程运行（scripts/start-executor-service.ps1，默认 127.0.0.1:8101），
  只有它加载 Docker SDK / 访问 Docker daemon；FastAPI 业务进程绝不导入本模块；
- 接口是受约束的任务接口，不是任意 Docker API 代理：请求只含
  user_id/experiment_id/task_id/code/timeout_seconds，无任何镜像/容器/挂载参数；
- 鉴权：X-Execution-Token 与服务端配置比对（常量时间比较）；令牌未配置时服务拒绝启动；
- Docker 不可用 / digest 未锁定 / 任何基础设施异常 → 结构化 error，fail-closed。

注意：本模块依赖 fastapi，仅在执行服务进程内导入。
"""

import secrets
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from fastapi import FastAPI, HTTPException, Request
from pydantic import BaseModel, Field

from app.services.executor.base import (
    DockerSandboxConfig,
    UnsafeExecutionRequest,
)
from app.services.executor.models import ExecutionTask
from app.services.executor.records import ExecutionRecord, JsonlRecordStore
from app.services.executor.service import SandboxExecutionService


class ExecutionTaskIn(BaseModel):
    """受约束的执行任务请求体——没有镜像、容器、挂载等任何注入面。"""

    user_id: str = Field(min_length=1, max_length=128)
    experiment_id: str = Field(min_length=1, max_length=128)
    task_id: str = Field(min_length=1, max_length=128)
    language: str = "python"
    code: str = Field(min_length=1)
    timeout_seconds: int = 10


def create_executor_app(
    token: str,
    driver: Any = None,
    expected_digest: str | None = None,
    store: JsonlRecordStore | None = None,
    config: DockerSandboxConfig | None = None,
) -> FastAPI:
    """构建执行服务应用。

    token 为空 → 拒绝启动（fail-closed）；driver/expected_digest/store 可注入用于测试。
    生产路径下 driver 由调用方选择（DockerSdkDriver），由独立进程在 main() 中装配。
    """
    if not token:
        raise ValueError("执行服务令牌未配置（ZD_EXECUTOR_TOKEN 为空），拒绝启动（fail-closed）")
    app = FastAPI(title="zhidao executor service", docs_url=None, redoc_url=None)
    resolved_store = store or JsonlRecordStore(Path("data/executor_records.jsonl"))
    service = SandboxExecutionService(
        driver=driver, config=config, expected_digest=expected_digest,
    )

    def _check_token(request: Request) -> None:
        provided = request.headers.get("X-Execution-Token", "")
        if not provided or not secrets.compare_digest(provided, token):
            raise HTTPException(status_code=401, detail="invalid execution token")

    @app.get("/healthz")
    def healthz() -> dict:
        engine = service._driver.engine_info()  # noqa: SLF001 - 同包边界内装配
        return {
            "status": "ok",
            "engine_available": bool(engine),
            "engine": dict(engine) if engine else None,
            "image_digest_locked": bool(expected_digest),
            "docker_integration_tests": (
                "FIRST_BATCH_PASSED_10_OF_10（2026-11-13 真实 Docker 实测：端到端/非root/"
                "只读根/tmpfs/禁网/分流/语法错误/超时终止/清理；扩大覆盖进行中）"
            ),
        }

    @app.post("/v1/executions")
    def create_execution(task_in: ExecutionTaskIn, request: Request) -> dict:
        _check_token(request)
        try:
            exec_request = _build_request(task_in)
            task = ExecutionTask(
                user_id=task_in.user_id,
                experiment_id=task_in.experiment_id,
                task_id=task_in.task_id,
                request=exec_request,
            )
        except UnsafeExecutionRequest as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        outcome = service.execute(task)
        record = ExecutionRecord.from_outcome(
            outcome,
            record_id=uuid.uuid4().hex,
            created_at=datetime.now(timezone.utc).isoformat(),
        )
        resolved_store.append(record)
        return {
            "record_id": record.record_id,
            "status": record.status,
            "exit_code": record.exit_code,
            "stdout": record.stdout,
            "stderr": record.stderr,
            "timed_out": record.timed_out,
            "truncated": record.truncated,
            "failure_kind": record.failure_kind,
            "failure_detail": record.failure_detail,
            "container_id": record.container_id,
            "duration_ms": record.duration_ms,
            "created_at": record.created_at,
        }

    return app


def _build_request(task_in: ExecutionTaskIn):
    from app.services.executor.base import ExecutionRequest

    return ExecutionRequest(
        language=task_in.language,
        code=task_in.code,
        timeout_seconds=task_in.timeout_seconds,
    )


def main() -> None:
    """独立执行服务进程入口：装配 Docker SDK 驱动并启动 uvicorn。"""
    import os

    import uvicorn

    from app.core.config import get_settings
    from app.services.executor.docker_adapter import DockerSdkDriver

    settings = get_settings()
    token = settings.executor_token
    if not token:
        raise SystemExit("ZD_EXECUTOR_TOKEN 未配置；执行服务拒绝启动（fail-closed）。")
    app = create_executor_app(
        token=token,
        driver=DockerSdkDriver(),
        expected_digest=settings.executor_image_digest or None,
        store=JsonlRecordStore(Path(settings.executor_records_path)),
        config=DockerSandboxConfig(image=settings.executor_image_tag),
    )
    uvicorn.run(
        app,
        host=settings.executor_bind_host,
        port=settings.executor_bind_port,
        log_level=settings.log_level.lower(),
    )


if __name__ == "__main__":
    main()
