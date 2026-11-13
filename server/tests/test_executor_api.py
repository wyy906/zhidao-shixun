"""独立执行服务 HTTP 接口测试（V2-04B 阶段 B2）。

Mock 驱动注入，验证鉴权/请求约束/记录落盘/fail-closed 语义；
不代表真实 Docker 集成验证（阶段 C 之前保持 BLOCKED）。
"""

import json
import sys
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.services.executor.client import (
    DockerUnavailableError,
    ExecutorServiceClient,
    ExecutorServiceError,
    ExecutionSubmission,
)
from app.services.executor.records import JsonlRecordStore
from app.services.executor.service_app import create_executor_app

from test_executor_service import FakeDriver, DIGEST_OK, make_task  # noqa: F401

TOKEN = "test-executor-token"


def make_client(tmp_path: Path, driver: FakeDriver, digest: str | None = DIGEST_OK,
                store: JsonlRecordStore | None = None) -> TestClient:
    app = create_executor_app(
        token=TOKEN,
        driver=driver,
        expected_digest=digest,
        store=store or JsonlRecordStore(tmp_path / "records.jsonl"),
    )
    return TestClient(app)


def post_task(client: TestClient, token: str = TOKEN, **overrides) -> object:
    body = {
        "user_id": "u1", "experiment_id": "exp1", "task_id": "t1",
        "language": "python", "code": "print('hello')", "timeout_seconds": 5,
    }
    body.update(overrides)
    return client.post(
        "/v1/executions", content=json.dumps(body),
        headers={"Content-Type": "application/json", "X-Execution-Token": token},
    )


def test_healthz_reports_engine_and_digest_gate(tmp_path) -> None:
    client = make_client(tmp_path, FakeDriver(engine=None), digest=None)
    resp = client.get("/healthz")
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "ok"
    assert data["engine_available"] is False
    assert data["image_digest_locked"] is False


def test_missing_or_wrong_token_rejected(tmp_path) -> None:
    client = make_client(tmp_path, FakeDriver())
    resp = post_task(client, token="")
    assert resp.status_code == 401
    resp = post_task(client, token="wrong-token")
    assert resp.status_code == 401


def test_empty_token_refuses_service_startup() -> None:
    with pytest.raises(ValueError, match="拒绝启动"):
        create_executor_app(token="", driver=FakeDriver())


def test_successful_execution_and_record(tmp_path) -> None:
    driver = FakeDriver()
    store = JsonlRecordStore(tmp_path / "records.jsonl")
    client = make_client(tmp_path, driver, store=store)
    resp = post_task(client)
    assert resp.status_code == 200, resp.text
    data = resp.json()
    assert data["status"] == "completed"
    assert data["exit_code"] == 0
    assert data["stdout"] == "hello\n"
    records = store.read_all()
    assert len(records) == 1
    assert records[0].user_id == "u1"
    assert records[0].experiment_id == "exp1"
    assert records[0].task_id == "t1"
    assert records[0].status == "completed"


def test_request_constraints_rejected_before_execution(tmp_path) -> None:
    driver = FakeDriver()
    client = make_client(tmp_path, driver)
    bad_bodies = [
        {"language": "bash"},
        {"code": "   "},
        {"code": "x" * 70000},
        {"timeout_seconds": 60},
        {"user_id": ""},
        {"task_id": ""},
    ]
    for override in bad_bodies:
        resp = post_task(client, **override)
        # 400 = 服务端业务校验拒绝；422 = pydantic 字段约束拒绝；两者都未触达容器
        assert resp.status_code in (400, 422), (override, resp.text)
    assert driver.specs == []  # 非法请求从未触达容器


def test_fail_closed_outcome_recorded(tmp_path) -> None:
    store = JsonlRecordStore(tmp_path / "records.jsonl")
    client = make_client(tmp_path, FakeDriver(engine=None))
    resp = post_task(client)
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "error"
    assert data["failure_kind"] == "docker_unavailable"
    assert len(store.read_all()) == 1


def test_digest_locked_false_blocks_execution(tmp_path) -> None:
    driver = FakeDriver()
    client = make_client(tmp_path, driver, digest=None)
    resp = post_task(client)
    data = resp.json()
    assert data["failure_kind"] == "image_digest_not_locked"
    assert driver.specs == []


# ---------- 业务侧客户端（连接失败 fail-closed）----------


def test_client_fails_closed_when_service_unreachable(tmp_path) -> None:
    c = ExecutorServiceClient(base_url="http://127.0.0.1:1", token=TOKEN, timeout_seconds=1)
    with pytest.raises(DockerUnavailableError, match="不可达"):
        c.submit(ExecutionSubmission(user_id="u", experiment_id="e", task_id="t", code="1"))


def test_client_requires_token() -> None:
    with pytest.raises(ExecutorServiceError, match="fail-closed"):
        ExecutorServiceClient(base_url="http://127.0.0.1:8101", token="")


# ---------- 架构边界静态检查 ----------


def test_business_main_never_imports_executor_service_or_sdk() -> None:
    """FastAPI 业务进程不得持有 Docker 能力：main.py 不导入执行服务/适配器/SDK。"""
    main_src = (Path(__file__).resolve().parents[1] / "app" / "main.py").read_text(encoding="utf-8")
    assert "executor" not in main_src
    assert "docker" not in main_src.lower()


def test_service_app_module_import_does_not_load_docker_sdk() -> None:
    """service_app 模块导入本身不加载 docker SDK（惰性装配只在 main() 发生）。"""
    adapter = (Path(__file__).resolve().parents[1] / "app" / "services" / "executor" / "service_app.py")
    top = adapter.read_text(encoding="utf-8").split("\ndef ")[0]
    assert "import docker" not in top


def test_service_app_never_uses_subprocess(tmp_path) -> None:
    src_dir = Path(__file__).resolve().parents[1] / "app" / "services" / "executor"
    for name in ("service_app.py", "client.py", "records.py"):
        src = (src_dir / name).read_text(encoding="utf-8")
        assert "import subprocess" not in src
        assert "os.system" not in src
