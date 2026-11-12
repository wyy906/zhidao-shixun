"""健康检查。"""

from fastapi import APIRouter

from app.core.config import get_settings
from zhidao_contracts import CONTRACT_VERSION

router = APIRouter(tags=["health"])


@router.get("/health")
def health() -> dict:
    settings = get_settings()
    return {
        "status": "ok",
        "app": settings.app_name,
        "app_env": settings.app_env,
        "api_version": "v1",
        "contract_version": CONTRACT_VERSION,
    }
