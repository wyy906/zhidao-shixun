"""沙箱管理器接口测试（FakeRunner，无 Docker 依赖）

验证：管理接口认证、输入校验、超时上限、任务状态流转、取消、重启后任务不存在
（业务后端会把这种情况按“沙箱不可用”安全失败）。
"""
import time

import pytest
from fastapi.testclient import TestClient

from sandbox_manager.config import ManagerConfig
from sandbox_manager.container_spec import SandboxLimits
from sandbox_manager.runner import SandboxError
from sandbox_manager.server import create_app

TOKEN = "test-token"
IMAGE = "zd-sandbox-python@sha256:" + "b" * 64
HEADERS = {"X-Sandbox-Token": TOKEN}


class FakeRunner:
    def __init__(self, result=None, ready_error: SandboxError | None = None, block=False):
        self.result = dict(result or {
            "status": "succeeded", "stdout": "ok\n", "stderr": "",
            "exit_code": 0, "duration_ms": 3,
        })
        self.ready_error = ready_error
        self.block = block
        self.calls: list[tuple[str, int]] = []

    def check_ready(self):
        if self.ready_error:
            raise self.ready_error
        return {"docker": True, "image": IMAGE}

    def limits(self):
        return SandboxLimits(max_concurrent=2)

    def run_job(self, code, timeout, cancel_event=None):
        self.calls.append((code, timeout))
        if self.block:
            while not cancel_event.is_set():
                time.sleep(0.02)
            return {"status": "cancelled", "stdout": "", "stderr": "任务已取消。",
                    "exit_code": -1, "duration_ms": 20}
        return dict(self.result)


def _config(**overrides) -> ManagerConfig:
    data = {"token": TOKEN, "image": IMAGE, "timeout_seconds": 2, "max_concurrent": 2}
    data.update(overrides)
    return ManagerConfig(**data)


def _app(runner):
    return TestClient(create_app(runner=runner, config=_config()))


def _wait(client: TestClient, job_id: str, deadline: float = 3.0) -> dict:
    end = time.monotonic() + deadline
    while time.monotonic() < end:
        body = client.get(f"/v1/jobs/{job_id}", headers=HEADERS).json()
        if body["status"] in {"succeeded", "failed", "timeout", "resource_exceeded", "cancelled"}:
            return body
        time.sleep(0.05)
    raise AssertionError("任务未在预期时间内结束")


def test_requires_manager_token():
    client = _app(FakeRunner())
    assert client.get("/health").status_code == 401
    assert client.post("/v1/jobs", json={"code": "print(1)"}).status_code == 401
    assert client.get("/health", headers={"X-Sandbox-Token": "wrong"}).status_code == 401


def test_invalid_configuration_refuses_to_start():
    """没有管理令牌 / 镜像未固定 digest 时，管理器直接拒绝启动"""
    with pytest.raises(ValueError):
        create_app(runner=FakeRunner(), config=_config(token=""))
    with pytest.raises(ValueError):
        create_app(runner=FakeRunner(), config=_config(image="python:3.12-slim"))


def test_health_reports_ready():
    resp = _app(FakeRunner()).get("/health", headers=HEADERS)
    assert resp.status_code == 200
    assert resp.json()["status"] == "ok"


def test_health_reports_unavailable():
    client = _app(FakeRunner(ready_error=SandboxError("docker_unavailable")))
    resp = client.get("/health", headers=HEADERS)
    assert resp.status_code == 503
    assert resp.json()["detail"]["error"] == "docker_unavailable"


def test_submit_and_poll_result():
    runner = FakeRunner()
    client = _app(runner)
    resp = client.post("/v1/jobs", json={"code": "print('hi')", "timeout": 1}, headers=HEADERS)
    assert resp.status_code == 202
    body = _wait(client, resp.json()["job_id"])
    assert body["status"] == "succeeded"
    assert body["stdout"] == "ok\n"
    assert runner.calls[-1][0] == "print('hi')"


def test_timeout_is_clamped_to_admin_limit():
    runner = FakeRunner()
    client = _app(runner)
    client.post("/v1/jobs", json={"code": "print(1)", "timeout": 999}, headers=HEADERS)
    time.sleep(0.1)
    assert runner.calls[-1][1] == _config().timeout_seconds


def test_rejects_empty_and_oversize_code():
    client = _app(FakeRunner())
    assert client.post("/v1/jobs", json={"code": "   "}, headers=HEADERS).status_code == 400
    oversize = "a" * (_config().input_bytes + 1)
    assert client.post("/v1/jobs", json={"code": oversize}, headers=HEADERS).status_code == 400


def test_submit_refused_when_docker_unavailable():
    client = _app(FakeRunner(ready_error=SandboxError("docker_unavailable")))
    resp = client.post("/v1/jobs", json={"code": "print(1)"}, headers=HEADERS)
    assert resp.status_code == 503
    assert resp.json()["detail"]["error"] == "docker_unavailable"


def test_cancel_running_job():
    client = _app(FakeRunner(block=True))
    job_id = client.post("/v1/jobs", json={"code": "print(1)"}, headers=HEADERS).json()["job_id"]
    time.sleep(0.1)
    resp = client.delete(f"/v1/jobs/{job_id}", headers=HEADERS)
    assert resp.status_code == 200
    body = _wait(client, job_id)
    assert body["status"] == "cancelled"


def test_unknown_job_returns_404():
    client = _app(FakeRunner())
    assert client.get("/v1/jobs/nope", headers=HEADERS).status_code == 404
    assert client.delete("/v1/jobs/nope", headers=HEADERS).status_code == 404


def test_restart_loses_previous_jobs():
    """管理器重启后旧 job 不存在 → 业务后端会按不可用安全失败"""
    runner = FakeRunner()
    client = _app(runner)
    job_id = client.post("/v1/jobs", json={"code": "print(1)"}, headers=HEADERS).json()["job_id"]
    _wait(client, job_id)

    restarted = _app(FakeRunner())
    assert restarted.get(f"/v1/jobs/{job_id}", headers=HEADERS).status_code == 404


def test_configuration_rejects_unpinned_image():
    with pytest.raises(ValueError):
        ManagerConfig(token=TOKEN, image="python:3.12-slim").validate()
    with pytest.raises(ValueError):
        ManagerConfig(token="", image=IMAGE).validate()
