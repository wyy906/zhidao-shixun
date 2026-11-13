"""实验列表与详情接口（V2-04D1：前端选择实验所需的最小只读 API）。

- 数据来自 ExperimentsRepository（experiments/ 目录，用户导入，仓库不内置演示数据）；
- 加载遵循 V2-03 fail-closed 语义：非法文件不进入列表，问题数如实返回 issues_count；
- 只读接口，不涉及代码执行与任何敏感能力，无需开发令牌。
"""

from fastapi import APIRouter, Depends

from app.core.errors import AppError
from app.experiments.repository import ExperimentsRepository
from app.api.v1.executions import get_experiments_repository

router = APIRouter(tags=["experiments"])


@router.get("/experiments")
def list_experiments(
    repository: ExperimentsRepository = Depends(get_experiments_repository),
) -> dict:
    loaded, issues = repository.load_all()
    experiments = [
        {
            "experiment_id": d.experiment_id,
            "title": d.title,
            "category": d.category,
            "version": d.version,
            "environment": d.environment,
            "step_count": len(d.steps),
            "estimated_minutes": d.meta.estimated_minutes,
            "difficulty": d.meta.difficulty,
        }
        for d in sorted(loaded.values(), key=lambda item: item.experiment_id)
    ]
    return {"experiments": experiments, "issues_count": len(issues)}


@router.get("/experiments/{experiment_id}")
def get_experiment(
    experiment_id: str,
    repository: ExperimentsRepository = Depends(get_experiments_repository),
) -> dict:
    definition = repository.get(experiment_id)
    if definition is None:
        raise AppError(
            code="experiment_not_found",
            message=f"实验 {experiment_id} 不存在或未导入（experiments/ 目录）。",
            status_code=404,
        )
    return {"experiment": definition.model_dump(mode="json")}
