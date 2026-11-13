#!/usr/bin/env python3
"""在真实 Linux 执行节点上验证沙箱隔离与资源限制

⚠️ 本脚本包含危险测试（无限循环、内存耗尽、fork、巨量输出），
   只能在**专用、可销毁的测试虚拟机**上执行，禁止在正式业务服务器运行。

用法（建议直接在执行节点本机运行）：
    python3 verify_isolation.py \
        --url https://10.0.0.20:8443 --token "$ZD_SANDBOX_TOKEN" \
        --ca /etc/zd-sandbox/tls/ca.crt \
        --on-execution-node --confirm-manager-docker-same-host --docker-check local \
        [--client-cert client.crt --client-key client.key] \
        [--expect-mtls --invalid-client-cert bad.crt --invalid-client-key bad.key] \
        [--lan-host 10.0.0.5 --lan-port 3306] \
        [--backend-host 10.0.0.10 --backend-port 8000] \
        [--host-file /tmp/zd_host_probe.txt] \
        [--expected-cpu 0.5 --expected-memory-mb 128 --expected-pids 32] \
        [--expected-swap-mb 0] \
        [--output-limit 32768 --output-total-limit 65536]

判定语义：
  - PASS：所有必检项通过。
  - FAIL：任一必检项失败。
  - INCOMPLETE：无 FAIL，但存在必检项 SKIP（例如无法确认标记文件在 Docker
    宿主机、Docker CLI 不在执行节点、缺少客户端证书等）。
  - 可选项目（未提供局域网/业务后端目标、未提供 host-file）SKIP 不影响结论，
    但会在输出中单独标注。

注意：
  - `--on-execution-node` 只是操作人员的人工声明，**不是密码学身份认证**。
  - 还必须额外提供 `--confirm-manager-docker-same-host`，人工确认“管理器实际
    使用的 Docker Engine 就是本机执行节点”。请先通过 SSH 登录到 Docker 执行
    节点本机，核对管理器运行位置、管理器 Docker 连接配置、Docker Engine 地址、
    Docker Socket 是否为本机 Socket，再运行本脚本。任一条件未确认时，节点身份、
    宿主机标记文件、容器残留检查一律 SKIP（结论 INCOMPLETE），不得当作通过。
  - 网络判定只接受明确“连接未建立”的证据（ENETUNREACH/EHOSTUNREACH/
    EACCES/EPERM）；DNS 解析失败、ConnectionRefused、超时、未知异常一律
    不能证明网络隔离。

退出码：0 = PASS；1 = FAIL；2 = INCOMPLETE（SKIP 不等于通过）。
结果只代表**本次**节点与配置，请把输出如实记录到验收证据目录。
"""
from __future__ import annotations

import argparse
import http.client
import json
import os
import ssl
import subprocess
import sys
import time
import urllib.error
import urllib.request

TERMINAL = {"succeeded", "failed", "timeout", "resource_exceeded", "cancelled"}

# 截断标记 “\n…（输出过长，已截断）” 的 UTF-8 字节容差（约 37 字节）。
# 只用于容纳标记本身，不得据此放宽实际上限。
TRUNCATION_TOLERANCE = 100

# 实际返回字节数至少要达到预期上限的这一比例，否则视为“输出缺失/未真正写满”，
# 防止 5MB 任务只返回 100 字节也被判 PASS。
MIN_OUTPUT_RATIO = 0.9

REQUIRED = True
OPTIONAL = False


# ===========================================================================
# 结论汇总
# ===========================================================================
def record(results: list[dict], name: str, ok: bool | None, detail: str,
           required: bool = REQUIRED) -> None:
    if ok is None:
        state = "SKIP"
    elif ok:
        state = "PASS"
    else:
        state = "FAIL"
    results.append({
        "name": name,
        "state": state,
        "required": required,
        "detail": detail,
    })
    flag = "" if required else "（可选）"
    print(f"[{state}] {name}{flag}: {detail}")


def final_verdict(results: list[dict]) -> tuple[str, int]:
    """返回 (结论, 退出码)：0=PASS，1=FAIL，2=INCOMPLETE"""
    if any(r["state"] == "FAIL" for r in results):
        return "FAIL", 1
    if any(r["state"] == "SKIP" and r["required"] for r in results):
        return "INCOMPLETE", 2
    return "PASS", 0


# ===========================================================================
# 判定辅助（纯函数，便于单元测试）
# ===========================================================================
def judge_wrong_token(status: int | None = None, error: BaseException | None = None
                      ) -> tuple[bool, str]:
    """只有服务器明确返回 401 才算认证校验通过"""
    if error is not None:
        return False, f"请求异常，不能认定认证生效: {type(error).__name__}"
    if status == 401:
        return True, "HTTP 401"
    return False, f"期望 HTTP 401，实际 HTTP {status}"


def judge_network(status: str, stdout: str, stderr: str) -> tuple[bool, str]:
    """解析容器内网络探测结果，只有明确“未建立连接”的错误才算隔离

    判定规则（errno 以 Linux 为准）：
      - ENETUNREACH(101) / EHOSTUNREACH(113)：目标不可达 → PASS
      - EACCES(13) / EPERM(1)：被策略拒绝 → PASS
      - ECONNREFUSED(111)：主机可达、端口无服务 → FAIL（不能证明隔离）
      - ETIMEDOUT(110) / timeout：超时原因不明 → FAIL
      - gaierror / DNS 失败 → FAIL（DNS 失败不能证明网络隔离）
      - 连接成功、缺少 NET_RESULT、任务异常 → FAIL
    """
    if status != "succeeded":
        return False, f"测试代码未正常结束（status={status}），不能判定为隔离"

    line = next((ln for ln in stdout.splitlines() if ln.startswith("NET_RESULT")), None)
    if line is None:
        return False, "缺少 NET_RESULT 证据"
    try:
        payload = json.loads(line[len("NET_RESULT"):].strip())
    except json.JSONDecodeError:
        return False, f"NET_RESULT 无法解析: {line[:80]}"

    if payload.get("connected"):
        return False, "连接成功（NET_REACHABLE）"

    err_type = str(payload.get("type") or "")
    err_no = payload.get("errno")
    detail = f"type={err_type} errno={err_no}"

    # 容器内是 Linux，errno 使用 Linux 数值（不依赖脚本宿主平台）
    if err_no in (101, 113):          # ENETUNREACH / EHOSTUNREACH
        return True, f"目标不可达 {detail}"
    if err_no in (13, 1):             # EACCES / EPERM
        return True, f"策略拒绝 {detail}"
    if err_no == 111 or err_type == "ConnectionRefusedError":
        return False, f"端口拒绝，但主机可能可达，不能证明隔离 {detail}"
    if err_no == 110 or "timeout" in err_type.lower():
        return False, f"连接超时，原因无法确定 {detail}"
    if "gaierror" in err_type.lower():
        return False, f"DNS 解析失败，不能证明网络隔离 {detail}"
    return False, f"未知网络错误，不能判定为隔离 {detail}"


def network_probe_code(host: str, port: int) -> str:
    """生成容器内网络探测代码：输出结构化 NET_RESULT"""
    return (
        "import json, socket\n"
        "try:\n"
        f"    s = socket.create_connection(({host!r}, {port}), 2)\n"
        "    s.close()\n"
        "    print('NET_RESULT', json.dumps({'connected': True}))\n"
        "except Exception as e:\n"
        "    print('NET_RESULT', json.dumps({\n"
        "        'connected': False,\n"
        "        'type': type(e).__name__,\n"
        "        'errno': getattr(e, 'errno', None),\n"
        "    }))\n"
    )


def judge_marker(status: str, stdout: str) -> tuple[bool, str]:
    if status != "succeeded":
        return False, f"测试代码未正常结束（status={status}）"
    if "READ_DENIED" in stdout:
        return True, "READ_DENIED"
    return False, "未看到 READ_DENIED，可能读取到了宿主机文件"


def judge_uid(status: str, stdout: str) -> tuple[bool, str]:
    if status != "succeeded":
        return False, f"status={status}"
    return ("UID: 65534" in stdout), f"stdout={stdout.strip()[:80]}"


def judge_rootfs(status: str, stdout: str) -> tuple[bool, str]:
    if status != "succeeded":
        return False, f"status={status}"
    return ("MOUNT_OPTS: ro" in stdout), f"stdout={stdout.strip()[:120]}"


def judge_ifaces(status: str, stdout: str) -> tuple[bool, str]:
    if status != "succeeded":
        return False, f"status={status}"
    return ("IFACES: ['lo']" in stdout), f"stdout={stdout.strip()[:120]}"


def parse_cpu_max(text: str, expected_cores: float) -> tuple[bool, str]:
    """解析 cgroup v2 cpu.max：`<quota> <period>` 或 `max <period>`"""
    parts = (text or "").split()
    if len(parts) != 2:
        return False, f"无法解析 cpu.max={text!r}"
    quota_raw, period_raw = parts
    if quota_raw == "max":
        return False, "CPU quota 为 max（未限制）"
    try:
        quota, period = int(quota_raw), int(period_raw)
    except ValueError:
        return False, f"无法解析 cpu.max={text!r}"
    if period <= 0:
        return False, f"period 非法: {period}"
    expected = expected_cores * period
    ok = abs(quota - expected) <= 1
    detail = f"quota={quota} period={period} 比例={quota / period:.3f} 期望={expected_cores}"
    return ok, detail


def parse_memory_max(text: str, expected_mb: int) -> tuple[bool, str]:
    raw = (text or "").strip()
    if raw in {"", "max"}:
        return False, f"memory.max={raw or '空'}（未限制或不可读）"
    try:
        value = int(raw)
    except ValueError:
        return False, f"无法解析 memory.max={raw!r}"
    expected = expected_mb * 1024 * 1024
    return value == expected, f"memory.max={value} 期望={expected}"


def parse_pids_max(text: str, expected: int) -> tuple[bool, str]:
    raw = (text or "").strip()
    if raw in {"", "max"}:
        return False, f"pids.max={raw or '空'}（未限制或不可读）"
    try:
        value = int(raw)
    except ValueError:
        return False, f"无法解析 pids.max={raw!r}"
    return value == expected, f"pids.max={value} 期望={expected}"


def parse_swap_max(text: str, expected_mb: int) -> tuple[bool, str]:
    """memory.swap.max：`max` 表示未限制；本项目 memswap == mem 时期望 0"""
    raw = (text or "").strip()
    if raw in {"", "max"}:
        return False, f"memory.swap.max={raw or '空'}（未限制或不可读）"
    try:
        value = int(raw)
    except ValueError:
        return False, f"无法解析 memory.swap.max={raw!r}"
    expected = expected_mb * 1024 * 1024
    return value == expected, f"memory.swap.max={value} 期望={expected}"


def judge_timeout(status: str) -> tuple[bool, str]:
    return status == "timeout", f"status={status}（期望 timeout）"


def judge_memory_limit(status: str, stdout: str, stderr: str) -> tuple[bool, str]:
    """内存限制：明确 OOM / MemoryError 证据才算通过；成功分配则失败"""
    if "MEMORY_OK" in stdout:
        return False, "成功分配 512MB，内存限制未生效"
    if status == "resource_exceeded":
        return True, "status=resource_exceeded"
    if status == "succeeded" and "MEMORY_LIMITED" in stdout:
        return True, "MEMORY_LIMITED（MemoryError）"
    return False, f"status={status}，缺少明确的内存超限证据"


def judge_fork(status: str, stdout: str) -> tuple[bool, str]:
    if status == "resource_exceeded":
        return True, "status=resource_exceeded"
    if status == "succeeded" and "FORK_LIMITED" in stdout:
        return True, "FORK_LIMITED（进程数上限生效）"
    return False, f"status={status}，未看到 FORK_LIMITED 或 resource_exceeded"


def judge_disk(status: str, stdout: str) -> tuple[bool, str]:
    if "DISK_LIMIT_NOT_ENFORCED" in stdout:
        return False, "写入 64MB 成功，磁盘限制未生效"
    if status == "succeeded" and "DISK_LIMITED" in stdout:
        return True, "DISK_LIMITED（ENOSPC）"
    return False, f"status={status}，未看到明确的 DISK_LIMITED"


def judge_output(status: str, stdout_size: int, limit: int) -> tuple[bool, str]:
    """单个输出流截断判定：既要不超过上限，也要接近上限。

    只检查“非空 + 不超限”会导致 5MB 任务只返回 100 字节也判 PASS；
    这里要求实际字节数至少达到上限的 `MIN_OUTPUT_RATIO`。
    """
    if status != "succeeded":
        return False, f"status={status}，不能判定为截断成功"
    if stdout_size <= 0:
        return False, "stdout 为空，缺少截断证据"
    if stdout_size > limit + TRUNCATION_TOLERANCE:
        return False, (
            f"字节数={stdout_size} 超过上限 {limit}"
            f"（容差 {TRUNCATION_TOLERANCE}）"
        )
    min_expected = int(limit * MIN_OUTPUT_RATIO)
    if stdout_size < min_expected:
        return False, (
            f"字节数={stdout_size} 明显低于上限 {limit}"
            f"（至少应接近 {min_expected}），疑似输出缺失或未真正写满"
        )
    return True, f"bytes={stdout_size} 上限≈{limit}"


def judge_total_output(status: str, stdout_size: int, stderr_size: int,
                       per_stream_limit: int,
                       total_limit: int) -> tuple[bool, str]:
    """同一个任务的 stdout + stderr 合计上限判定

    要求任务成功、两通道都接近单流上限，且合计接近（但不超过）总上限。
    两个不同任务的结果不得相加；任一通道明显不足都判 FAIL。
    """
    if status != "succeeded":
        return False, f"status={status}，不能判定总输出限制"
    if stdout_size <= 0 or stderr_size <= 0:
        return False, (
            f"stdout/stderr 存在空通道（stdout={stdout_size} stderr={stderr_size}），"
            "缺少双通道证据"
        )
    min_stream = int(per_stream_limit * MIN_OUTPUT_RATIO)
    if stdout_size < min_stream:
        return False, (
            f"stdout_bytes={stdout_size} 明显低于单流上限 {per_stream_limit}"
            f"（至少应接近 {min_stream}）"
        )
    if stderr_size < min_stream:
        return False, (
            f"stderr_bytes={stderr_size} 明显低于单流上限 {per_stream_limit}"
            f"（至少应接近 {min_stream}）"
        )
    total = stdout_size + stderr_size
    if total > total_limit + TRUNCATION_TOLERANCE:
        return False, (
            f"合计={total} 超过总上限 {total_limit}（容差 {TRUNCATION_TOLERANCE}）"
        )
    # 单流有上限，因此可达到的合计上限不会超过 2×单流上限
    expected_total = min(total_limit, 2 * per_stream_limit)
    min_total = int(expected_total * MIN_OUTPUT_RATIO)
    if total < min_total:
        return False, (
            f"合计={total} 明显低于预期总上限 {expected_total}"
            f"（至少应接近 {min_total}）"
        )
    return True, (
        f"stdout_bytes={stdout_size} stderr_bytes={stderr_size} "
        f"合计={total} 上限≈{total_limit}"
    )


def judge_node_identity(on_execution_node: bool, confirm_same_host: bool,
                        docker_available: bool,
                        docker_env_hint: str = "") -> tuple[bool | None, str]:
    """执行节点身份（人工核验，不是密码学证明）

    `--on-execution-node` 只是声明，不能单独作为身份通过依据。必须同时提供
    `--confirm-manager-docker-same-host`（人工确认管理器使用的 Docker Engine
    就是本机执行节点），且本机 Docker Engine 可用，才允许判定为通过；任一条件
    缺失都返回 SKIP。
    """
    if not on_execution_node:
        return None, "未声明 --on-execution-node，无法确认执行节点身份"
    if not confirm_same_host:
        extra = f"（检测到 {docker_env_hint}）" if docker_env_hint else ""
        return None, (
            "未提供 --confirm-manager-docker-same-host，未人工确认管理器与 "
            f"Docker Engine 同节点{extra}"
        )
    if not docker_available:
        return None, "本机 Docker Engine 不可用，无法确认与管理器同节点"
    detail = "人工确认管理器与 Docker Engine 同节点（人工核验，非密码学证明）"
    if docker_env_hint:
        detail += (
            f"；注意 Docker 客户端使用 {docker_env_hint}，需人工确认与管理器配置一致"
        )
    return True, detail


def judge_container_residue(docker_check: str, node_confirmed: bool,
                            output: str | None = None,
                            error: BaseException | None = None
                            ) -> tuple[bool | None, str]:
    """无法确认节点身份时返回 SKIP（None）"""
    if docker_check != "local" or not node_confirmed:
        return None, (
            "无法确认本机 Docker CLI 属于执行节点；请先人工确认节点身份，"
            "并在执行节点运行 `docker ps -aq --filter label=zd.sandbox=1` 单独记录"
        )
    if error is not None:
        return None, f"Docker CLI 不可用: {type(error).__name__}"
    return output == "", f"residual={output or 'none'}"


def judge_host_marker_scope(node_confirmed: bool) -> tuple[bool | None, str]:
    """标记文件必须在 Docker 宿主机上创建；未人工确认节点身份时 SKIP"""
    if not node_confirmed:
        return None, (
            "未确认执行节点身份（需要 --on-execution-node 且 "
            "--confirm-manager-docker-same-host），不创建/不测试宿主机标记文件"
        )
    return True, ""

def ssl_error_of(exc: BaseException) -> ssl.SSLError | None:
    """从 urllib 包装异常中取出底层 SSL 异常"""
    if isinstance(exc, ssl.SSLError):
        return exc
    if isinstance(exc, urllib.error.URLError) and isinstance(exc.reason, ssl.SSLError):
        return exc.reason
    return None


def _exception_chain(exc: BaseException):
    """遍历异常链（含 urllib 包装的 reason），用于识别底层异常类型"""
    seen: set[int] = set()
    current: BaseException | None = exc
    while current is not None and id(current) not in seen:
        seen.add(id(current))
        yield current
        reason = getattr(current, "reason", None)
        if isinstance(reason, BaseException) and id(reason) not in seen:
            yield reason
            seen.add(id(reason))
        current = current.__cause__ or current.__context__


def tls_rejection_of(exc: BaseException) -> tuple[bool, str]:
    """判断异常是否表明服务端在 TLS 层拒绝了连接

    只接受两类证据：
      1. 明确的 SSL 异常；
      2. TLS 已建立后被服务端关闭（RemoteDisconnected / RST / BrokenPipe），
         此时客户端收不到任何 HTTP 响应。

    DNS 失败、连接被拒绝、超时、证书/私钥配置错误一律不算。
    TLS 1.3 下服务端告警在握手完成后才到达，客户端因此看到的是连接被关闭，
    而不是 SSLError，故必须按“零 HTTP 响应”识别，不能直接当作握手失败。
    """
    ssl_exc = ssl_error_of(exc)
    if ssl_exc is not None:
        reason = getattr(ssl_exc, "reason", "") or ""
        return True, f"SSLError({reason})" if reason else "SSLError"

    for item in _exception_chain(exc):
        if isinstance(item, (http.client.RemoteDisconnected, ConnectionResetError, BrokenPipeError)):
            return True, f"{type(item).__name__}（TLS 层关闭，未收到 HTTP 响应）"
    return False, f"{type(exc).__name__}（非 TLS 层拒绝，不能作为 mTLS 证据）"


# ===========================================================================
# 管理器客户端
# ===========================================================================
class Manager:
    def __init__(self, url: str, token: str, ca: str | None = None,
                 client_cert: str | None = None, client_key: str | None = None):
        if bool(client_cert) != bool(client_key):
            raise ValueError("客户端证书与私钥必须同时提供")
        self.base = url.rstrip("/")
        self.token = token
        self.ctx = self.build_ssl_context(ca, client_cert, client_key)
        self.mtls = bool(client_cert)

    @staticmethod
    def build_ssl_context(ca: str | None, client_cert: str | None,
                          client_key: str | None) -> ssl.SSLContext:
        if bool(client_cert) != bool(client_key):
            raise ValueError("客户端证书与私钥必须同时提供")
        ctx = ssl.create_default_context(cafile=ca) if ca else ssl.create_default_context()
        if client_cert:
            # 私钥只用于加载证书链，绝不写入日志或输出
            ctx.load_cert_chain(certfile=client_cert, keyfile=client_key)
        return ctx

    def _request(self, method: str, path: str, payload: dict | None = None,
                 token: str | None = None) -> tuple[int, dict]:
        data = json.dumps(payload).encode() if payload is not None else None
        req = urllib.request.Request(
            f"{self.base}{path}", data=data, method=method,
            headers={
                "X-Sandbox-Token": token if token is not None else self.token,
                "Content-Type": "application/json",
            },
        )
        try:
            with urllib.request.urlopen(req, context=self.ctx, timeout=15) as resp:
                return resp.status, json.loads(resp.read().decode() or "{}")
        except urllib.error.HTTPError as exc:
            body = exc.read().decode(errors="replace")
            return exc.code, {"raw": body}

    def probe_wrong_token(self) -> tuple[bool, str]:
        """错误令牌探测：仅 HTTP 401 算通过；网络/TLS 异常一律不算"""
        try:
            status, _ = self._request("GET", "/health", token="wrong-token")
        except Exception as exc:  # noqa: BLE001 - 需要区分具体异常类型
            return judge_wrong_token(error=exc)
        return judge_wrong_token(status=status)

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


def run_case(m: Manager, code: str, timeout: int = 5) -> dict:
    job_id = m.submit(code, timeout)
    return m.wait(job_id, deadline_seconds=timeout + 30)


# ===========================================================================
# 主流程
# ===========================================================================
def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--url", required=True)
    parser.add_argument("--token", required=True)
    parser.add_argument("--ca")
    parser.add_argument("--client-cert", help="双向 TLS 客户端证书（与 --client-key 成对）")
    parser.add_argument("--client-key", help="双向 TLS 客户端私钥（不会输出到日志）")
    parser.add_argument("--expect-mtls", action="store_true",
                        help="声明服务端强制双向 TLS，并验证无证书/错误证书/不受信服务端")
    parser.add_argument("--invalid-client-cert", help="错误的客户端证书（用于负向测试）")
    parser.add_argument("--invalid-client-key", help="错误客户端证书对应的私钥")
    parser.add_argument("--on-execution-node", action="store_true",
                        help="声明本脚本直接运行在 Docker 执行节点上（仅为声明）")
    parser.add_argument("--confirm-manager-docker-same-host", action="store_true",
                        help="人工确认管理器使用的 Docker Engine 就是本机执行节点"
                             "（人工核验，非密码学证明）")
    parser.add_argument("--docker-check", choices=["local", "skip"], default="skip",
                        help="local=本机就是执行节点并检查残留容器；skip=不检查")
    parser.add_argument("--lan-host")
    parser.add_argument("--lan-port", type=int, default=80)
    parser.add_argument("--backend-host")
    parser.add_argument("--backend-port", type=int, default=8000)
    parser.add_argument("--host-file", help="执行节点上专门创建的无敏感测试文件")
    parser.add_argument("--expected-cpu", type=float, default=0.5)
    parser.add_argument("--expected-memory-mb", type=int, default=128)
    parser.add_argument("--expected-pids", type=int, default=32)
    parser.add_argument("--expected-swap-mb", type=int, default=0,
                        help="memory.swap.max 期望值（memswap==mem 时为 0）")
    parser.add_argument("--output-limit", type=int, default=32768,
                        help="单个输出流上限（管理器默认每流 32KB）")
    parser.add_argument("--output-total-limit", type=int, default=65536,
                        help="stdout+stderr 合计上限（默认 64KB）")
    args = parser.parse_args()

    results: list[dict] = []

    def add(name: str, ok: bool | None, detail: str, required: bool = REQUIRED) -> None:
        record(results, name, ok, detail, required)

    def case(name: str, code: str, judge, timeout: int = 5,
             required: bool = REQUIRED) -> None:
        try:
            r = run_case(m, code, timeout)
        except Exception as exc:  # noqa: BLE001
            add(name, False, f"任务执行异常: {type(exc).__name__}")
            return
        ok, detail = judge(r["status"], r.get("stdout", ""), r.get("stderr", ""))
        add(name, ok, detail, required)

    try:
        m = Manager(args.url, args.token, args.ca,
                    args.client_cert, args.client_key)
    except Exception as exc:  # noqa: BLE001
        print(f"[FAIL] 初始化 TLS 客户端失败: {type(exc).__name__}: {exc}")
        return 1

    # 0. 错误令牌：只有明确 401 才算通过
    ok, detail = m.probe_wrong_token()
    add("管理接口拒绝错误令牌", ok, detail)

    # 0.1 双向 TLS
    if args.expect_mtls:
        _check_mtls(m, args, add)
    else:
        add("双向 TLS 客户端证书认证", None,
            "未启用 --expect-mtls（仅校验服务端证书）", OPTIONAL)

    # 0.2 执行节点身份（人工声明 + 人工确认管理器与 Docker 同节点 + 本机 Docker 可用）
    # 仅凭 --on-execution-node 或本机 docker info 成功都不能证明与管理器同 Engine。
    docker_env_hint = ""
    for key in ("DOCKER_HOST", "DOCKER_CONTEXT"):
        val = os.environ.get(key)
        if val:
            docker_env_hint = f"{key}={val}"
            break
    docker_available = False
    if args.on_execution_node and args.confirm_manager_docker_same_host:
        try:
            subprocess.check_output(
                ["docker", "info", "--format", "{{.ID}}"],
                text=True, stderr=subprocess.DEVNULL, timeout=10,
            )
            docker_available = True
        except Exception:  # noqa: BLE001
            docker_available = False
    identity_ok, identity_detail = judge_node_identity(
        args.on_execution_node, args.confirm_manager_docker_same_host,
        docker_available, docker_env_hint)
    add("执行节点身份（管理器与 Docker 同节点）", identity_ok, identity_detail)
    # 后续节点侧检查（宿主机标记文件、容器残留）一律以人工确认结果为前提
    node_confirmed = identity_ok is True

    # 1. 公网隔离
    case("公网不可达", network_probe_code("1.1.1.1", 443), judge_network)

    # 2. 局域网 / 业务后端 / 数据库端口
    for label, host, port in [
        ("局域网目标不可达", args.lan_host, args.lan_port),
        ("业务后端端口不可达", args.backend_host, args.backend_port),
    ]:
        if not host:
            add(label, None, "未提供目标地址，跳过（可选）", OPTIONAL)
            continue
        case(label, network_probe_code(host, port), judge_network)

    # 3. 宿主机标记文件：只能在人工确认执行节点身份后，在本机创建
    scope_ok, scope_detail = judge_host_marker_scope(node_confirmed)
    marker_path = f"/tmp/zd_verify_marker_{os.getpid()}"
    if node_confirmed:
        try:
            with open(marker_path, "w", encoding="utf-8") as f:
                f.write("zd-host-only-marker")
            code = (
                "try:\n"
                f"    print(open({marker_path!r}).read())\n"
                "except Exception as e:\n"
                "    print('READ_DENIED', type(e).__name__)\n"
            )
            case("无法读取宿主机标记文件", code,
                 lambda status, out, err: judge_marker(status, out))
        except OSError as exc:
            add("无法读取宿主机标记文件", None,
                f"无法在执行节点创建标记文件: {type(exc).__name__}")
        finally:
            try:
                os.unlink(marker_path)   # 只删除本轮专用文件
            except OSError:
                pass
    else:
        add("无法读取宿主机标记文件", scope_ok, scope_detail)

    # 4. 业务项目文件 / .env（可选；也必须位于已确认的执行节点）
    if not args.host_file:
        add("无法读取业务项目文件 / .env", None, "未提供 --host-file，跳过（可选）", OPTIONAL)
    elif not node_confirmed:
        add("无法读取业务项目文件 / .env", None,
            "未确认执行节点身份，无法确认文件位于 Docker 宿主机", OPTIONAL)
    elif not os.path.isfile(args.host_file):
        add("无法读取业务项目文件 / .env", None,
            f"执行节点上不存在该文件: {args.host_file}")
    else:
        code = (
            "try:\n"
            f"    print(open({args.host_file!r}).read()[:80])\n"
            "except Exception as e:\n"
            "    print('READ_DENIED', type(e).__name__)\n"
        )
        case("无法读取业务项目文件 / .env", code,
             lambda status, out, err: judge_marker(status, out))

    # 5. 工作目录隔离
    case("任务工作目录独立且为空",
         "import os\nprint('WORKSPACE:', os.listdir('/workspace'))\n",
         lambda status, out, err: (
             status == "succeeded" and "WORKSPACE: []" in out,
             f"status={status} stdout={out.strip()[:80]}",
         ))

    # 5.1 非 root
    case("容器内为非 root 用户",
         "import os\nprint('UID:', os.getuid())\n",
         lambda status, out, err: judge_uid(status, out))

    # 5.2 根文件系统只读
    case("根文件系统只读",
         "opts=[p.split()[3] for p in open('/proc/mounts') if len(p.split())>3 and p.split()[1]=='/']\n"
         "print('MOUNT_OPTS:', opts[0] if opts else 'UNKNOWN')\n",
         lambda status, out, err: judge_rootfs(status, out))

    # 5.3 仅回环网卡
    case("容器仅有回环网络接口",
         "import socket\nprint('IFACES:', sorted(n for _, n in socket.if_nameindex()))\n",
         lambda status, out, err: judge_ifaces(status, out))

    # 5.4 cgroup 限额
    cgroup_code = (
        "def _read(path):\n"
        "    try:\n"
        "        return open(path).read().strip()\n"
        "    except OSError:\n"
        "        return 'UNAVAILABLE'\n"
        "print('CPU_MAX:', _read('/sys/fs/cgroup/cpu.max'))\n"
        "print('MEM_MAX:', _read('/sys/fs/cgroup/memory.max'))\n"
        "print('SWAP_MAX:', _read('/sys/fs/cgroup/memory.swap.max'))\n"
        "print('PIDS_MAX:', _read('/sys/fs/cgroup/pids.max'))\n"
    )
    try:
        cg = run_case(m, cgroup_code)
        if cg["status"] != "succeeded":
            for name in ("CPU 限额", "内存限额", "交换空间限额", "PID 限额"):
                add(name, None, f"cgroup 读取任务未成功（status={cg['status']}）")
        else:
            values = dict(
                line.split(":", 1) for line in cg["stdout"].splitlines() if ":" in line
            )
            values = {k.strip(): v.strip() for k, v in values.items()}
            for name, raw, judge in [
                ("CPU 限额", "CPU_MAX", lambda v: parse_cpu_max(v, args.expected_cpu)),
                ("内存限额", "MEM_MAX", lambda v: parse_memory_max(v, args.expected_memory_mb)),
                ("交换空间限额", "SWAP_MAX", lambda v: parse_swap_max(v, args.expected_swap_mb)),
                ("PID 限额", "PIDS_MAX", lambda v: parse_pids_max(v, args.expected_pids)),
            ]:
                value = values.get(raw, "UNAVAILABLE")
                if value == "UNAVAILABLE":
                    add(name, None, "cgroup 文件不可读，无法验证")
                else:
                    ok, detail = judge(value)
                    add(name, ok, detail)
    except Exception as exc:  # noqa: BLE001
        for name in ("CPU 限额", "内存限额", "交换空间限额", "PID 限额"):
            add(name, False, f"任务异常: {type(exc).__name__}")

    # 6. 超时
    case("无限循环被超时终止", "while True:\n    pass\n",
         lambda status, out, err: judge_timeout(status), timeout=2)

    # 7. 内存
    case("内存超限被限制",
         "try:\n"
         "    buf = bytearray(512 * 1024 * 1024)\n"
         "    print('MEMORY_OK')\n"
         "except MemoryError:\n"
         "    print('MEMORY_LIMITED')\n",
         lambda status, out, err: judge_memory_limit(status, out, err), timeout=8)

    # 8. fork
    fork_code = (
        "import os\nn=0\n"
        "try:\n"
        "    while True:\n"
        "        os.fork(); n+=1\n"
        "except OSError:\n"
        "    print('FORK_LIMITED', n)\n"
    )
    case("进程数超限被限制", fork_code,
         lambda status, out, err: judge_fork(status, out), timeout=5)

    # 9. 磁盘
    disk_code = (
        "try:\n"
        "    with open('/workspace/big.bin','wb') as f:\n"
        "        f.write(b'x' * (64 * 1024 * 1024))\n"
        "    print('DISK_LIMIT_NOT_ENFORCED')\n"
        "except OSError as e:\n"
        "    print('DISK_LIMITED', e.errno)\n"
    )
    case("磁盘超限被限制", disk_code,
         lambda status, out, err: judge_disk(status, out), timeout=8)

    # 10. 输出截断（stdout 独立 / stderr 独立 / 同一任务合计）
    try:
        r_out = run_case(m, "print('A' * (5 * 1024 * 1024))\n", timeout=8)
        out_status = r_out["status"]
        out_bytes = len(r_out.get("stdout", "").encode("utf-8"))
        ok, detail = judge_output(out_status, out_bytes, args.output_limit)
        add("stdout 输出被截断", ok, detail)
    except Exception as exc:  # noqa: BLE001
        add("stdout 输出被截断", False, f"任务异常: {type(exc).__name__}")
    try:
        r_err = run_case(
            m, "import sys\nsys.stderr.write('B' * (5 * 1024 * 1024))\n", timeout=8)
        err_status = r_err["status"]
        err_bytes = len(r_err.get("stderr", "").encode("utf-8"))
        ok, detail = judge_output(err_status, err_bytes, args.output_limit)
        add("stderr 输出被截断", ok, detail)
    except Exception as exc:  # noqa: BLE001
        add("stderr 输出被截断", False, f"任务异常: {type(exc).__name__}")

    # 10.1 合计限制：必须在**同一个任务**中同时产生 stdout 与 stderr，
    # 不能用两个不同任务的字节数相加冒充合计证据。
    combined_code = (
        "import sys\n"
        "sys.stdout.write('A' * (5 * 1024 * 1024) + '\\n')\n"
        "sys.stderr.write('B' * (5 * 1024 * 1024) + '\\n')\n"
    )
    try:
        r_comb = run_case(m, combined_code, timeout=8)
        comb_status = r_comb["status"]
        comb_stdout = len(r_comb.get("stdout", "").encode("utf-8"))
        comb_stderr = len(r_comb.get("stderr", "").encode("utf-8"))
        ok, detail = judge_total_output(
            comb_status, comb_stdout, comb_stderr,
            args.output_limit, args.output_total_limit)
        add("stdout+stderr 合计输出限制（同一任务）", ok, detail)
    except Exception as exc:  # noqa: BLE001
        add("stdout+stderr 合计输出限制（同一任务）", False,
            f"任务异常: {type(exc).__name__}")

    # 11. 容器残留（必须在人工确认节点身份后才检查）
    if args.docker_check == "local" and node_confirmed:
        try:
            output = subprocess.check_output(
                ["docker", "ps", "-aq", "--filter", "label=zd.sandbox=1"],
                text=True, stderr=subprocess.DEVNULL,
            ).strip()
            ok, detail = judge_container_residue(
                args.docker_check, node_confirmed, output=output)
        except Exception as exc:  # noqa: BLE001
            ok, detail = judge_container_residue(
                args.docker_check, node_confirmed, error=exc)
    else:
        ok, detail = judge_container_residue(
            args.docker_check, node_confirmed)
    add("任务结束后无残留容器", ok, detail)

    # 汇总
    failed = [r for r in results if r["state"] == "FAIL"]
    skipped = [r for r in results if r["state"] == "SKIP"]
    optional_skipped = [r for r in skipped if not r["required"]]
    verdict, code = final_verdict(results)
    print(
        f"\n合计: {len(results)} 项，FAIL {len(failed)}，SKIP {len(skipped)}"
        f"（其中可选 {len(optional_skipped)}）"
    )
    print(f"验收结论: {verdict}")
    if verdict == "INCOMPLETE":
        print("存在必检项 SKIP，不能视为验收通过；请补齐条件后重新执行。")
    return code


def _check_mtls(m: Manager, args, add) -> None:
    """双向 TLS 负向/正向验证"""
    if not (args.client_cert and args.client_key):
        add("双向 TLS：合法客户端证书可访问", False,
            "服务端声明强制 mTLS，但未提供 --client-cert / --client-key")
        return

    positive_ok = False
    try:
        status, _ = m._request("GET", "/health")
        positive_ok = status == 200
        add("双向 TLS：合法客户端证书可访问", positive_ok, f"status={status}")
    except Exception as exc:  # noqa: BLE001
        add("双向 TLS：合法客户端证书可访问", False,
            f"请求异常: {type(exc).__name__}")

    def _judge_negative(label: str, client: Manager) -> None:
        try:
            status, _ = client._request("GET", "/health")
        except Exception as exc:  # noqa: BLE001 - 需要给出异常类型依据
            ok, detail = tls_rejection_of(exc)
            if ok and not positive_ok:
                # 合法证书都无法访问时，负向结果无法归因于证书校验
                ok = False
                detail += "；合法证书请求未成功，无法归因"
            add(label, ok, detail)
        else:
            add(label, False, f"请求成功 status={status}，mTLS 未生效")

    # 无客户端证书：必须在 TLS 层被拒绝（零 HTTP 响应）
    _judge_negative("双向 TLS：无客户端证书被拒绝",
                    Manager(args.url, args.token, args.ca))

    # 错误客户端证书：必须在 TLS 层被拒绝
    if args.invalid_client_cert and args.invalid_client_key:
        _judge_negative(
            "双向 TLS：错误客户端证书被拒绝",
            Manager(args.url, args.token, args.ca,
                    args.invalid_client_cert, args.invalid_client_key),
        )
    else:
        add("双向 TLS：错误客户端证书被拒绝", None,
            "未提供 --invalid-client-cert / --invalid-client-key，无法执行负向测试")

    # 不受信服务端证书：必须由客户端证书校验明确拒绝
    try:
        untrusted = Manager(args.url, args.token, None,
                            args.client_cert, args.client_key)
        status, _ = untrusted._request("GET", "/health")
        add("TLS：不受信服务端证书被拒绝", False, f"请求成功 status={status}")
    except Exception as exc:  # noqa: BLE001
        ssl_exc = ssl_error_of(exc)
        ok = isinstance(ssl_exc, ssl.SSLCertVerificationError)
        add("TLS：不受信服务端证书被拒绝", ok, f"{type(exc).__name__}")


if __name__ == "__main__":
    sys.exit(main())
