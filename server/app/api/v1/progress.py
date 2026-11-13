"""实验步骤进度接口（V2-04E1）：运行结果 → 验证器判定 → 状态机推进。

- 读进度无需令牌；提交/重置与运行接口同样受开发模式门（ZD_DEV_API_TOKEN）保护；
- 状态为进程内存态（开发/受控测试模式），重启即重置，响应中如实标注。
"""

from functools import lru_cache

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field

from app.api.v1.executions import (
    get_executor_client,
    get_experiments_repository,
    require_dev_access,
)
from app.core.errors import AppError
from app.experiments.repository import ExperimentsRepository
from app.services.executor.client import ExecutorServiceClient
from app.services.progress import StepProgressService

router = APIRouter(tags=["progress"])


class StepSubmitIn(BaseModel):
    code: str = Field(min_length=1)
    timeout_seconds: int = Field(default=10, gt=0, le=20)
    task_id: str = Field(default="step", min_length=1, max_length=128)


@lru_cache(maxsize=1)
def _singleton_service() -> StepProgressService:
    return StepProgressService()


def get_progress_service() -> StepProgressService:
    """进程级单例：步骤会话在同一进程内跨请求保持（重启即重置）。"""
    return _singleton_service()


@router.get("/experiments/{experiment_id}/progress")
def get_progress(
    experiment_id: str,
    repository: ExperimentsRepository = Depends(get_experiments_repository),
    service: StepProgressService = Depends(get_progress_service),
) -> dict:
    definition = _load(repository, experiment_id)
    return {"experiment_id": experiment_id, "states": service.states_view(definition)}


@router.post("/experiments/{experiment_id}/steps/{step_id}/submit")
def submit_step(
    experiment_id: str,
    step_id: str,
    body: StepSubmitIn,
    _: None = Depends(require_dev_access),
    repository: ExperimentsRepository = Depends(get_experiments_repository),
    client: ExecutorServiceClient = Depends(get_executor_client),
    service: StepProgressService = Depends(get_progress_service),
) -> dict:
    definition = _load(repository, experiment_id)
    if len(body.code.encode("utf-8")) > 65536:
        raise AppError(code="code_too_large", message="代码超过 65536 字节上限。", status_code=400)
    result = service.submit_step(
        definition, step_id, body.code, body.task_id, client, body.timeout_seconds
    )
    result["experiment_id"] = experiment_id
    result["step_id"] = step_id
    return result


@router.post("/experiments/{experiment_id}/progress/reset")
def reset_progress(
    experiment_id: str,
    _: None = Depends(require_dev_access),
    repository: ExperimentsRepository = Depends(get_experiments_repository),
    service: StepProgressService = Depends(get_progress_service),
) -> dict:
    definition = _load(repository, experiment_id)
    return {"experiment_id": experiment_id, "states": service.reset(definition)}


def _load(repository: ExperimentsRepository, experiment_id: str):
    definition = repository.get(experiment_id)
    if definition is None:
        raise AppError(
            code="experiment_not_found",
            message=f"实验 {experiment_id} 不存在或未导入（experiments/ 目录）。",
            status_code=404,
        )
    return definition
