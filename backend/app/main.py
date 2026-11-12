"""FastAPI 应用主入口"""
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.core.config import settings
from app.api.v1.api import api_router
from app.db.session import engine, Base, SessionLocal


def _ensure_admin() -> None:
    """数据库里一个用户都没有时，创建一个管理员账号用于首次登录

    这不是演示数据：只创建登录所需的管理员，实验等内容全部由老师后期导入。
    """
    from app.core.security import hash_password
    from app.models import User

    db = SessionLocal()
    try:
        if db.query(User).count() == 0:
            db.add(User(
                username=settings.admin_username,
                hashed_password=hash_password(settings.admin_password),
                real_name="管理员",
                role="teacher",
            ))
            db.commit()
    finally:
        db.close()


def _fail_interrupted_tasks(db) -> int:
    """服务重启时，把上次未完成的代码执行任务标记为失败

    容器由独立执行节点回收，业务后端重启后无法再确认这些任务是否成功，
    因此绝不能把它们当成成功状态返回。
    """
    from app.models import CodeTask

    interrupted = db.query(CodeTask).filter(CodeTask.status.in_(["queued", "running"])).all()
    for task in interrupted:
        task.status = "failed"
        task.error_code = "service_restarted"
        task.error_message = "服务重启，任务已中断"
        task.stderr = "代码执行环境已重启，任务中断，请重新运行。"
    if interrupted:
        db.commit()
    return len(interrupted)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """应用生命周期：启动时建表，关闭时清理"""
    # 开发环境自动建表（生产建议用 alembic migrate）
    Base.metadata.create_all(bind=engine)
    _ensure_admin()
    db = SessionLocal()
    try:
        _fail_interrupted_tasks(db)
    finally:
        db.close()
    yield


app = FastAPI(
    title=settings.app_name,
    version="0.1.0",
    description="智导实训 - AI 视觉感知与实时操作引导平台 API",
    lifespan=lifespan,
)

# CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# 挂载路由
app.include_router(api_router, prefix="/api")


@app.get("/health")
async def health() -> dict:
    return {"status": "ok", "app": settings.app_name}


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(
        "app.main:app",
        host=settings.host,
        port=settings.port,
        reload=settings.debug,
    )
