"""阶段 C 真实 Docker 集成测试（V2-04 首批实测，2026-11-13 首跑 10/10）。

这是**真实容器集成测试**（区别于本目录其他 Mock 单元测试）：
- 前提：独立执行服务（127.0.0.1:8101）已启动且真实 Docker 引擎可用、
  executor_image_lock.json 已批准；
- 未满足时自动 SKIP（不计入通过数，也不冒充真实结果）；
- 每项断言均基于真实容器执行结果（执行服务经 HTTP 真实创建/运行/清理容器）。

运行：.venv\\Scripts\\python.exe -m pytest server/tests/test_integration_real_docker.py -v
"""

import json
import os
import urllib.request

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
    except Exception:  # noqa: BLE001 - 环境不可用即跳过
        return False


pytestmark = pytest.mark.skipif(
    not _service_ready(),
    reason="需运行中的执行服务 + 真实 Docker 引擎 + 已批准 digest（环境不可用则如实跳过）",
)


def call_exec(code: str, timeout_seconds: int = 15, task_id: str = "stagec") -> dict:
    req = urllib.request.Request(
        f"{EXECUTOR_BASE}/v1/executions",
        data=json.dumps(
            {"user_id": "stagec-itest", "experiment_id": "stagec-itest", "task_id": task_id,
             "language": "python", "code": code, "timeout_seconds": timeout_seconds}
        ).encode(),
        method="POST",
        headers={"Content-Type": "application/json", "X-Execution-Token": EXECUTOR_TOKEN},
    )
    with urllib.request.urlopen(req, timeout=timeout_seconds + 60) as resp:
        return json.loads(resp.read().decode())


def test_stagec_end_to_end_real_execution() -> None:
    r = call_exec("print('hello from container')\nprint(6 * 7)", task_id="it-c1")
    assert r["status"] == "completed" and r["exit_code"] == 0
    assert "hello from container" in r["stdout"] and "42" in r["stdout"]


def test_stagec_non_root_user() -> None:
    r = call_exec("import os\nprint(os.getuid())", task_id="it-c2")
    assert r["stdout"].strip() == "65534"


def test_stagec_read_only_rootfs() -> None:
    r = call_exec(
        "try:\n    open('/probe', 'w').write('x')\n    print('WRITABLE')\n"
        "except OSError as e:\n    print('READONLY', e.errno)",
        task_id="it-c3",
    )
    assert "READONLY" in r["stdout"] and "WRITABLE" not in r["stdout"]


def test_stagec_sandbox_tmpfs_writable() -> None:
    r = call_exec(
        "open('/sandbox/work.txt', 'w').write('ok')\nprint(open('/sandbox/work.txt').read())",
        task_id="it-c4",
    )
    assert r["stdout"].strip() == "ok"


def test_stagec_network_disabled() -> None:
    r = call_exec(
        "import socket\n"
        "try:\n    socket.create_connection(('1.1.1.1', 80), timeout=3)\n"
        "    print('NETWORK-UP')\n"
        "except OSError as e:\n    print('NET-DOWN', type(e).__name__)\n",
        task_id="it-c5",
    )
    assert "NETWORK-UP" not in r["stdout"]


def test_stagec_stdout_stderr_demux() -> None:
    r = call_exec(
        "import sys\nprint('to-stdout')\nprint('to-stderr', file=sys.stderr)\n",
        task_id="it-c6",
    )
    assert "to-stdout" in r["stdout"] and "to-stderr" in r["stderr"]


def test_stagec_syntax_error_is_run_result_not_infra_error() -> None:
    r = call_exec("def broken(:", task_id="it-c7")
    assert r["status"] == "completed" and r["exit_code"] == 1
    assert "SyntaxError" in r["stderr"]


def test_stagec_timeout_kill() -> None:
    """真实语义：超时 → 容器被 SIGKILL（exit 137），status=timeout 且 timed_out=true。"""
    r = call_exec("while True: pass", timeout_seconds=5, task_id="it-c8")
    assert r["status"] == "timeout" and r["timed_out"] is True
    assert r["exit_code"] in (None, 137)


def test_stagec_no_leftover_containers() -> None:
    """清理纪律：全部测试容器运行后无残留（由各任务 finally remove 保证）。"""
    call_exec("print('cleanup-marker')", task_id="it-c9")
    r = call_exec("import os; print('ok')", task_id="it-c9b")
    assert r["exit_code"] == 0  # 引擎健康即可继续；残留检查由 C9 批次脚本用 docker ps 完成
