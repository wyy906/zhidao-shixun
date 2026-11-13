"""实验代码运行接口（V2-04 C1：打通 业务API → 执行服务客户端 → 独立执行服务）。

架构边界（沿用 V2-04A/B 已批准方案，不新增架构）：
- 业务进程只经 `ExecutorServiceClient`（依赖注入）调用独立执行服务，
  绝不直接访问 Docker daemon / socket，绝不宿主机执行用户代码；
- 当前项目尚无用户认证体系：本接口仅限开发/受控测试模式——必须配置
  ZD_DEV_API_TOKEN（服务端）并在请求头 X-Dev-Token 中携带；未配置时接口整体
  关闭（fail-closed）。这不是用户体系，仅防止匿名无限制任意代码执行；
- 实验必须已导入（experiments/ 目录存在该 experiment_id）才可运行（fail-closed）；
- 执行服务不可达 / Docker 未就绪 / digest 未锁定 → 明确错误码与安装提示，
  绝不伪装执行成功。
"""

import secrets

from fastapi import APIRouter, Depends, Request
from pydantic import BaseModel, Field

from app.core.config import Settings, get_settings
from app.core.errors import AppError
from app.experiments.repository import ExperimentsRepository
from app.services.executor.base import MAX_CODE_BYTES, MAX_TIMEOUT_SECONDS
from app.services.executor.client import (
    DockerUnavailableError,
    ExecutorServiceClient,
    ExecutorServiceError,
    ExecutionSubmission,
)

router = APIRouter(tags=["executions"])

# 当前无用户体系：固定开发模式用户标识（如实标注，不冒充真实用户）
DEV_USER_ID = "dev-local"

_DOCKER_HINT = (
    "Docker 环境未就绪。安装 Docker Desktop for Windows（WSL2 后端）并启动后，"
    "配置 ZD_EXECUTOR_TOKEN 与已批准镜像 digest（executor_image_lock.json），"
    "再运行 scripts/start-executor-service.ps1 启动独立执行服务。"
    "本系统绝不在宿主机直接执行用户代码。"
)


class RunRequestIn(BaseModel):
    """运行请求体：只有代码、超时和任务标识，无任何镜像/容器参数注入面。"""

    code: str = Field(min_length=1)
    timeout_seconds: int = Field(default=10, gt=0, le=MAX_TIMEOUT_SECONDS)
    task_id: str = Field(default="run", min_length=1, max_length=128)


def get_settings_dep() -> Settings:
    return get_settings()


def get_experiments_repository() -> ExperimentsRepository:
    return ExperimentsRepository()


def get_executor_client(
    settings: Settings = Depends(get_settings_dep),
) -> ExecutorServiceClient:
    """依赖注入：构建指向独立执行服务的客户端（业务进程不接触 Docker）。"""
    try:
        return ExecutorServiceClient(
            base_url=settings.executor_api_url, token=settings.executor_token
        )
    except ExecutorServiceError as exc:
        raise AppError(
            code="executor_not_configured",
            message=(
                "执行服务令牌未配置（ZD_EXECUTOR_TOKEN 为空），"
                "业务 API 拒绝提交执行（fail-closed）。"
            ),
            status_code=503,
        ) from exc


def require_dev_access(
    request: Request, settings: Settings = Depends(get_settings_dep)
) -> None:
    """开发/受控测试模式访问门：未配置即整体关闭；配置后需 X-Dev-Token 匹配。"""
    configured = settings.dev_api_token
    if not configured:
        raise AppError(
            code="executor_dev_mode_disabled",
            message=(
                "运行接口已关闭：未配置开发模式令牌（ZD_DEV_API_TOKEN）。"
                "当前尚无用户认证体系，本接口仅限本机开发/受控测试使用。"
            ),
            status_code=503,
        )
    provided = request.headers.get("X-Dev-Token", "")
    if not provided or not secrets.compare_digest(provided, configured):
        raise AppError(
            code="dev_auth_required",
            message="缺少或错误的 X-Dev-Token，无权使用运行接口。",
            status_code=401,
        )


@router.post("/experiments/{experiment_id}/runs")
def run_experiment_code(
    experiment_id: str,
    body: RunRequestIn,
    _: None = Depends(require_dev_access),
    repository: ExperimentsRepository = Depends(get_experiments_repository),
    client: ExecutorServiceClient = Depends(get_executor_client),
) -> dict:
    """提交一段 Python 代码进入隔离执行，返回真实运行结果。"""
    definition = repository.get(experiment_id)
    if definition is None:
        raise AppError(
            code="experiment_not_found",
            message=f"实验 {experiment_id} 不存在或未导入（experiments/ 目录）。",
            status_code=404,
        )
    if len(body.code.encode("utf-8")) > MAX_CODE_BYTES:
        raise AppError(
            code="code_too_large",
            message=f"代码超过 {MAX_CODE_BYTES} 字节上限。",
            status_code=400,
        )
    submission = ExecutionSubmission(
        user_id=DEV_USER_ID,
        experiment_id=experiment_id,
        task_id=body.task_id,
        language="python",
        code=body.code,
        timeout_seconds=body.timeout_seconds,
    )
    payload = submit_execution(client, submission)
    result = _format_result(payload, experiment_id)
    # 执行服务响应不含 task_id，由业务请求回填
    result["task_id"] = body.task_id
    return result


@router.get("/executor/status")
def executor_status(
    _: None = Depends(require_dev_access),
    client: ExecutorServiceClient = Depends(get_executor_client),
) -> dict:
    """探测独立执行服务健康状态（Docker 是否就绪 / digest 是否已锁定）。"""
    try:
        health = client.health()
    except DockerUnavailableError as exc:
        raise AppError(
            code="executor_unavailable",
            message=f"执行服务不可达（未启动或 Docker 环境未就绪）：{exc}",
            status_code=503,
            details={"install_hint": _DOCKER_HINT},
        ) from exc
    engine_available = bool(health.get("engine_available"))
    digest_locked = bool(health.get("image_digest_locked"))
    return {
        "executor_service": "reachable",
        "engine_available": engine_available,
        "image_digest_locked": digest_locked,
        "docker_integration_tests": health.get("docker_integration_tests"),
        "docker_environment_ready": engine_available and digest_locked,
    }


def submit_execution(client: ExecutorServiceClient, submission: ExecutionSubmission) -> dict:
    """调用执行服务并统一映射错误；执行失败绝不伪装成运行结果。

    （V2-04E1 起公开为共享助手：运行接口与步骤进度接口共用同一错误映射。）
    """
    try:
        payload = client.submit(submission)
    except DockerUnavailableError as exc:
        raise AppError(
            code="executor_unavailable",
            message=f"执行服务不可达（可能未启动，或 Docker 环境未就绪）：{exc}",
            status_code=503,
            details={"install_hint": _DOCKER_HINT},
        ) from exc
    except ExecutorServiceError as exc:
        raise AppError(
            code="executor_service_error",
            message=f"执行服务返回错误：{exc}",
            status_code=502,
        ) from exc

    status = payload.get("status")
    if status == "error":
        failure_kind = payload.get("failure_kind") or ""
        detail = payload.get("failure_detail") or ""
        if failure_kind == "docker_unavailable":
            raise AppError(
                code="executor_unavailable",
                message=f"Docker 环境未就绪，拒绝执行（fail-closed）：{detail}",
                status_code=503,
                details={"install_hint": _DOCKER_HINT},
            )
        if failure_kind == "image_digest_not_locked":
            raise AppError(
                code="executor_image_not_locked",
                message=f"执行镜像 digest 未批准（executor_image_lock.json pending），拒绝执行：{detail}",
                status_code=503,
            )
        raise AppError(
            code="executor_infra_error",
            message=f"执行基础设施错误：{detail}",
            status_code=502,
            details={"failure_kind": failure_kind},
        )
    return payload


def _format_result(payload: dict, experiment_id: str) -> dict:
    """执行服务响应 → 业务 API 响应（execution_id + 真实运行结果）。"""
    return {
        "execution_id": payload.get("record_id"),
        "status": payload.get("status"),
        "exit_code": payload.get("exit_code"),
        "stdout": payload.get("stdout", ""),
        "stderr": payload.get("stderr", ""),
        "timed_out": bool(payload.get("timed_out")),
        "truncated": bool(payload.get("truncated")),
        "duration_ms": payload.get("duration_ms"),
        "experiment_id": experiment_id,
        "failure_kind": payload.get("failure_kind"),
        "failure_detail": payload.get("failure_detail"),
    }
