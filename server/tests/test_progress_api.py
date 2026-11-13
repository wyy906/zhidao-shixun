"""步骤进度接口测试（V2-04E1：运行结果 → 验证器 → 状态机推进）。

全部 Mock/依赖注入测试（FakeExecutorClient），不构成真实 Docker 验证。
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
from app.api.v1.progress import get_progress_service
from app.core.config import Settings
from app.experiments.repository import ExperimentsRepository
from app.main import create_app
from app.services.executor.base import DockerUnavailableError
from app.services.progress import StepProgressService
import app.services.progress as progress_module

sys.path.insert(0, str(Path(__file__).resolve().parent))
from helpers_experiment import make_valid_experiment  # noqa: E402

DEV_TOKEN = "dev-token-123"
EXPERIMENT_ID = "py-web-demo"
SUBMIT_URL = f"/api/v1/experiments/{EXPERIMENT_ID}/steps/{{step_id}}/submit"


def ok_payload(**overrides):
    payload = {
        "record_id": "rec-1",
        "status": "completed",
        "exit_code": 0,
        "stdout": "",
        "stderr": "",
        "timed_out": False,
        "truncated": False,
        "failure_kind": None,
        "failure_detail": None,
        "container_id": "cid-1",
        "duration_ms": 11,
        "created_at": "2026-11-13T00:00:00+00:00",
    }
    payload.update(overrides)
    return payload


class FakeExecutorClient:
    def __init__(self, responses=None, submit_error=None):
        self.responses = list(responses or [])
        self.submit_error = submit_error
        self.submissions = []

    def submit(self, submission):
        self.submissions.append(submission)
        if self.submit_error is not None:
            raise self.submit_error
        if self.responses:
            return self.responses.pop(0)
        return ok_payload()


def make_settings(**overrides) -> Settings:
    defaults = dict(dev_api_token=DEV_TOKEN, executor_token="exec-token")
    defaults.update(overrides)
    return Settings(_env_file=None, **defaults)


def make_client(fake, tmp_path, *, two_steps: bool = True) -> TestClient:
    app = create_app()
    app.dependency_overrides[get_settings_dep] = lambda: make_settings()
    app.dependency_overrides[get_executor_client] = lambda: fake
    service = StepProgressService()  # 单实例：会话跨请求保持（与生产单例语义一致）
    app.dependency_overrides[get_progress_service] = lambda: service
    exp_dir = tmp_path / "experiments"
    exp_dir.mkdir(exist_ok=True)
    data = make_valid_experiment()
    data["experiment_id"] = EXPERIMENT_ID
    if not two_steps:
        data["steps"] = [data["steps"][0]]
        data["steps"][0]["depends_on"] = []
    (exp_dir / "demo.json").write_text(
        json.dumps(data, ensure_ascii=False), encoding="utf-8"
    )
    app.dependency_overrides[get_experiments_repository] = lambda: ExperimentsRepository(
        directory=exp_dir
    )
    return TestClient(app)


def submit(http, step_id="s1", token=DEV_TOKEN, code="print('ok')", **overrides):
    headers = {"X-Dev-Token": token} if token is not None else {}
    payload = {"code": code, "timeout_seconds": 5}
    payload.update(overrides)
    return http.post(
        f"/api/v1/experiments/{EXPERIMENT_ID}/steps/{step_id}/submit",
        json=payload,
        headers=headers,
    )


# ---------- 通过路径与依赖解锁 ----------


def test_pass_unlocks_downstream_blocked_step(tmp_path):
    """s1 验证通过 → s1 passed；s2 依赖全部满足 → blocked 解除为 pending。"""
    fake = FakeExecutorClient(responses=[ok_payload(stdout="done\n")])
    http = make_client(fake, tmp_path)
    resp = submit(http, "s1")
    assert resp.status_code == 200
    body = resp.json()
    assert body["progressed"] is True
    assert body["step_status"] == "passed"
    assert body["states"] == {"s1": "passed", "s2": "pending"}
    assert body["verify"]["outcome"] == "passed"


def test_stdout_contains_verifier_passes_on_step2(tmp_path):
    fake = FakeExecutorClient(responses=[
        ok_payload(),  # s1 通过
        ok_payload(stdout="hello world\n"),  # s2 输出包含 hello
    ])
    http = make_client(fake, tmp_path)
    submit(http, "s1")
    resp = submit(http, "s2", code="print('hello world')")
    assert resp.status_code == 200
    body = resp.json()
    assert body["step_status"] == "passed"
    assert body["verify"]["outcome"] == "passed"


# ---------- 失败与重试 ----------


def test_nonzero_exit_fails_step_and_feedback(tmp_path):
    fake = FakeExecutorClient(responses=[ok_payload(
        exit_code=1, stderr="ValueError\n",
    )])
    http = make_client(fake, tmp_path)
    resp = submit(http, "s1", code="raise ValueError")
    assert resp.status_code == 200
    body = resp.json()
    assert body["step_status"] == "failed"
    assert body["verify"]["outcome"] == "failed"
    assert "退出码" in body["verify"]["feedback"]
    assert body["run"]["stderr"] == "ValueError\n"


def test_resubmit_after_failure_can_pass(tmp_path):
    fake = FakeExecutorClient(responses=[
        ok_payload(exit_code=1),
        ok_payload(stdout="ok\n"),
    ])
    http = make_client(fake, tmp_path)
    first = submit(http, "s1", code="bad")
    assert first.json()["step_status"] == "failed"
    second = submit(http, "s1", code="good")
    assert second.status_code == 200
    body = second.json()
    assert body["step_status"] == "passed"
    assert body["states"] == {"s1": "passed", "s2": "pending"}


# ---------- uncertain 永不推进 ----------


def test_timeout_run_does_not_progress_step(tmp_path):
    """超时 → exit_code=None → python_exit_code_zero 求值 uncertain → 状态不变。"""
    fake = FakeExecutorClient(responses=[ok_payload(
        status="timeout", exit_code=None, timed_out=True,
    )])
    http = make_client(fake, tmp_path)
    resp = submit(http, "s1")
    assert resp.status_code == 200
    body = resp.json()
    assert body["verify"]["outcome"] == "uncertain"
    assert body["progressed"] is False
    assert body["step_status"] == "pending"  # 状态保持不变


def test_evaluator_exception_is_fail_closed_uncertain(tmp_path, monkeypatch):
    """验证器求值异常 → uncertain → 不推进（fail-closed）。"""
    from zhidao_contracts import VerifyOutcome, VerifyResult

    def boom(verifier_type, params, actual, *, step_id):
        return VerifyResult(
            step_id=step_id, outcome=VerifyOutcome.UNCERTAIN,
            confidence=0.0, feedback="求值异常", evidence={},
        )

    monkeypatch.setattr(progress_module, "evaluate_verifier", boom)
    fake = FakeExecutorClient()
    http = make_client(fake, tmp_path)
    resp = submit(http, "s1")
    body = resp.json()
    assert body["verify"]["outcome"] == "uncertain"
    assert body["step_status"] == "pending"
    assert body["progressed"] is False


# ---------- 访问与状态保护 ----------


def test_blocked_step_cannot_submit_before_dependencies(tmp_path):
    """s2 依赖未通过 → 409 dependencies_not_satisfied，状态不变。"""
    fake = FakeExecutorClient()
    http = make_client(fake, tmp_path)
    resp = submit(http, "s2", code="print('hello world')")
    assert resp.status_code == 409
    assert resp.json()["error"]["code"] == "dependencies_not_satisfied"


def test_terminal_step_resubmission_rejected(tmp_path):
    fake = FakeExecutorClient(responses=[ok_payload(), ok_payload()])
    http = make_client(fake, tmp_path)
    submit(http, "s1")
    resp = submit(http, "s1")
    assert resp.status_code == 409
    assert resp.json()["error"]["code"] == "step_already_terminal"


def test_unknown_step_404(tmp_path):
    http = make_client(FakeExecutorClient(), tmp_path)
    resp = submit(http, "no-such-step")
    assert resp.status_code == 404
    assert resp.json()["error"]["code"] == "step_not_found"


def test_infra_error_leaves_state_unchanged(tmp_path):
    fake = FakeExecutorClient(submit_error=DockerUnavailableError("refused"))
    http = make_client(fake, tmp_path)
    resp = submit(http, "s1")
    assert resp.status_code == 503
    assert resp.json()["error"]["code"] == "executor_unavailable"
    progress = http.get(f"/api/v1/experiments/{EXPERIMENT_ID}/progress").json()
    assert progress["states"] == {"s1": "pending", "s2": "blocked"}


def test_missing_dev_token_unauthorized(tmp_path):
    http = make_client(FakeExecutorClient(), tmp_path)
    resp = submit(http, "s1", token=None)
    assert resp.status_code == 401


def test_oversized_code_rejected(tmp_path):
    http = make_client(FakeExecutorClient(), tmp_path)
    resp = submit(http, "s1", code="x" * 70000)
    assert resp.status_code == 400


# ---------- 进度读取与重置 ----------


def test_progress_view_and_reset(tmp_path):
    fake = FakeExecutorClient(responses=[ok_payload()])
    http = make_client(fake, tmp_path)
    initial = http.get(f"/api/v1/experiments/{EXPERIMENT_ID}/progress").json()
    assert initial["states"] == {"s1": "pending", "s2": "blocked"}
    submit(http, "s1")
    after = http.get(f"/api/v1/experiments/{EXPERIMENT_ID}/progress").json()
    assert after["states"]["s1"] == "passed"
    reset = http.post(
        f"/api/v1/experiments/{EXPERIMENT_ID}/progress/reset",
        headers={"X-Dev-Token": DEV_TOKEN},
    ).json()
    assert reset["states"] == {"s1": "pending", "s2": "blocked"}
