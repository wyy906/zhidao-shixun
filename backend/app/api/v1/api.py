"""API 路由汇总"""
from fastapi import APIRouter

from app.api.v1.routers import auth, experiments, progress, ai, analytics, code

api_router = APIRouter()
api_router.include_router(auth.router, prefix="/v1/auth", tags=["auth"])
api_router.include_router(experiments.router, prefix="/v1/experiments", tags=["experiments"])
api_router.include_router(progress.router, prefix="/v1/progress", tags=["progress"])
api_router.include_router(ai.router, prefix="/v1/ai", tags=["ai"])
api_router.include_router(code.router, prefix="/v1/code", tags=["code"])
api_router.include_router(analytics.router, prefix="/v1/analytics", tags=["analytics"])
