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


# 启动时必须存在的表（迁移后应全部就绪）
REQUIRED_TABLES = frozenset({
    "users",
    "experiments",
    "experiment_steps",
    "experiment_progress",
    "operation_records",
    "experiment_reports",
    "code_tasks",
})


def _auto_create_enabled() -> bool:
    """解析建表策略：未显式配置时，仅 development 自动建表"""
    if settings.db_auto_create is None:
        return settings.app_env == "development"
    return bool(settings.db_auto_create)


def initialize_database(bind=None, auto_create: bool | None = None) -> None:
    """初始化数据库结构

    - 开发环境（默认）：`create_all` 自动建表，保持原有体验；
    - 生产环境：**不**自动建表，缺少表时拒绝启动并提示执行 `alembic upgrade head`。
      这样避免 create_all 长期替代正式迁移。
    """
    bind = engine if bind is None else bind
    if auto_create is None:
        auto_create = _auto_create_enabled()

    # 确保所有 ORM 模型已注册到 Base.metadata（create_all 与迁移检查都依赖它）
    from app import models  # noqa: F401

    if auto_create:
        Base.metadata.create_all(bind=bind)
        return

    from sqlalchemy import inspect

    missing = sorted(REQUIRED_TABLES - set(inspect(bind).get_table_names()))
    if missing:
        raise RuntimeError(
            "数据库结构不完整，拒绝启动（当前环境不允许 create_all 自动建表）。"
            f"缺少表: {', '.join(missing)}。请先执行 `alembic upgrade head`，"
            "或在开发环境显式设置 DB_AUTO_CREATE=true。"
        )


@asynccontextmanager
async def lifespan(app: FastAPI):
    """应用生命周期：启动时初始化数据库，关闭时清理"""
    initialize_database()
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
