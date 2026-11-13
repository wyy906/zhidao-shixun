"""CodeTask 的正式 Alembic 迁移应可用（建表 / 幂等 / 回滚）"""
import importlib.util
from pathlib import Path

from alembic.migration import MigrationContext
from alembic.operations import Operations
from sqlalchemy import create_engine, inspect

REVISION_FILE = (
    Path(__file__).resolve().parents[1]
    / "alembic" / "versions" / "20261112_0001_add_code_tasks.py"
)


def _load_revision():
    spec = importlib.util.spec_from_file_location("zd_rev_code_tasks", REVISION_FILE)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _run(engine, func):
    with engine.begin() as conn:
        context = MigrationContext.configure(conn)
        with Operations.context(context):
            func()
        return inspect(conn).get_table_names()


def test_code_tasks_migration_upgrade_and_downgrade(tmp_path):
    revision = _load_revision()
    assert revision.revision == "20261112_0001"
    # 迁移链：20261113_0000（基线核心表）→ 20261112_0001（code_tasks）
    assert revision.down_revision == "20261113_0000"

    engine = create_engine(f"sqlite:///{(tmp_path / 'mig.db').as_posix()}")
    assert "code_tasks" in _run(engine, revision.upgrade)
    # 已由 create_all 建过表时应幂等跳过
    assert "code_tasks" in _run(engine, revision.upgrade)
    assert "code_tasks" not in _run(engine, revision.downgrade)
