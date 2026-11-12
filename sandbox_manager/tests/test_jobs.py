"""任务队列上限测试（无需 Docker）

验证：
  - 排队任务达到上限时立即拒绝（queue_full），不创建任务记录、不启动执行；
  - 任务开始 / 完成 / 取消后正确释放容量；
  - 并发提交不会突破上限；
  - 被拒绝的请求不会触发执行器（即不会创建容器）。
"""
import threading
import time

import pytest

from sandbox_manager.container_spec import SandboxLimits
from sandbox_manager.jobs import JobStore, QueueFullError

TERMINAL = {"succeeded", "failed", "timeout", "resource_exceeded", "cancelled"}


class BlockingRunner:
    def __init__(self) -> None:
        self.release = threading.Event()
        self.started = threading.Event()
        self.calls = 0
        self._lock = threading.Lock()

    def run_job(self, code, timeout, cancel_event=None, job_id=""):
        with self._lock:
            self.calls += 1
        self.started.set()
        self.release.wait(5)
        return {
            "status": "succeeded", "stdout": "ok", "stderr": "",
            "exit_code": 0, "duration_ms": 1,
        }


def _store(runner, **limits) -> JobStore:
    return JobStore(runner, SandboxLimits(max_concurrent=1, **limits))


def _wait_status(store: JobStore, job_id: str, timeout: float = 3.0) -> dict:
    end = time.monotonic() + timeout
    while time.monotonic() < end:
        job = store.get(job_id)
        if job and job["status"] in TERMINAL:
            return job
        time.sleep(0.02)
    raise AssertionError("任务未在预期时间内结束")


def test_queue_full_rejects_without_starting_execution():
    runner = BlockingRunner()
    store = _store(runner, max_pending=2)
    first = store.submit("print(1)", 1)
    assert runner.started.wait(2)

    second = store.submit("print(2)", 1)
    third = store.submit("print(3)", 1)
    with pytest.raises(QueueFullError) as exc:
        store.submit("print(4)", 1)
    assert exc.value.code == "queue_full"

    # 被拒绝的任务不占用记录，也没有额外的执行线程/容器
    assert len(store._jobs) == 3
    assert runner.calls == 1
    assert store.get(first["job_id"])["status"] == "running"
    assert store.get(second["job_id"])["status"] == "queued"
    assert store.get(third["job_id"])["status"] == "queued"
    runner.release.set()


def test_capacity_released_after_tasks_finish():
    runner = BlockingRunner()
    runner.release.set()  # 立即完成
    store = _store(runner, max_pending=1)

    first = store.submit("print(1)", 1)
    _wait_status(store, first["job_id"])
    second = store.submit("print(2)", 1)
    _wait_status(store, second["job_id"])
    third = store.submit("print(3)", 1)
    assert _wait_status(store, third["job_id"])["status"] == "succeeded"


def test_cancel_queued_job_releases_capacity():
    runner = BlockingRunner()
    store = _store(runner, max_pending=1)
    first = store.submit("print(1)", 1)
    assert runner.started.wait(2)
    queued = store.submit("print(2)", 1)
    with pytest.raises(QueueFullError):
        store.submit("print(3)", 1)

    cancelled = store.cancel(queued["job_id"])
    assert cancelled["status"] == "cancelled"

    accepted = store.submit("print(3)", 1)
    assert accepted["status"] in {"queued", "running"}
    runner.release.set()
    _wait_status(store, first["job_id"])


def test_concurrent_submissions_do_not_exceed_limit():
    runner = BlockingRunner()
    store = _store(runner, max_pending=2)
    accepted: list[str] = []
    rejected = 0

    def _submit(index: int) -> None:
        nonlocal rejected
        try:
            job = store.submit(f"print({index})", 1)
            accepted.append(job["job_id"])
        except QueueFullError:
            rejected += 1

    threads = [threading.Thread(target=_submit, args=(i,)) for i in range(10)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()

    # 1 个执行中 + 最多 2 个排队；并发下只会更少，绝不会更多
    assert 1 <= len(accepted) <= 3
    assert rejected == 10 - len(accepted)
    assert runner.calls <= 1  # 只有开始执行的任务才会进入 Docker 执行器
    runner.release.set()
    for job_id in accepted:
        _wait_status(store, job_id)
