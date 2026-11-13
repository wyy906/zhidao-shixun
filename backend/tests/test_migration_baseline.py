"""基线迁移（20261113_0000）应创建全部核心表且对 create_all 历史库幂等"""
import importlib.util
from pathlib import Path

from alembic.migration import MigrationContext
from alembic.operations import Operations
from sqlalchemy import create_engine, inspect

REVISION_FILE = (
    Path(__file__).resolve().parents[1]
    / "alembic" / "versions" / "20261113_0000_baseline.py"
)

CORE_TABLES = {
    "users",
    "experiments",
    "experiment_steps",
    "experiment_progress",
    "operation_records",
    "experiment_reports",
}


def _load_revision():
    spec = importlib.util.spec_from_file_location("zd_rev_baseline", REVISION_FILE)
    module = importlib.util.module_from_spec(spec)
    sys_modules_guard = "zd_rev_baseline"
    import sys

    sys.modules[sys_modules_guard] = module
    spec.loader.exec_module(module)
    return module


def _run(engine, func):
    with engine.begin() as conn:
        context = MigrationContext.configure(conn)
        with Operations.context(context):
            func()
        return set(inspect(conn).get_table_names())


def test_baseline_upgrade_creates_all_core_tables(tmp_path):
    revision = _load_revision()
    assert revision.revision == "20261113_0000"
    assert revision.down_revision is None

    engine = create_engine(f"sqlite:///{(tmp_path / 'mig.db').as_posix()}")
    tables = _run(engine, revision.upgrade)
    assert CORE_TABLES <= tables
    # 幂等：再次 upgrade 不报错
    assert CORE_TABLES <= _run(engine, revision.upgrade)


def test_baseline_downgrade_removes_core_tables(tmp_path):
    revision = _load_revision()
    engine = create_engine(f"sqlite:///{(tmp_path / 'mig.db').as_posix()}")
    _run(engine, revision.upgrade)
    tables = _run(engine, revision.downgrade)
    assert CORE_TABLES.isdisjoint(tables)
