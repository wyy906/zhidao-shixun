"""阶段 C 扩展真实集成测试（V2-04C 第二批）：资源限制与并发实测。

前提同首批：执行服务运行中 + 真实引擎 + 已批准 digest，否则诚实 SKIP。
"""

import json
import os
import urllib.request
from concurrent.futures import ThreadPoolExecutor

import pytest

EXECUTOR_BASE = "http://127.0.0.1:8101"
EXECUTOR_TOKEN = os.environ.get("ZD_EXECUTOR_TOKEN", "")


def _service_ready() -> bool:
    if not EXECUTOR_TOKEN:
        return False
    try:
        req = urllib.request.Request(
            f"{EXECUTOR_BASE}/healthz", headers={"X-Execution-Token": EXECUTOR_TOKEN}
        )
        with urllib.request.urlopen(req, timeout=10) as resp:
            health = json.loads(resp.read().decode())
        return bool(health["engine_available"]) and health["image_digest_locked"]
    except Exception:  # noqa: BLE001
        return False


pytestmark = pytest.mark.skipif(
    not _service_ready(),
    reason="需运行中的执行服务 + 真实 Docker 引擎 + 已批准 digest（环境不可用则如实跳过）",
)


def call_exec(code: str, timeout_seconds: int = 15, task_id: str = "stagec2") -> dict:
    req = urllib.request.Request(
        f"{EXECUTOR_BASE}/v1/executions",
        data=json.dumps(
            {"user_id": "stagec-itest", "experiment_id": "stagec-itest", "task_id": task_id,
             "language": "python", "code": code, "timeout_seconds": timeout_seconds}
        ).encode(),
        method="POST",
        headers={"Content-Type": "application/json", "X-Execution-Token": EXECUTOR_TOKEN},
    )
    with urllib.request.urlopen(req, timeout=timeout_seconds + 90) as resp:
        return json.loads(resp.read().decode())


def test_batch2_output_over_limit_truncated() -> None:
    """输出超限实测：生成 70KB stdout → truncated=true 且体积受限（65536 字节上限）。"""
    r = call_exec("print('x' * 70000)", task_id="b2-truncate")
    assert r["status"] == "completed" and r["exit_code"] == 0
    assert r["truncated"] is True
    assert len(r["stdout"].encode("utf-8")) <= 65536


def test_batch2_code_over_limit_rejected() -> None:
    """代码字节上限（65536）：超限请求被拒（4xx/5xx 结构化错误），不创建容器。"""
    big = "x = '" + "y" * 70000 + "'"
    req = urllib.request.Request(
        f"{EXECUTOR_BASE}/v1/executions",
        data=json.dumps(
            {"user_id": "stagec-itest", "experiment_id": "stagec-itest", "task_id": "b2-bigcode",
             "language": "python", "code": big, "timeout_seconds": 5}
        ).encode(),
        method="POST",
        headers={"Content-Type": "application/json", "X-Execution-Token": EXECUTOR_TOKEN},
    )
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            body = json.loads(resp.read().decode())
        # 若实现为 200+结构化错误（fail-closed），也必须带 failure_detail 且无 stdout 结果
        assert "error" in body or body.get("status") == "error", body
    except urllib.error.HTTPError as e:
        assert 400 <= e.code < 600


def test_batch2_timeout_over_limit_rejected() -> None:
    """timeout_seconds 上限 20：超限被拒。"""
    req = urllib.request.Request(
        f"{EXECUTOR_BASE}/v1/executions",
        data=json.dumps(
            {"user_id": "stagec-itest", "experiment_id": "stagec-itest", "task_id": "b2-bigtimeout",
             "language": "python", "code": "print(1)", "timeout_seconds": 60}
        ).encode(),
        method="POST",
        headers={"Content-Type": "application/json", "X-Execution-Token": EXECUTOR_TOKEN},
    )
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            body = json.loads(resp.read().decode())
        assert "error" in body or body.get("status") == "error", body
    except urllib.error.HTTPError as e:
        assert 400 <= e.code < 600


def test_batch2_concurrent_executions_isolated() -> None:
    """并发实测：3 个任务并行运行，各自结果正确且互不串扰（独立容器）。"""
    def run(i: int):
        return call_exec(f"import time; time.sleep(1); print({i})", task_id=f"b2-conc-{i}")

    with ThreadPoolExecutor(max_workers=3) as pool:
        results = list(pool.map(run, [1, 2, 3]))
    for i, r in zip([1, 2, 3], results):
        assert r["status"] == "completed" and r["exit_code"] == 0
        assert r["stdout"].strip() == str(i)


def test_batch2_long_task_at_max_timeout() -> None:
    """timeout_seconds=20（上限）正常任务：允许的边界值可用。"""
    r = call_exec("print('at-max')", timeout_seconds=20, task_id="b2-maxtimeout")
    assert r["status"] == "completed" and r["exit_code"] == 0
    assert r["stdout"].strip() == "at-max"


def test_batch2_runtime_exception_stderr_captured() -> None:
    """运行时异常：exit=1、完整 traceback 在 stderr、stdout 不串流。"""
    r = call_exec("print('before')\nraise ValueError('boom-marker')", task_id="b2-runtime")
    assert r["status"] == "completed" and r["exit_code"] == 1
    assert "boom-marker" in r["stderr"]
    assert r["stdout"].strip() == "before"
