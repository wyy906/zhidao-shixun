"""v1 路由聚合。"""

from fastapi import APIRouter

from app.api.v1 import contract, health

api_router = APIRouter()
api_router.include_router(health.router)
api_router.include_router(contract.router)
