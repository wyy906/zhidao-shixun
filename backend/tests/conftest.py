"""pytest 公共夹具 —— 测试数据库隔离

隔离策略（三条同时生效，缺一不可）：
1. **导入 app 之前**把 DATABASE_URL 指向一次性临时文件，确保即使误触发 lifespan
   也不会碰到项目真实数据库 zd_shixun.db。
2. 每个测试用 pytest 的 tmp_path 新建独立 SQLite 文件，测试结束即销毁。
3. 用 app.dependency_overrides 把 get_db 换成测试会话，请求不会用到全局 engine。

因此测试不需要联网、不需要真实 AI Key、不读取真实 .env。
"""
import os
import sys
import tempfile
from pathlib import Path

import pytest

# ---------------------------------------------------------------------------
# 关键顺序：先设置环境变量，再导入 app 包
# ---------------------------------------------------------------------------
BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

_GUARD_DIR = tempfile.mkdtemp(prefix="zd_shixun_test_guard_")
_GUARD_DB = Path(_GUARD_DIR) / "guard.db"

# 环境变量优先级高于 .env，这里强制覆盖，避免读到真实配置
os.environ["DATABASE_URL"] = f"sqlite:///{_GUARD_DB.as_posix()}"
os.environ["APP_ENV"] = "development"

from fastapi.testclient import TestClient  # noqa: E402
from sqlalchemy import create_engine  # noqa: E402
from sqlalchemy.orm import sessionmaker  # noqa: E402

from app.core.security import hash_password  # noqa: E402
from app.db.session import Base, get_db  # noqa: E402
from app.main import app  # noqa: E402
from app.models import User  # noqa: E402

TEACHER = {"username": "teacher01", "password": "teacher-pass-123"}
STUDENT = {"username": "student01", "password": "student-pass-123"}
STUDENT2 = {"username": "student02", "password": "student-pass-123"}


@pytest.fixture()
def db_engine(tmp_path):
    """每个测试一个独立的临时 SQLite 库，结束即销毁"""
    db_file = tmp_path / "test.db"
    engine = create_engine(
        f"sqlite:///{db_file.as_posix()}",
        connect_args={"check_same_thread": False},
    )
    Base.metadata.create_all(bind=engine)
    yield engine
    Base.metadata.drop_all(bind=engine)
    engine.dispose()


@pytest.fixture()
def db_session(db_engine):
    """直连测试库的会话，用于准备数据和断言落库结果"""
    TestingSession = sessionmaker(bind=db_engine, autoflush=False, autocommit=False,
                                  expire_on_commit=False)
    session = TestingSession()
    try:
        yield session
    finally:
        session.close()


@pytest.fixture()
def client(db_engine):
    """FastAPI 测试客户端：get_db 被覆盖为测试库会话"""
    TestingSession = sessionmaker(bind=db_engine, autoflush=False, autocommit=False,
                                  expire_on_commit=False)

    def _override_get_db():
        db = TestingSession()
        try:
            yield db
        finally:
            db.close()

    app.dependency_overrides[get_db] = _override_get_db
    # 不使用 with TestClient(app)：避免触发 lifespan 的建表/建管理员逻辑
    test_client = TestClient(app)
    try:
        yield test_client
    finally:
        test_client.close()
        app.dependency_overrides.clear()


@pytest.fixture()
def users(db_session):
    """预置教师 1 名、学生 2 名"""
    teacher = User(username=TEACHER["username"], hashed_password=hash_password(TEACHER["password"]),
                   real_name="教师甲", role="teacher")
    student = User(username=STUDENT["username"], hashed_password=hash_password(STUDENT["password"]),
                   real_name="学生甲", role="student")
    student2 = User(username=STUDENT2["username"], hashed_password=hash_password(STUDENT2["password"]),
                    real_name="学生乙", role="student")
    db_session.add_all([teacher, student, student2])
    db_session.commit()
    return {
        "teacher": {"id": teacher.id, **TEACHER},
        "student": {"id": student.id, **STUDENT},
        "student2": {"id": student2.id, **STUDENT2},
    }


def _login(client: TestClient, username: str, password: str) -> str:
    resp = client.post("/api/v1/auth/login", json={"username": username, "password": password})
    assert resp.status_code == 200, resp.text
    return resp.json()["token"]


def _headers(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}


@pytest.fixture()
def teacher_token(client, users):
    return _login(client, TEACHER["username"], TEACHER["password"])


@pytest.fixture()
def student_token(client, users):
    return _login(client, STUDENT["username"], STUDENT["password"])


@pytest.fixture()
def student2_token(client, users):
    return _login(client, STUDENT2["username"], STUDENT2["password"])


@pytest.fixture()
def teacher_headers(teacher_token):
    return _headers(teacher_token)


@pytest.fixture()
def student_headers(student_token):
    return _headers(student_token)


@pytest.fixture()
def student2_headers(student2_token):
    return _headers(student2_token)


# ---------------------------------------------------------------------------
# 常用数据构造
# ---------------------------------------------------------------------------
def make_experiment_payload(title: str = "测试实验", steps: list | None = None) -> dict:
    """构造导入接口所需的实验包结构"""
    if steps is None:
        steps = [
            {"title": "步骤一", "instruction": "打开终端", "expected_result": "终端已打开"},
            {"title": "步骤二", "instruction": "输入命令", "expected_result": "命令执行成功"},
            {"title": "步骤三", "instruction": "保存结果", "expected_result": "结果已保存"},
        ]
    return {
        "version": 1,
        "overwrite": False,
        "experiment": {
            "title": title,
            "description": "自动化测试用实验",
            "type": "python",
            "software": "Windows Terminal",
            "prerequisites": ["Python 基础"],
            "criteria": ["能运行脚本"],
            "status": "published",
        },
        "steps": steps,
    }


@pytest.fixture()
def imported_experiment(client, teacher_headers):
    """直接通过导入接口创建一个 3 步实验，返回响应体"""
    resp = client.post("/api/v1/experiments/import",
                       json=make_experiment_payload(), headers=teacher_headers)
    assert resp.status_code == 200, resp.text
    return resp.json()
