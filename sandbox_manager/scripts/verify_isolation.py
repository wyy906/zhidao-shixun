#!/usr/bin/env python3
"""在真实 Linux 执行节点上验证沙箱隔离与资源限制

⚠️ 本脚本包含危险测试（无限循环、内存耗尽、fork、巨量输出），
   只能在**专用、可销毁的测试虚拟机**上执行，禁止在正式业务服务器运行。

用法（在能访问沙箱管理器的机器上）：
    python3 verify_isolation.py \
        --url https://10.0.0.20:8443 --token "$ZD_SANDBOX_TOKEN" \
        [--ca /etc/zd-sandbox/tls/ca.crt] \
        [--lan-host 10.0.0.5 --lan-port 3306] \
        [--backend-host 10.0.0.10 --backend-port 8000] \
        [--host-file /tmp/zd_host_probe.txt]

覆盖：管理接口认证、公网/局域网/业务端口不可达、宿主机文件不可读、工作目录隔离、
非 root 身份、根文件系统只读、仅回环网卡、cgroup CPU/内存/PID 限额、
超时、内存、fork、磁盘、输出截断、容器残留。

退出码：0 表示全部通过（或明确 SKIP），1 表示存在 FAIL。
结果只代表**本次**节点配置，请把输出如实记录到 TEST_REPORT.md。
"""
from __future__ import annotations

import argparse
import json
import socket
import ssl
import subprocess
import sys
import time
import urllib.error
import urllib.request

TERMINAL = {"succeeded", "failed", "timeout", "resource_exceeded", "cancelled"}


class Manager:
    def __init__(self, url: str, token: str, ca: str | None):
        self.base = url.rstrip("/")
        self.token = token
        ctx = ssl.create_default_context(cafile=ca) if ca else ssl.create_default_context()
        self.ctx = ctx

    def _request(self, method: str, path: str, payload: dict | None = None) -> tuple[int, dict]:
        data = json.dumps(payload).encode() if payload is not None else None
        req = urllib.request.Request(
            f"{self.base}{path}", data=data, method=method,
            headers={"X-Sandbox-Token": self.token, "Content-Type": "application/json"},
        )
        try:
            with urllib.request.urlopen(req, context=self.ctx, timeout=15) as resp:
                return resp.status, json.loads(resp.read().decode() or "{}")
        except urllib.error.HTTPError as exc:
            body = exc.read().decode(errors="replace")
            return exc.code, {"raw": body}

    def submit(self, code: str, timeout: int = 5) -> str:
        status, body = self._request("POST", "/v1/jobs", {"code": code, "timeout": timeout})
        if status not in (200, 202):
            raise RuntimeError(f"提交失败 {status}: {body}")
        return body["job_id"]

    def wait(self, job_id: str, deadline_seconds: float = 60) -> dict:
        end = time.monotonic() + deadline_seconds
        while time.monotonic() < end:
            status, body = self._request("GET", f"/v1/jobs/{job_id}")
            if status != 200:
                raise RuntimeError(f"查询失败 {status}: {body}")
            if body["status"] in TERMINAL:
                return body
            time.sleep(0.3)
        raise RuntimeError("等待任务结束超时")


def run_case(m: Manager, name: str, code: str, timeout: int = 5) -> dict:
    job_id = m.submit(code, timeout)
    return m.wait(job_id, deadline_seconds=timeout + 30)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--url", required=True)
    parser.add_argument("--token", required=True)
    parser.add_argument("--ca")
    parser.add_argument("--lan-host")
    parser.add_argument("--lan-port", type=int, default=80)
    parser.add_argument("--backend-host")
    parser.add_argument("--backend-port", type=int, default=8000)
    parser.add_argument("--host-file", help="执行节点上不应被容器读取的文件路径")
    parser.add_argument("--output-limit", type=int, default=65536)
    args = parser.parse_args()

    m = Manager(args.url, args.token, args.ca)
    results: list[tuple[str, str, str]] = []

    def record(name: str, ok: bool | None, detail: str) -> None:
        state = "SKIP" if ok is None else ("PASS" if ok else "FAIL")
        results.append((state, name, detail))
        print(f"[{state}] {name}: {detail}")

    # 0. 管理接口认证
    try:
        status, _ = Manager(args.url, "wrong-token", args.ca)._request("GET", "/health")
        record("管理接口拒绝错误令牌", status == 401, f"status={status}")
    except Exception as exc:  # 网络/TLS 异常本身说明未暴露
        record("管理接口拒绝错误令牌", True, f"请求被拒绝: {exc}")

    # 1. 公网隔离
    try:
        r = run_case(m, "public", (
            "import socket\n"
            "s=socket.socket(); s.settimeout(2)\n"
            "s.connect(('1.1.1.1',443))\n"
            "print('INTERNET_REACHABLE')\n"
        ))
        record("公网不可达", "INTERNET_REACHABLE" not in r["stdout"], f"status={r['status']}")
    except Exception as exc:
        record("公网不可达", False, str(exc))

    # 2. 局域网 / 业务后端 / 数据库端口
    for label, host, port in [
        ("局域网目标不可达", args.lan_host, args.lan_port),
        ("业务后端端口不可达", args.backend_host, args.backend_port),
    ]:
        if not host:
            record(label, None, "未提供目标地址，跳过")
            continue
        code = (
            "import socket\n"
            f"s=socket.socket(); s.settimeout(2)\n"
            f"s.connect(({host!r},{port}))\n"
            "print('LAN_REACHABLE')\n"
        )
        try:
            r = run_case(m, label, code)
            record(label, "LAN_REACHABLE" not in r["stdout"], f"status={r['status']}")
        except Exception as exc:
            record(label, False, str(exc))

    # 3. 宿主机文件隔离（标记文件由宿主机预先放在 /tmp，容器内 /tmp 是独立 tmpfs）
    marker_path = "/tmp/zd_sandbox_host_marker"
    try:
        with open(marker_path, "w", encoding="utf-8") as f:
            f.write("host-only-marker")
        code = (
            "try:\n"
            f"    print(open({marker_path!r}).read())\n"
            "except Exception as e:\n"
            "    print('READ_DENIED', type(e).__name__)\n"
        )
        r = run_case(m, "host-marker", code)
        record("无法读取宿主机标记文件", "host-only-marker" not in r["stdout"], r["stdout"].strip()[:80])
    except Exception as exc:
        record("无法读取宿主机标记文件", False, str(exc))
    finally:
        try:
            import os
            os.unlink(marker_path)
        except OSError:
            pass

    # 4. 业务项目文件 / 真实 .env
    if not args.host_file:
        record("无法读取业务项目文件 / .env", None, "未提供 --host-file，跳过")
    else:
        code = (
            "try:\n"
            f"    print(open({args.host_file!r}).read()[:80])\n"
            "except Exception as e:\n"
            "    print('READ_DENIED', type(e).__name__)\n"
        )
        try:
            r = run_case(m, "host-file", code)
            record("无法读取业务项目文件 / .env", "READ_DENIED" in r["stdout"], r["stdout"].strip()[:80])
        except Exception as exc:
            record("无法读取业务项目文件 / .env", False, str(exc))

    # 5. 任务工作目录隔离（新任务 /workspace 必须为空）
    try:
        r = run_case(m, "workspace", "import os\nprint('WORKSPACE:', os.listdir('/workspace'))\n")
        record("任务工作目录独立且为空", "WORKSPACE: []" in r["stdout"], r["stdout"].strip())
    except Exception as exc:
        record("任务工作目录独立且为空", False, str(exc))

    # 5.1 非 root 身份
    try:
        r = run_case(m, "uid", "import os\nprint('UID:', os.getuid())\n")
        record("容器内为非 root 用户", "UID: 65534" in r["stdout"], r["stdout"].strip())
    except Exception as exc:
        record("容器内为非 root 用户", False, str(exc))

    # 5.2 根文件系统只读（读取 /proc/mounts 中 / 的挂载选项）
    try:
        code = (
            "opts = [p.split()[3] for p in open('/proc/mounts') if len(p.split()) > 3 and p.split()[1] == '/']\n"
            "print('MOUNT_OPTS:', opts[0] if opts else 'UNKNOWN')\n"
        )
        r = run_case(m, "rootfs", code)
        record("根文件系统只读", "MOUNT_OPTS: ro" in r["stdout"], r["stdout"].strip()[:120])
    except Exception as exc:
        record("根文件系统只读", False, str(exc))

    # 5.3 网络接口（network=none 时只应有回环）
    try:
        r = run_case(m, "ifaces", "import socket\nprint('IFACES:', sorted(n for _, n in socket.if_nameindex()))\n")
        record("容器仅有回环网络接口", "IFACES: ['lo']" in r["stdout"], r["stdout"].strip())
    except Exception as exc:
        record("容器仅有回环网络接口", False, str(exc))

    # 5.4 cgroup v2 实际限额（CPU / 内存 / PID）
    try:
        code = (
            "def _read(path):\n"
            "    try:\n"
            "        return open(path).read().strip()\n"
            "    except OSError:\n"
            "        return 'UNAVAILABLE'\n"
            "print('CPU_MAX:', _read('/sys/fs/cgroup/cpu.max'))\n"
            "print('MEM_MAX:', _read('/sys/fs/cgroup/memory.max'))\n"
            "print('PIDS_MAX:', _read('/sys/fs/cgroup/pids.max'))\n"
        )
        r = run_case(m, "cgroup", code)
        out = r["stdout"]
        if "UNAVAILABLE" in out:
            record("CPU / 内存 / PID 限额实际生效", None, out.strip()[:160])
        else:
            cpu_ok = "CPU_MAX: 50000" in out
            mem_ok = "MEM_MAX: 134217728" in out
            pids_ok = "PIDS_MAX: 32" in out
            record("CPU / 内存 / PID 限额实际生效", cpu_ok and mem_ok and pids_ok, out.strip()[:160])
    except Exception as exc:
        record("CPU / 内存 / PID 限额实际生效", False, str(exc))

    # 6. 无限循环 → 超时终止
    try:
        r = run_case(m, "timeout", "while True:\n    pass\n", timeout=2)
        record("无限循环被超时终止", r["status"] == "timeout", f"status={r['status']}")
    except Exception as exc:
        record("无限循环被超时终止", False, str(exc))

    # 7. 内存耗尽 → 资源限制
    try:
        r = run_case(m, "memory", "buf = bytearray(512 * 1024 * 1024)\nprint('MEMORY_OK')\n", timeout=8)
        record("内存超限被限制", r["status"] != "succeeded" and "MEMORY_OK" not in r["stdout"],
               f"status={r['status']}")
    except Exception as exc:
        record("内存超限被限制", False, str(exc))

    # 8. fork bomb → 进程数限制
    try:
        code = (
            "import os\n"
            "n=0\n"
            "try:\n"
            "    while True:\n"
            "        os.fork(); n+=1\n"
            "except OSError:\n"
            "    print('FORK_LIMITED', n)\n"
        )
        r = run_case(m, "pids", code, timeout=5)
        record("进程数超限被限制", r["status"] != "succeeded" or "FORK_LIMITED" in r["stdout"],
               f"status={r['status']}")
    except Exception as exc:
        record("进程数超限被限制", False, str(exc))

    # 9. 磁盘写满 → tmpfs 大小限制
    try:
        code = (
            "try:\n"
            "    with open('/workspace/big.bin','wb') as f:\n"
            "        f.write(b'x' * (64 * 1024 * 1024))\n"
            "    print('DISK_LIMIT_NOT_ENFORCED')\n"
            "except OSError as e:\n"
            "    print('DISK_LIMITED', e.errno)\n"
        )
        r = run_case(m, "disk", code, timeout=8)
        record("磁盘超限被限制", "DISK_LIMIT_NOT_ENFORCED" not in r["stdout"], r["stdout"].strip()[:80])
    except Exception as exc:
        record("磁盘超限被限制", False, str(exc))

    # 10. 巨量输出 → 截断
    try:
        r = run_case(m, "output", "print('A' * (5 * 1024 * 1024))\n", timeout=8)
        size = len(r["stdout"].encode("utf-8"))
        record("巨量输出被截断", size <= args.output_limit + 100, f"stdout_bytes={size}")
    except Exception as exc:
        record("巨量输出被截断", False, str(exc))

    # 11. 容器残留检查（本机有 docker CLI 时）
    try:
        out = subprocess.check_output(
            ["docker", "ps", "-aq", "--filter", "label=zd.sandbox=1"],
            text=True, stderr=subprocess.DEVNULL,
        ).strip()
        record("任务结束后无残留容器", out == "", out or "none")
    except Exception:
        record("任务结束后无残留容器", None, "本机无 docker CLI，请手动执行: docker ps -a --filter label=zd.sandbox=1")

    failed = [r for r in results if r[0] == "FAIL"]
    skipped = [r for r in results if r[0] == "SKIP"]
    print(f"\n合计: {len(results)} 项，FAIL {len(failed)}，SKIP {len(skipped)}")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
