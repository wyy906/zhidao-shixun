"""代码执行沙箱接口测试

全部使用 FakeSandbox 替换真实沙箱管理器：
  - 验证业务后端的校验、任务落库、状态映射、权限隔离与安全失败；
  - **不**在业务后端执行任何学生代码（真实隔离需在 Linux 执行节点验证，
    见 sandbox_manager/scripts/verify_isolation.py 与 TEST_REPORT.md）。
"""
import uuid

from app.api.v1.routers import code as code_router
from app.core.config import settings
from app.core.security import hash_password
from app.main import _fail_interrupted_tasks, app
from app.models import CodeTask, User
from app.services.sandbox_client import (
    SAFE_UNAVAILABLE_MESSAGE,
    SandboxBusy,
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

    def __init__(self, result=None, submit_error=False, poll_error=False,
                 poll_exception=None, cancel_error=False, missing_job_id=False,
                 submit_busy=False):
        self.result = dict(result or SUCCESS_RESULT)
        self.submit_error = submit_error
        self.poll_error = poll_error
        self.poll_exception = poll_exception
        self.cancel_error = cancel_error
        self.missing_job_id = missing_job_id
        self.submit_busy = submit_busy
        self.submitted: list[tuple[str, int]] = []
        self.cancelled: list[str] = []

    def submit(self, code, timeout):
        self.submitted.append((code, timeout))
        if self.submit_busy:
            raise SandboxBusy("queue full")
        if self.submit_error:
            raise SandboxUnavailable("manager down")
        job_id = "" if self.missing_job_id else "job-" + uuid.uuid4().hex
        return {"job_id": job_id, "status": "queued"}

    def get_job(self, job_id):
        if self.poll_error:
            raise SandboxUnavailable("manager down")
        if self.poll_exception:
            raise self.poll_exception
        return dict(self.result)

    def cancel(self, job_id):
        self.cancelled.append(job_id)
        if self.cancel_error:
            raise SandboxUnavailable("manager down")
        return {"job_id": job_id, "status": "cancelled"}

    # 路由使用异步接口，避免阻塞事件循环
    async def asubmit(self, code, timeout):
        return self.submit(code, timeout)

    async def aget_job(self, job_id):
        return self.get_job(job_id)

    async def acancel(self, job_id):
        return self.cancel(job_id)


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


def test_run_endpoint_is_async():
    """异步路由：轮询等待不阻塞 FastAPI 事件循环"""
    import inspect

    assert inspect.iscoroutinefunction(code_router.run_code)


# ===========================================================================
# 学生端错误脱敏
# ===========================================================================
def test_student_cannot_see_internal_error_details(
    client, student_headers, teacher_headers, db_session, users
):
    secret = (
        "docker inspect /srv/zd-sandbox/secrets.json failed; image "
        "zd-sandbox-python@sha256:" + "e" * 64
    )
    task = CodeTask(
        id=uuid.uuid4().hex,
        user_id=users["student"]["id"],
        status="failed",
        timeout_seconds=10,
        error_code="container_error",
        error_message=secret,
    )
    db_session.add(task)
    db_session.commit()

    own = client.get(f"/api/v1/code/tasks/{task.id}", headers=student_headers)
    assert own.status_code == 200
    body = own.json()
    assert body["error_message"] == code_router.SAFE_FAILED_MESSAGE
    assert "/srv/zd-sandbox" not in str(body)
    assert "sha256:" not in str(body)
    # 错误码是稳定标识，可以返回；不包含内部路径
    assert body["error_code"] == "container_error"

    # 教师通过权限检查后可查看内部诊断信息
    teacher = client.get(f"/api/v1/code/tasks/{task.id}", headers=teacher_headers)
    assert teacher.status_code == 200
    assert secret in teacher.json()["error_message"]


# ===========================================================================
# 异常收口：不留下永久 running
# ===========================================================================
def test_malformed_job_status_fails_task(client, student_headers, db_session):
    _use_sandbox(FakeSandbox({"status": "definitely-not-a-status"}))
    resp = _run(client, student_headers)
    assert resp.status_code == 503

    task = db_session.query(CodeTask).order_by(CodeTask.created_at.desc()).first()
    assert task.status == "failed"
    assert task.error_code == "sandbox_bad_response"


def test_poll_unexpected_exception_fails_task(client, student_headers, db_session):
    fake = FakeSandbox(poll_exception=RuntimeError("boom"))
    _use_sandbox(fake)
    resp = _run(client, student_headers)
    assert resp.status_code == 503
    assert resp.json()["detail"] == SAFE_UNAVAILABLE_MESSAGE
    # 提交成功后发生异常，必须尽力取消远端任务
    assert fake.cancelled

    task = db_session.query(CodeTask).order_by(CodeTask.created_at.desc()).first()
    assert task.status == "failed"
    assert task.error_code == "internal_error"
    assert "boom" not in (task.error_message or "")


def test_result_save_failure_closes_task(client, student_headers, db_session, monkeypatch):
    """模拟保存结果失败：不得假称成功，任务落为安全终态"""
    _use_sandbox(FakeSandbox())

    def _boom(*args, **kwargs):
        raise RuntimeError("db commit failed")

    monkeypatch.setattr(code_router, "_save_result", _boom)
    resp = _run(client, student_headers)
    assert resp.status_code == 503

    task = db_session.query(CodeTask).order_by(CodeTask.created_at.desc()).first()
    assert task.status in {"failed", "timeout"}
    assert task.error_code == "internal_error"


def test_missing_job_id_fails_closed(client, student_headers, db_session):
    _use_sandbox(FakeSandbox(missing_job_id=True))
    resp = _run(client, student_headers)
    assert resp.status_code == 503
    task = db_session.query(CodeTask).order_by(CodeTask.created_at.desc()).first()
    assert task.status == "failed"
    assert task.error_code == "sandbox_bad_response"


def test_sync_wait_timeout_with_cancel_failure_still_terminates(
    client, student_headers, db_session, monkeypatch
):
    fake = FakeSandbox({
        "status": "running", "stdout": "", "stderr": "",
        "exit_code": None, "duration_ms": None,
    }, cancel_error=True)
    _use_sandbox(fake)
    monkeypatch.setattr(settings, "sandbox_sync_wait_seconds", 0.05)

    resp = _run(client, student_headers)
    assert resp.status_code == 200
    assert resp.json()["status"] == "timeout"
    assert fake.cancelled  # 已尽力取消

    task = db_session.query(CodeTask).order_by(CodeTask.created_at.desc()).first()
    assert task.status == "timeout"


# ===========================================================================
# 并发保护
# ===========================================================================
def test_concurrency_guard_limits_global_and_per_user():
    guard = code_router.ConcurrencyGuard()
    assert guard.try_acquire(1, global_max=2, per_user_max=1) is True
    assert guard.try_acquire(1, global_max=2, per_user_max=1) is False
    assert guard.try_acquire(2, global_max=2, per_user_max=1) is True
    assert guard.try_acquire(3, global_max=2, per_user_max=1) is False
    guard.release(1)
    assert guard.try_acquire(1, global_max=2, per_user_max=1) is True


def test_concurrent_request_rejected_before_submit(
    client, student_headers, users, monkeypatch
):
    fake = FakeSandbox()
    _use_sandbox(fake)
    monkeypatch.setattr(settings, "code_max_concurrent_per_user", 1)
    code_router.guard.reset()
    student_id = users["student"]["id"]
    assert code_router.guard.try_acquire(student_id, 8, 1) is True
    try:
        resp = _run(client, student_headers)
        assert resp.status_code == 429
        assert resp.json()["detail"] == code_router.SAFE_BUSY_MESSAGE
        assert fake.submitted == []
    finally:
        code_router.guard.release(student_id)
        code_router.guard.reset()


# ===========================================================================
# 管理器队列满：429 不能被错误映射为 503
# ===========================================================================
def test_manager_queue_full_maps_to_429(client, student_headers, db_session):
    _use_sandbox(FakeSandbox(submit_busy=True))
    resp = _run(client, student_headers)
    assert resp.status_code == 429
    assert resp.json()["detail"] == code_router.SAFE_BUSY_MESSAGE

    task = db_session.query(CodeTask).order_by(CodeTask.created_at.desc()).first()
    assert task.status == "failed"
    assert task.error_code == "queue_full"
    # 学生接口只返回固定安全文案
    detail = client.get(f"/api/v1/code/tasks/{task.id}", headers=student_headers)
    assert detail.status_code == 200
    assert detail.json()["error_message"] == code_router.SAFE_FAILED_MESSAGE


# ===========================================================================
# 教师 / 管理员权限统一
# ===========================================================================
def _make_staff(db_session, username: str, role: str, password: str) -> None:
    db_session.add(User(
        username=username,
        hashed_password=hash_password(password),
        real_name=username,
        role=role,
    ))
    db_session.commit()


def _staff_headers(client, username: str, password: str) -> dict:
    resp = client.post("/api/v1/auth/login",
                       json={"username": username, "password": password})
    assert resp.status_code == 200, resp.text
    return {"Authorization": f"Bearer {resp.json()['token']}"}


def test_admin_and_teacher_share_task_visibility_rules(
    client, db_session, users
):
    secret = "docker error /srv/zd/secrets.json sha256:" + "a" * 64
    task = CodeTask(
        id=uuid.uuid4().hex,
        user_id=users["student"]["id"],
        status="failed",
        timeout_seconds=10,
        error_code="container_error",
        error_message=secret,
    )
    db_session.add(task)
    db_session.commit()

    _make_staff(db_session, "teacher02", "teacher", "teacher-pass-123")
    _make_staff(db_session, "admin01", "admin", "admin-pass-123")

    for username, password in (
        ("teacher02", "teacher-pass-123"),
        ("admin01", "admin-pass-123"),
    ):
        headers = _staff_headers(client, username, password)
        resp = client.get(f"/api/v1/code/tasks/{task.id}", headers=headers)
        assert resp.status_code == 200
        assert secret in resp.json()["error_message"]

    # 普通学生仍看不到内部细节，且不能查看他人任务
    student_headers = _staff_headers(client, "student01", "student-pass-123")
    resp = client.get(f"/api/v1/code/tasks/{task.id}", headers=student_headers)
    assert resp.status_code == 200
    assert secret not in str(resp.json())

    other = _staff_headers(client, "student02", "student-pass-123")
    assert client.get(
        f"/api/v1/code/tasks/{task.id}", headers=other
    ).status_code == 404
