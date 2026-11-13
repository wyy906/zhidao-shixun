"""实验运行接口测试（V2-04 C1：主业务 API → 执行服务客户端接入）。

全部为 Mock/依赖注入测试（FakeExecutorClient）：验证业务 API 的接入、错误码
映射与访问控制；不构成真实 Docker 执行验证（真实 Docker 集成测试保持 BLOCKED）。
"""

import json
import sys
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.api.v1.executions import (
    get_executor_client,
    get_experiments_repository,
    get_settings_dep,
)
from app.core.config import Settings
from app.experiments.repository import ExperimentsRepository
from app.main import create_app
from app.services.executor.base import DockerUnavailableError
from app.services.executor.client import ExecutorServiceError

sys.path.insert(0, str(Path(__file__).resolve().parent))
from helpers_experiment import make_valid_experiment  # noqa: E402

DEV_TOKEN = "dev-token-123"
EXPERIMENT_ID = "py-web-demo"
RUN_URL = f"/api/v1/experiments/{EXPERIMENT_ID}/runs"


def ok_payload(**overrides):
    """执行服务成功响应的标准形态（与 service_app.py 返回字段一致）。"""
    payload = {
        "record_id": "rec-ok-1",
        "status": "completed",
        "exit_code": 0,
        "stdout": "hello from sandbox\n",
        "stderr": "",
        "timed_out": False,
        "truncated": False,
        "failure_kind": None,
        "failure_detail": None,
        "container_id": "cid-1",
        "duration_ms": 42,
        "created_at": "2026-11-13T00:00:00+00:00",
    }
    payload.update(overrides)
    return payload


class FakeExecutorClient:
    """脚本化假客户端：记录提交内容，返回预设响应或抛出预设异常。"""

    def __init__(self, responses=None, submit_error=None, health_response=None):
        self.responses = list(responses or [])
        self.submit_error = submit_error
        self.health_response = health_response
        self.submissions = []

    def submit(self, submission):
        self.submissions.append(submission)
        if self.submit_error is not None:
            raise self.submit_error
        if self.responses:
            return self.responses.pop(0)
        return ok_payload()

    def health(self):
        if isinstance(self.health_response, Exception):
            raise self.health_response
        return dict(self.health_response or {})


def make_settings(**overrides) -> Settings:
    defaults = dict(dev_api_token=DEV_TOKEN, executor_token="exec-token")
    defaults.update(overrides)
    return Settings(_env_file=None, **defaults)


def make_app(fake=None, settings=None, repo=None) -> TestClient:
    app = create_app()
    app.dependency_overrides[get_settings_dep] = lambda: (
        settings or make_settings()
    )
    if fake is not None:
        app.dependency_overrides[get_executor_client] = lambda: fake
    if repo is not None:
        app.dependency_overrides[get_experiments_repository] = lambda: repo
    return TestClient(app)


@pytest.fixture()
def repo_with_experiment(tmp_path):
    exp_dir = tmp_path / "experiments"
    exp_dir.mkdir()
    data = make_valid_experiment()
    data["experiment_id"] = EXPERIMENT_ID
    (exp_dir / "demo.json").write_text(
        json.dumps(data, ensure_ascii=False), encoding="utf-8"
    )
    return ExperimentsRepository(directory=exp_dir)


def post_run(http, code="print('hello')", exp=EXPERIMENT_ID, token=DEV_TOKEN, **overrides):
    headers = {"X-Dev-Token": token} if token is not None else {}
    payload = {"code": code, "timeout_seconds": 5}
    payload.update(overrides)
    payload = {k: v for k, v in payload.items() if v is not None}  # code=None → 缺字段
    return http.post(f"/api/v1/experiments/{exp}/runs", json=payload, headers=headers)


# ---------- 正常运行 ----------


def test_run_success_returns_real_result(repo_with_experiment):
    fake = FakeExecutorClient()
    http = make_app(fake, repo=repo_with_experiment)
    resp = post_run(http)
    assert resp.status_code == 200
    body = resp.json()
    assert body["execution_id"] == "rec-ok-1"
    assert body["status"] == "completed"
    assert body["exit_code"] == 0
    assert body["stdout"] == "hello from sandbox\n"
    assert body["stderr"] == ""
    assert body["duration_ms"] == 42
    assert body["experiment_id"] == EXPERIMENT_ID
    assert body["task_id"] == "run"
    # 业务 API 以固定开发模式用户提交，元数据完整传递
    assert fake.submissions[0].user_id == "dev-local"
    assert fake.submissions[0].experiment_id == EXPERIMENT_ID
    assert fake.submissions[0].language == "python"


# ---------- Python 语法错误 / 运行时异常（真实执行语义：非零退出码是运行结果）----------


def test_syntax_error_reports_nonzero_exit_not_infra_error(repo_with_experiment):
    fake = FakeExecutorClient(responses=[ok_payload(
        status="completed", exit_code=1, stdout="",
        stderr="  File \"<string>\", line 1\ndef broken(:\n             ^\nSyntaxError: invalid syntax\n",
    )])
    http = make_app(fake, repo=repo_with_experiment)
    resp = post_run(http, code="def broken(:")
    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] == "completed"
    assert body["exit_code"] == 1
    assert "SyntaxError" in body["stderr"]
    assert body["failure_kind"] is None  # 语法错误是运行结果，不是执行器故障


def test_runtime_exception_reports_stderr_and_exit_code(repo_with_experiment):
    fake = FakeExecutorClient(responses=[ok_payload(
        status="completed", exit_code=1, stdout="before\n",
        stderr="Traceback (most recent call last):\nZeroDivisionError: division by zero\n",
    )])
    http = make_app(fake, repo=repo_with_experiment)
    resp = post_run(http, code="print('before')\nx = 1 / 0")
    assert resp.status_code == 200
    body = resp.json()
    assert body["exit_code"] == 1
    assert body["stdout"] == "before\n"
    assert "ZeroDivisionError" in body["stderr"]


# ---------- 超时 ----------


def test_timeout_is_reported_as_timeout_status(repo_with_experiment):
    fake = FakeExecutorClient(responses=[ok_payload(
        status="timeout", exit_code=None, stdout="", stderr="",
        timed_out=True, container_id="cid-t",
    )])
    http = make_app(fake, repo=repo_with_experiment)
    resp = post_run(http, code="while True: pass", timeout_seconds=5)
    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] == "timeout"
    assert body["timed_out"] is True
    assert body["exit_code"] is None


# ---------- 输出截断 ----------


def test_truncated_output_is_passed_through(repo_with_experiment):
    big_stdout = "x" * 65536
    fake = FakeExecutorClient(responses=[ok_payload(
        status="completed", exit_code=0, stdout=big_stdout, truncated=True,
    )])
    http = make_app(fake, repo=repo_with_experiment)
    resp = post_run(http, code="print('x' * 100000)")
    assert resp.status_code == 200
    body = resp.json()
    assert body["truncated"] is True
    assert body["stdout"] == big_stdout  # 执行服务已截断，业务 API 不再放大


# ---------- 执行服务不可用 / Docker 未就绪 ----------


def test_executor_unreachable_maps_to_503_with_hint(repo_with_experiment):
    fake = FakeExecutorClient(submit_error=DockerUnavailableError("connection refused"))
    http = make_app(fake, repo=repo_with_experiment)
    resp = post_run(http)
    assert resp.status_code == 503
    error = resp.json()["error"]
    assert error["code"] == "executor_unavailable"
    assert "Docker" in error["message"]
    assert error["details"]["install_hint"]


def test_docker_unavailable_outcome_maps_to_503_not_success(repo_with_experiment):
    """执行服务返回 docker_unavailable 失败 → 业务 API 绝不伪装执行成功。"""
    fake = FakeExecutorClient(responses=[ok_payload(
        status="error", exit_code=None, stdout="", stderr="",
        failure_kind="docker_unavailable",
        failure_detail="Docker 不可用（无宿主机回退）",
    )])
    http = make_app(fake, repo=repo_with_experiment)
    resp = post_run(http)
    assert resp.status_code == 503
    error = resp.json()["error"]
    assert error["code"] == "executor_unavailable"
    assert "fail-closed" in error["message"]


def test_image_digest_not_locked_maps_to_503(repo_with_experiment):
    fake = FakeExecutorClient(responses=[ok_payload(
        status="error", failure_kind="image_digest_not_locked",
        failure_detail="digest pending",
    )])
    http = make_app(fake, repo=repo_with_experiment)
    resp = post_run(http)
    assert resp.status_code == 503
    assert resp.json()["error"]["code"] == "executor_image_not_locked"


def test_other_infra_failure_maps_to_502(repo_with_experiment):
    fake = FakeExecutorClient(responses=[ok_payload(
        status="error", failure_kind="container_create_failed",
        failure_detail="create failed: no such image",
    )])
    http = make_app(fake, repo=repo_with_experiment)
    resp = post_run(http)
    assert resp.status_code == 502
    error = resp.json()["error"]
    assert error["code"] == "executor_infra_error"
    assert error["details"]["failure_kind"] == "container_create_failed"


def test_executor_http_error_maps_to_502(repo_with_experiment):
    fake = FakeExecutorClient(submit_error=ExecutorServiceError("执行服务返回 HTTP 401"))
    http = make_app(fake, repo=repo_with_experiment)
    resp = post_run(http)
    assert resp.status_code == 502
    assert resp.json()["error"]["code"] == "executor_service_error"


# ---------- 非法请求 ----------


@pytest.mark.parametrize(
    "payload",
    [
        {"code": None, "timeout_seconds": 5},  # 缺 code
        {"code": ""},  # 空 code
        {"code": "print(1)", "timeout_seconds": 0},  # 超时下界
        {"code": "print(1)", "timeout_seconds": 21},  # 超时上界
        {"code": "print(1)", "task_id": ""},  # 空 task_id
    ],
)
def test_invalid_requests_rejected(repo_with_experiment, payload):
    http = make_app(FakeExecutorClient(), repo=repo_with_experiment)
    resp = post_run(http, **payload)
    assert resp.status_code == 422


def test_oversized_code_rejected_cleanly(repo_with_experiment):
    http = make_app(FakeExecutorClient(), repo=repo_with_experiment)
    resp = post_run(http, code="x" * 70000)
    assert resp.status_code == 400
    assert resp.json()["error"]["code"] == "code_too_large"


# ---------- 实验访问控制 ----------


def test_unknown_experiment_rejected(repo_with_experiment):
    http = make_app(FakeExecutorClient(), repo=repo_with_experiment)
    resp = post_run(http, exp="no-such-experiment")
    assert resp.status_code == 404
    assert resp.json()["error"]["code"] == "experiment_not_found"


def test_missing_dev_token_is_unauthorized(repo_with_experiment):
    http = make_app(FakeExecutorClient(), repo=repo_with_experiment)
    resp = post_run(http, token=None)
    assert resp.status_code == 401
    assert resp.json()["error"]["code"] == "dev_auth_required"


def test_wrong_dev_token_is_unauthorized(repo_with_experiment):
    http = make_app(FakeExecutorClient(), repo=repo_with_experiment)
    resp = post_run(http, token="wrong-token")
    assert resp.status_code == 401


def test_dev_mode_not_configured_closes_endpoint():
    """未配置开发模式令牌 → 接口整体关闭（fail-closed，防匿名任意执行）。"""
    http = make_app(None, settings=make_settings(dev_api_token=""), repo=None)
    resp = post_run(http)
    assert resp.status_code == 503
    assert resp.json()["error"]["code"] == "executor_dev_mode_disabled"


def test_executor_token_not_configured_rejects_submission(repo_with_experiment):
    settings = make_settings(executor_token="")
    http = make_app(None, settings=settings, repo=repo_with_experiment)
    resp = post_run(http)
    assert resp.status_code == 503
    assert resp.json()["error"]["code"] == "executor_not_configured"


# ---------- 执行器状态探测 ----------


def test_executor_status_reports_docker_not_ready_honestly():
    """本机无 Docker 的真实形态：服务可达但 engine_available=False，如实报告。"""
    fake = FakeExecutorClient(health_response={
        "engine_available": False, "image_digest_locked": False,
        "docker_integration_tests": "BLOCKED（等待真实 Docker 环境）",
    })
    http = make_app(fake)
    resp = http.get("/api/v1/executor/status", headers={"X-Dev-Token": DEV_TOKEN})
    assert resp.status_code == 200
    body = resp.json()
    assert body["executor_service"] == "reachable"
    assert body["engine_available"] is False
    assert body["docker_environment_ready"] is False
    assert "BLOCKED" in body["docker_integration_tests"]


def test_executor_status_unreachable_maps_to_503():
    fake = FakeExecutorClient(health_response=DockerUnavailableError("unreachable"))
    http = make_app(fake)
    resp = http.get("/api/v1/executor/status", headers={"X-Dev-Token": DEV_TOKEN})
    assert resp.status_code == 503
    error = resp.json()["error"]
    assert error["code"] == "executor_unavailable"
    assert error["details"]["install_hint"]
