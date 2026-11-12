"""数据库初始化策略测试

- 开发环境（默认）：create_all 自动建表；
- 生产环境：缺少表时拒绝启动，必须先用 Alembic 迁移；
- 迁移补齐 code_tasks 后，生产模式可正常通过检查。
"""
import importlib.util
from pathlib import Path

import pytest
from alembic.migration import MigrationContext
from alembic.operations import Operations
from sqlalchemy import create_engine, inspect, text

from app.core.config import settings
from app.db.session import Base
from app.main import REQUIRED_TABLES, _auto_create_enabled, initialize_database
from app import models  # noqa: F401  注册全部 ORM 模型

REVISION_FILE = (
    Path(__file__).resolve().parents[1]
    / "alembic" / "versions" / "20261112_0001_add_code_tasks.py"
)


def _engine(tmp_path):
    return create_engine(f"sqlite:///{(tmp_path / 'init.db').as_posix()}")


def _run_migration(engine) -> None:
    spec = importlib.util.spec_from_file_location("zd_rev_code_tasks_init", REVISION_FILE)
    revision = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(revision)
    with engine.begin() as conn:
        context = MigrationContext.configure(conn)
        with Operations.context(context):
            revision.upgrade()


def test_development_auto_create_builds_full_schema(tmp_path):
    engine = _engine(tmp_path)
    initialize_database(bind=engine, auto_create=True)
    assert REQUIRED_TABLES <= set(inspect(engine).get_table_names())


def test_production_refuses_empty_database(tmp_path):
    engine = _engine(tmp_path)
    with pytest.raises(RuntimeError, match="alembic upgrade head"):
        initialize_database(bind=engine, auto_create=False)


def test_production_refuses_schema_without_code_tasks(tmp_path):
    engine = _engine(tmp_path)
    initialize_database(bind=engine, auto_create=True)
    with engine.begin() as conn:
        conn.execute(text("DROP TABLE code_tasks"))

    with pytest.raises(RuntimeError, match="code_tasks"):
        initialize_database(bind=engine, auto_create=False)


def test_production_accepts_schema_completed_by_alembic(tmp_path):
    engine = _engine(tmp_path)
    initialize_database(bind=engine, auto_create=True)
    with engine.begin() as conn:
        conn.execute(text("DROP TABLE code_tasks"))

    _run_migration(engine)
    initialize_database(bind=engine, auto_create=False)  # 不抛异常
    assert "code_tasks" in set(inspect(engine).get_table_names())


def test_auto_create_default_follows_app_env(monkeypatch):
    monkeypatch.setattr(settings, "db_auto_create", None)
    monkeypatch.setattr(settings, "app_env", "development")
    assert _auto_create_enabled() is True
    monkeypatch.setattr(settings, "app_env", "production")
    assert _auto_create_enabled() is False
    monkeypatch.setattr(settings, "db_auto_create", True)
    assert _auto_create_enabled() is True
    monkeypatch.setattr(settings, "db_auto_create", False)
    assert _auto_create_enabled() is False
