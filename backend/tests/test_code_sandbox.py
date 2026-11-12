"""代码执行沙箱接口测试

全部使用 FakeSandbox 替换真实沙箱管理器：
  - 验证业务后端的校验、任务落库、状态映射、权限隔离与安全失败；
  - **不**在业务后端执行任何学生代码（真实隔离需在 Linux 执行节点验证，
    见 sandbox_manager/scripts/verify_isolation.py 与 TEST_REPORT.md）。
"""
import uuid

from app.api.v1.routers import code as code_router
from app.core.config import settings
from app.main import _fail_interrupted_tasks, app
from app.models import CodeTask
from app.services.sandbox_client import (
    SAFE_UNAVAILABLE_MESSAGE,
    SandboxUnavailable,
    get_sandbox_client,
)

SUCCESS_RESULT = {
    "status": "succeeded",
    "stdout": "hello\n",
    "stderr": "",
    "exit_code": 0,
    "duration_ms": 12,
}


class FakeSandbox:
    """可控的假沙箱管理器"""

    def __init__(self, result=None, submit_error=False, poll_error=False):
        self.result = dict(result or SUCCESS_RESULT)
        self.submit_error = submit_error
        self.poll_error = poll_error
        self.submitted: list[tuple[str, int]] = []
        self.cancelled: list[str] = []

    def submit(self, code, timeout):
        self.submitted.append((code, timeout))
        if self.submit_error:
            raise SandboxUnavailable("manager down")
        return {"job_id": "job-" + uuid.uuid4().hex, "status": "queued"}

    def get_job(self, job_id):
        if self.poll_error:
            raise SandboxUnavailable("manager down")
        return dict(self.result)

    def cancel(self, job_id):
        self.cancelled.append(job_id)
        return {"job_id": job_id, "status": "cancelled"}


def _use_sandbox(fake: FakeSandbox) -> None:
    app.dependency_overrides[get_sandbox_client] = lambda: fake


def _run(client, headers, code="print('hi')", timeout=None):
    payload = {"code": code}
    if timeout is not None:
        payload["timeout"] = timeout
    return client.post("/api/v1/code/run", json=payload, headers=headers)


# ===========================================================================
# 功能与兼容
# ===========================================================================
def test_requires_login(client):
    resp = client.post("/api/v1/code/run", json={"code": "print(1)"})
    assert resp.status_code == 401


def test_empty_code_rejected(client, student_headers):
    _use_sandbox(FakeSandbox())
    resp = _run(client, student_headers, code="   ")
    assert resp.status_code == 400


def test_oversize_code_rejected(client, student_headers):
    fake = FakeSandbox()
    _use_sandbox(fake)
    resp = _run(client, student_headers, code="a" * (settings.code_max_input_bytes + 1))
    assert resp.status_code == 400
    assert fake.submitted == []


def test_success_returns_compatible_payload(client, student_headers, db_session):
    fake = FakeSandbox()
    _use_sandbox(fake)

    resp = _run(client, student_headers)
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["stdout"] == "hello\n"
    assert body["stderr"] == ""
    assert body["exit_code"] == 0
    assert body["duration_ms"] == 12
    assert body["timed_out"] is False
    assert body["status"] == "succeeded"
    assert len(body["task_id"]) == 32

    task = db_session.query(CodeTask).filter(CodeTask.id == body["task_id"]).first()
    assert task is not None
    assert task.status == "succeeded"
    assert task.exit_code == 0


def test_timeout_cannot_be_raised_by_student(client, student_headers):
    fake = FakeSandbox()
    _use_sandbox(fake)
    resp = _run(client, student_headers, timeout=30)
    assert resp.status_code == 200
    assert fake.submitted[-1][1] == settings.code_run_timeout_seconds


def test_resource_exceeded_maps_to_safe_message(client, student_headers):
    _use_sandbox(FakeSandbox({
        "status": "resource_exceeded",
        "stdout": "",
        "stderr": "",
        "exit_code": -1,
        "duration_ms": 30,
    }))
    resp = _run(client, student_headers)
    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] == "resource_exceeded"
    assert "资源使用超过限制" in body["stderr"]
    assert body["exit_code"] == -1


def test_large_output_is_clipped(client, student_headers):
    _use_sandbox(FakeSandbox({
        "status": "succeeded",
        "stdout": "A" * (settings.code_max_output_bytes * 2),
        "stderr": "",
        "exit_code": 0,
        "duration_ms": 5,
    }))
    resp = _run(client, student_headers)
    body = resp.json()
    assert len(body["stdout"].encode("utf-8")) <= settings.code_max_output_bytes + 100
    assert "已截断" in body["stdout"]


# ===========================================================================
# 安全失败：沙箱不可用时绝不本地执行 / 绝不降级
# ===========================================================================
def test_sandbox_unavailable_returns_503_and_never_executes_locally(
    client, student_headers, tmp_path
):
    marker = tmp_path / "local_execution_marker.txt"
    code = f"open({str(marker)!r}, 'w').write('executed locally')\n"
    _use_sandbox(FakeSandbox(submit_error=True))

    resp = _run(client, student_headers, code=code)
    assert resp.status_code == 503
    assert resp.json()["detail"] == SAFE_UNAVAILABLE_MESSAGE
    # 关键：代码没有在业务后端（或本机 subprocess）执行
    assert not marker.exists()


def test_manager_down_during_poll_returns_503(client, student_headers, db_session):
    _use_sandbox(FakeSandbox(poll_error=True))
    resp = _run(client, student_headers)
    assert resp.status_code == 503
    task = db_session.query(CodeTask).order_by(CodeTask.created_at.desc()).first()
    assert task is not None
    assert task.status == "failed"
    assert task.error_code == "sandbox_unavailable"


def test_execution_disabled_returns_503(client, student_headers, monkeypatch):
    _use_sandbox(FakeSandbox())
    monkeypatch.setattr(settings, "code_execution_enabled", False)
    resp = _run(client, student_headers)
    assert resp.status_code == 503
    assert resp.json()["detail"] == SAFE_UNAVAILABLE_MESSAGE


# ===========================================================================
# 任务查询与权限隔离
# ===========================================================================
def test_task_query_owner_teacher_and_other_student(
    client, student_headers, student2_headers, teacher_headers
):
    _use_sandbox(FakeSandbox())
    task_id = _run(client, student_headers).json()["task_id"]

    own = client.get(f"/api/v1/code/tasks/{task_id}", headers=student_headers)
    assert own.status_code == 200
    assert own.json()["task_id"] == task_id
    assert own.json()["status"] == "succeeded"

    # 其他学生：404（不泄露任务是否存在）
    other = client.get(f"/api/v1/code/tasks/{task_id}", headers=student2_headers)
    assert other.status_code == 404

    # 教师：可查看必要任务
    teacher = client.get(f"/api/v1/code/tasks/{task_id}", headers=teacher_headers)
    assert teacher.status_code == 200


def test_unknown_task_returns_404(client, student_headers):
    resp = client.get("/api/v1/code/tasks/" + "0" * 32, headers=student_headers)
    assert resp.status_code == 404


def test_restart_marks_unfinished_tasks_failed(db_session, users):
    running = CodeTask(id=uuid.uuid4().hex, user_id=users["student"]["id"],
                       status="running", timeout_seconds=10)
    queued = CodeTask(id=uuid.uuid4().hex, user_id=users["student"]["id"],
                      status="queued", timeout_seconds=10)
    done = CodeTask(id=uuid.uuid4().hex, user_id=users["student"]["id"],
                    status="succeeded", timeout_seconds=10)
    db_session.add_all([running, queued, done])
    db_session.commit()

    count = _fail_interrupted_tasks(db_session)
    assert count == 2
    db_session.refresh(running)
    db_session.refresh(queued)
    db_session.refresh(done)
    assert running.status == "failed" and running.error_code == "service_restarted"
    assert queued.status == "failed"
    # 已完成任务不受影响，更不会被当作“未完成但成功”
    assert done.status == "succeeded"


def test_extra_fields_rejected(client, student_headers):
    """学生不能通过请求参数指定镜像、网络模式或资源限制"""
    fake = FakeSandbox()
    _use_sandbox(fake)
    resp = client.post(
        "/api/v1/code/run",
        json={
            "code": "print(1)",
            "image": "evil:latest",
            "network_mode": "host",
            "memory_mb": 4096,
        },
        headers=student_headers,
    )
    assert resp.status_code == 422
    assert fake.submitted == []


def test_submitted_code_is_not_persisted():
    """任务表只保存状态与长度，不落库学生代码本体"""
    columns = set(CodeTask.__table__.columns.keys())
    assert "code" not in columns
    assert "code_b64" not in columns
    assert "code_length" in columns


def test_router_does_not_import_subprocess():
    """静态确认：沙箱版路由不再具备本机 subprocess 执行路径"""
    import inspect

    source = inspect.getsource(code_router)
    assert "import subprocess" not in source
    assert "subprocess.run" not in source
    assert "sys.executable" not in source
