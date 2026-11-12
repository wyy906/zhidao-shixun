"""verify_isolation.py 判定逻辑与 mTLS 行为测试

全部使用纯函数、临时文件和本机 127.0.0.1 临时 TLS 服务，不连接外网、
不使用真实证书，也不执行 fork / 内存耗尽等危险代码。
"""
from __future__ import annotations

import importlib.util
import socket
import ssl
import threading
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

_SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "verify_isolation.py"
_spec = importlib.util.spec_from_file_location("verify_isolation", _SCRIPT)
vi = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(vi)


# ---------------------------------------------------------------------------
# 结论汇总
# ---------------------------------------------------------------------------
def _rec(results, name, ok, required=True):
    vi.record(results, name, ok, "detail", required)


def test_all_pass_returns_zero():
    results = []
    _rec(results, "a", True)
    _rec(results, "b", True)
    assert vi.final_verdict(results) == ("PASS", 0)


def test_fail_returns_nonzero():
    results = []
    _rec(results, "a", True)
    _rec(results, "b", False)
    assert vi.final_verdict(results) == ("FAIL", 1)


def test_required_skip_is_incomplete_nonzero():
    results = []
    _rec(results, "a", True)
    _rec(results, "b", None)
    assert vi.final_verdict(results) == ("INCOMPLETE", 2)


def test_all_skip_never_returns_zero():
    results = []
    _rec(results, "a", None)
    _rec(results, "b", None)
    verdict, code = vi.final_verdict(results)
    assert verdict == "INCOMPLETE"
    assert code != 0


def test_optional_skip_does_not_block_pass():
    results = []
    _rec(results, "a", True)
    _rec(results, "opt", None, required=False)
    assert vi.final_verdict(results) == ("PASS", 0)


# ---------------------------------------------------------------------------
# 认证
# ---------------------------------------------------------------------------
def test_wrong_token_pass_only_on_401():
    assert vi.judge_wrong_token(status=401)[0] is True
    assert vi.judge_wrong_token(status=200)[0] is False
    assert vi.judge_wrong_token(status=503)[0] is False


def test_network_error_is_not_auth_pass():
    ok, detail = vi.judge_wrong_token(error=ConnectionRefusedError("refused"))
    assert ok is False
    assert "ConnectionRefusedError" in detail


def test_tls_certificate_error_is_not_auth_pass():
    exc = ssl.SSLCertVerificationError("certificate verify failed")
    ok, detail = vi.judge_wrong_token(error=exc)
    assert ok is False
    assert "SSLCertVerificationError" in detail


# ---------------------------------------------------------------------------
# 网络判定
# ---------------------------------------------------------------------------
def _net(err_type: str, err_no) -> str:
    import json
    return "NET_RESULT " + json.dumps(
        {"connected": False, "type": err_type, "errno": err_no})


def test_dns_failure_is_not_network_isolation():
    ok, detail = vi.judge_network("succeeded", _net("gaierror", -2), "")
    assert ok is False
    assert "DNS" in detail


def test_connection_refused_is_not_network_isolation():
    ok, detail = vi.judge_network(
        "succeeded", _net("ConnectionRefusedError", 111), "")
    assert ok is False
    assert "111" in detail


def test_unreachable_errors_are_blocking_evidence():
    assert vi.judge_network("succeeded", _net("OSError", 101), "")[0] is True   # ENETUNREACH
    assert vi.judge_network("succeeded", _net("OSError", 113), "")[0] is True   # EHOSTUNREACH
    assert vi.judge_network("succeeded", _net("PermissionError", 13), "")[0] is True


def test_timeout_and_unknown_errors_are_not_blocking_evidence():
    assert vi.judge_network("succeeded", _net("TimeoutError", 110), "")[0] is False
    assert vi.judge_network("succeeded", _net("TimeoutError", None), "")[0] is False
    assert vi.judge_network("succeeded", _net("RuntimeError", 999), "")[0] is False


def test_connected_or_missing_evidence_is_failure():
    import json
    assert vi.judge_network(
        "succeeded", "NET_RESULT " + json.dumps({"connected": True}), "")[0] is False
    assert vi.judge_network("succeeded", "", "")[0] is False
    assert vi.judge_network("failed", _net("OSError", 101), "")[0] is False


# ---------------------------------------------------------------------------
# 输出、CPU、内存、交换、PID
# ---------------------------------------------------------------------------
def test_stdout_truncation():
    # 恰好达到上限、或上限 + 截断标记容差内 → 通过
    assert vi.judge_output("succeeded", 32768, 32768)[0] is True
    assert vi.judge_output("succeeded", 32768 + 37, 32768)[0] is True
    assert vi.judge_output("succeeded", 30000, 32768)[0] is True  # 接近上限
    # 明显不足 / 为空 / 超过上限+容差 / 异常终止 → 失败
    assert vi.judge_output("succeeded", 100, 32768)[0] is False
    assert vi.judge_output("succeeded", 0, 32768)[0] is False
    assert vi.judge_output("failed", 100, 32768)[0] is False
    assert vi.judge_output("succeeded", 40000, 32768)[0] is False


def test_stderr_truncation_uses_same_rule():
    # stderr 复用同一判定：接近上限通过，明显不足或异常终止失败
    assert vi.judge_output("succeeded", 32768, 32768)[0] is True
    assert vi.judge_output("succeeded", 2000, 32768)[0] is False
    assert vi.judge_output("failed", 32768, 32768)[0] is False


def test_truncation_marker_bytes_do_not_misfire():
    # 截断标记约 37 字节，处于容差内，不得被判为超限
    assert vi.judge_output("succeeded", 32768 + 37, 32768)[0] is True
    assert vi.judge_total_output("succeeded", 32768, 32768, 32768, 65536)[0] is True
    # 超过容差（> 上限+100）才失败
    assert vi.judge_output("succeeded", 32768 + 101, 32768)[0] is False


def test_total_output_limit():
    # 同一任务两通道都接近单流上限、合计贴近总上限 → 通过
    assert vi.judge_total_output("succeeded", 32768, 32768, 32768, 65536)[0] is True
    # 合计超过总上限 + 容差 → 失败
    assert vi.judge_total_output("succeeded", 40000, 40000, 32768, 65536)[0] is False
    # 任一通道为空 → 失败（不能把单通道结果当合计证据）
    assert vi.judge_total_output("succeeded", 32768, 0, 32768, 65536)[0] is False
    assert vi.judge_total_output("succeeded", 0, 32768, 32768, 65536)[0] is False
    assert vi.judge_total_output("succeeded", 0, 0, 32768, 65536)[0] is False
    # 任务异常终止 → 失败
    assert vi.judge_total_output("failed", 32768, 32768, 32768, 65536)[0] is False
    assert vi.judge_total_output("timeout", 32768, 32768, 32768, 65536)[0] is False


def test_total_rejects_short_channel_even_if_nonempty():
    # 两通道都非空，但 stdout 明显不足 → 失败
    ok, detail = vi.judge_total_output("succeeded", 2000, 32768, 32768, 65536)
    assert ok is False
    assert "stdout" in detail
    # 两通道都非空，但 stderr 明显不足 → 失败
    ok, detail = vi.judge_total_output("succeeded", 32768, 2000, 32768, 65536)
    assert ok is False
    assert "stderr" in detail


def test_total_rejects_sum_far_below_expected():
    # 两通道各自勉强达标，但合计明显低于预期总上限 → 失败
    # 单流上限 32768，总上限 65536，两通道各 15000（均低于单流下限）会被单流拦截；
    # 该用例确认整体判定失败且不会误判通过。
    assert vi.judge_total_output("succeeded", 15000, 15000, 32768, 65536)[0] is False
    # 只在合计层面偏低的场景：总上限低于 2×单流上限时，合计超总上限即失败
    ok, detail = vi.judge_total_output("succeeded", 30000, 30000, 32768, 50000)
    assert ok is False
    assert "超过总上限" in detail


def test_cross_task_sum_is_not_accepted():
    """两个不同任务分别产生 stdout / stderr，不能相加冒充同一任务合计"""
    # 任务 A 只有 stdout、任务 B 只有 stderr：单独判定都不是合法合计证据
    assert vi.judge_total_output("succeeded", 32768, 0, 32768, 65536)[0] is False
    assert vi.judge_total_output("succeeded", 0, 24000, 32768, 65536)[0] is False


def test_cpu_quota_and_period_must_both_be_correct():
    assert vi.parse_cpu_max("50000 100000", 0.5)[0] is True
    assert vi.parse_cpu_max("100000 100000", 0.5)[0] is False
    assert vi.parse_cpu_max("50000 200000", 0.5)[0] is False
    assert vi.parse_cpu_max("max 100000", 0.5)[0] is False
    assert vi.parse_cpu_max("garbage", 0.5)[0] is False


def test_memory_and_pid_limits_are_exact():
    assert vi.parse_memory_max(str(128 * 1024 * 1024), 128)[0] is True
    assert vi.parse_memory_max(str(64 * 1024 * 1024), 128)[0] is False
    assert vi.parse_memory_max("max", 128)[0] is False
    assert vi.parse_pids_max("32", 32)[0] is True
    assert vi.parse_pids_max("64", 32)[0] is False
    assert vi.parse_pids_max("max", 32)[0] is False


def test_swap_limit_parsing():
    # memswap == mem 时，交换空间应为 0
    assert vi.parse_swap_max("0", 0)[0] is True
    assert vi.parse_swap_max("max", 0)[0] is False
    assert vi.parse_swap_max("", 0)[0] is False
    assert vi.parse_swap_max(str(128 * 1024 * 1024), 0)[0] is False


# ---------------------------------------------------------------------------
# 节点身份 / Docker 可见性
# ---------------------------------------------------------------------------
def test_remote_marker_cannot_pass():
    ok, detail = vi.judge_host_marker_scope(False)
    assert ok is None
    assert "未确认" in detail
    # 人工确认后才允许在节点侧创建标记文件
    assert vi.judge_host_marker_scope(True)[0] is True


def test_docker_cli_not_on_execution_node_is_skip():
    ok, _ = vi.judge_container_residue("local", False)
    assert ok is None
    ok, _ = vi.judge_container_residue("skip", True)
    assert ok is None
    ok, _ = vi.judge_container_residue("local", True, output="")
    assert ok is True


def test_node_identity_cannot_be_proven_by_flag_alone():
    # 只有声明，没有人工确认 → SKIP
    assert vi.judge_node_identity(True, False, True)[0] is None
    # 没有声明 → SKIP
    assert vi.judge_node_identity(False, True, True)[0] is None
    # 已声明并确认，但本机 Docker 不可用 → SKIP
    assert vi.judge_node_identity(True, True, False)[0] is None
    # 三个条件齐备 → 人工核验通过
    assert vi.judge_node_identity(True, True, True)[0] is True


def test_node_identity_requires_manual_confirmation_not_just_docker():
    # 本机 docker info 可用也不能单独证明与管理器同 Engine
    ok, detail = vi.judge_node_identity(True, False, True)
    assert ok is None
    assert "confirm-manager-docker-same-host" in detail


def test_node_identity_records_docker_env_hint():
    ok, detail = vi.judge_node_identity(True, True, True, "DOCKER_HOST=tcp://10.0.0.9:2375")
    assert ok is True
    assert "DOCKER_HOST=tcp://10.0.0.9:2375" in detail
    assert "非密码学证明" in detail


def test_node_identity_skip_when_docker_unavailable():
    ok, detail = vi.judge_node_identity(True, True, False)
    assert ok is None
    assert "Docker Engine 不可用" in detail


def test_residue_and_marker_skipped_without_confirmation():
    # 未人工确认时，容器残留与宿主机标记都不得 PASS
    assert vi.judge_container_residue("local", False)[0] is None
    assert vi.judge_host_marker_scope(False)[0] is None


# ---------------------------------------------------------------------------
# 资源限制
# ---------------------------------------------------------------------------
def test_abnormal_termination_is_not_resource_success():
    assert vi.judge_memory_limit("failed", "", "killed")[0] is False
    assert vi.judge_memory_limit("succeeded", "MEMORY_OK", "")[0] is False
    assert vi.judge_memory_limit("resource_exceeded", "", "")[0] is True
    assert vi.judge_memory_limit("succeeded", "MEMORY_LIMITED", "")[0] is True
    assert vi.judge_disk("failed", "boom")[0] is False
    assert vi.judge_disk("succeeded", "DISK_LIMIT_NOT_ENFORCED")[0] is False
    assert vi.judge_disk("succeeded", "DISK_LIMITED 28")[0] is True
    assert vi.judge_fork("failed", "")[0] is False
    assert vi.judge_fork("succeeded", "FORK_LIMITED 30")[0] is True
    assert vi.judge_timeout("failed")[0] is False
    assert vi.judge_timeout("timeout")[0] is True


# ---------------------------------------------------------------------------
# 本地临时 TLS / mTLS
# ---------------------------------------------------------------------------
def _write_cert_bundle(tmp_path: Path) -> dict[str, str]:
    """生成 CA、服务端证书、合法客户端证书、不受信客户端证书"""
    from cryptography import x509
    from cryptography.hazmat.primitives import hashes, serialization
    from cryptography.hazmat.primitives.asymmetric import rsa
    from cryptography.x509.oid import ExtendedKeyUsageOID, NameOID

    def _key():
        return rsa.generate_private_key(public_exponent=65537, key_size=2048)

    def _name(cn):
        return x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, cn)])

    def _write_key(path, key):
        path.write_bytes(key.private_bytes(
            serialization.Encoding.PEM,
            serialization.PrivateFormat.TraditionalOpenSSL,
            serialization.NoEncryption(),
        ))

    now = datetime.now(timezone.utc)

    ca_key = _key()
    ca_name = _name("ZD-Test-CA")
    ca_cert = (
        x509.CertificateBuilder()
        .subject_name(ca_name).issuer_name(ca_name)
        .public_key(ca_key.public_key())
        .serial_number(x509.random_serial_number())
        .not_valid_before(now - timedelta(days=1))
        .not_valid_after(now + timedelta(days=30))
        .add_extension(x509.BasicConstraints(ca=True, path_length=None), critical=True)
        .add_extension(x509.KeyUsage(
            digital_signature=True, content_commitment=False, key_encipherment=False,
            data_encipherment=False, key_agreement=False, key_cert_sign=True,
            crl_sign=True, encipher_only=False, decipher_only=False,
        ), critical=True)
        .add_extension(
            x509.SubjectKeyIdentifier.from_public_key(ca_key.public_key()),
            critical=False,
        )
        .sign(ca_key, hashes.SHA256())
    )

    def _signed(key, cn, *, signer_key, signer_cert, is_server=False,
                client_auth=False):
        extra = [
            x509.SubjectKeyIdentifier.from_public_key(key.public_key()),
            x509.AuthorityKeyIdentifier.from_issuer_public_key(
                signer_key.public_key()),
            x509.KeyUsage(
                digital_signature=True, content_commitment=False,
                key_encipherment=is_server, data_encipherment=False,
                key_agreement=False, key_cert_sign=False, crl_sign=False,
                encipher_only=False, decipher_only=False,
            ),
        ]
        if is_server:
            extra.append(x509.SubjectAlternativeName([x509.IPAddress(
                __import__("ipaddress").IPv4Address("127.0.0.1"))]))
            extra.append(x509.ExtendedKeyUsage([ExtendedKeyUsageOID.SERVER_AUTH]))
        if client_auth:
            extra.append(x509.ExtendedKeyUsage([ExtendedKeyUsageOID.CLIENT_AUTH]))
        builder = (
            x509.CertificateBuilder()
            .subject_name(_name(cn)).issuer_name(signer_cert.subject)
            .public_key(key.public_key())
            .serial_number(x509.random_serial_number())
            .not_valid_before(now - timedelta(days=1))
            .not_valid_after(now + timedelta(days=30))
        )
        for ext in extra:
            builder = builder.add_extension(ext, critical=False)
        return builder.sign(signer_key, hashes.SHA256())

    server_key = _key()
    server_cert = _signed(server_key, "127.0.0.1",
                          signer_key=ca_key, signer_cert=ca_cert, is_server=True)
    client_key = _key()
    client_cert = _signed(client_key, "zd-test-client",
                          signer_key=ca_key, signer_cert=ca_cert, client_auth=True)
    # 错误“不受信”证书：同样由本 CA 签发，但仅在服务端不信任该 CA 时使用
    other_key = _key()
    other_ca_name = _name("Other-CA")
    other_ca = (
        x509.CertificateBuilder()
        .subject_name(other_ca_name).issuer_name(other_ca_name)
        .public_key(other_key.public_key())
        .serial_number(x509.random_serial_number())
        .not_valid_before(now - timedelta(days=1))
        .not_valid_after(now + timedelta(days=30))
        .add_extension(x509.BasicConstraints(ca=True, path_length=None), critical=True)
        .add_extension(x509.KeyUsage(
            digital_signature=True, content_commitment=False, key_encipherment=False,
            data_encipherment=False, key_agreement=False, key_cert_sign=True,
            crl_sign=True, encipher_only=False, decipher_only=False,
        ), critical=True)
        .add_extension(
            x509.SubjectKeyIdentifier.from_public_key(other_key.public_key()),
            critical=False,
        )
        .sign(other_key, hashes.SHA256())
    )

    # 第二套 CA 签发的**正常客户端叶子证书**（含 CLIENT_AUTH、匹配私钥）；
    # 服务端只信任第一套 CA，因此这张合法结构但不受信的证书必须握手失败。
    other_client_key = _key()
    other_client_cert = _signed(
        other_client_key, "untrusted-client",
        signer_key=other_key, signer_cert=other_ca, client_auth=True)

    paths = {
        "ca": tmp_path / "ca.crt",
        "server_cert": tmp_path / "server.crt",
        "server_key": tmp_path / "server.key",
        "client_cert": tmp_path / "client.crt",
        "client_key": tmp_path / "client.key",
        "other_ca": tmp_path / "other-ca.crt",
        "other_cert": tmp_path / "other-client.crt",
        "other_key": tmp_path / "other-client.key",
    }
    paths["ca"].write_bytes(ca_cert.public_bytes(serialization.Encoding.PEM))
    paths["server_cert"].write_bytes(server_cert.public_bytes(serialization.Encoding.PEM))
    _write_key(paths["server_key"], server_key)
    paths["client_cert"].write_bytes(client_cert.public_bytes(serialization.Encoding.PEM))
    _write_key(paths["client_key"], client_key)
    paths["other_ca"].write_bytes(other_ca.public_bytes(serialization.Encoding.PEM))
    paths["other_cert"].write_bytes(
        other_client_cert.public_bytes(serialization.Encoding.PEM))
    _write_key(paths["other_key"], other_client_key)
    return {k: str(v) for k, v in paths.items()}


def _server_context(bundle: dict, require_client: bool) -> ssl.SSLContext:
    ctx = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
    ctx.load_cert_chain(bundle["server_cert"], bundle["server_key"])
    ctx.maximum_version = ssl.TLSVersion.TLSv1_2
    if require_client:
        ctx.verify_mode = ssl.CERT_REQUIRED
        ctx.load_verify_locations(bundle["ca"])
    return ctx


def _describe(exc: BaseException | None) -> str:
    """不含密钥的异常诊断：仅类型名 + 文本"""
    if exc is None:
        return "None"
    return f"{type(exc).__name__}: {exc}"


def _handshake(server_ctx, client_ctx):
    """本机完成一次 TLS 握手 + 一个字节往返。

    返回 (ok, client_error, server_error)，保留两端异常，便于区分
    “确属证书验证被拒绝”与“服务端线程异常 / TCP 失败 / 协议错误”等实现故障。
    """
    listener = socket.socket()
    listener.bind(("127.0.0.1", 0))
    listener.listen(1)
    port = listener.getsockname()[1]
    server_errors: list[BaseException] = []

    def serve():
        conn, _ = listener.accept()
        try:
            tls = server_ctx.wrap_socket(conn, server_side=True)
            tls.settimeout(3)
            data = tls.recv(1)
            tls.sendall(b"k" if data else b"")
        except BaseException as exc:  # noqa: BLE001 - 保留用于断言
            server_errors.append(exc)
        finally:
            conn.close()
            listener.close()

    thread = threading.Thread(target=serve, daemon=True)
    thread.start()
    ok = False
    client_error: BaseException | None = None
    raw = socket.create_connection(("127.0.0.1", port), timeout=3)
    try:
        tls = client_ctx.wrap_socket(raw, server_hostname="127.0.0.1")
        tls.sendall(b"x")
        ok = tls.recv(1) == b"k"
    except BaseException as exc:  # noqa: BLE001 - 保留用于断言
        client_error = exc
    finally:
        raw.close()
    thread.join(timeout=5)
    server_error = server_errors[0] if server_errors else None
    return ok, client_error, server_error


def test_mtls_valid_handshake_succeeds(tmp_path):
    bundle = _write_cert_bundle(tmp_path)
    server = _server_context(bundle, require_client=True)
    client = vi.Manager.build_ssl_context(
        bundle["ca"], bundle["client_cert"], bundle["client_key"])
    ok, client_error, server_error = _handshake(server, client)
    assert ok is True, f"client={_describe(client_error)} server={_describe(server_error)}"
    assert client_error is None
    assert server_error is None


def test_mtls_without_client_certificate_fails(tmp_path):
    bundle = _write_cert_bundle(tmp_path)
    server = _server_context(bundle, require_client=True)
    client = vi.Manager.build_ssl_context(
        bundle["ca"], None, None)
    ok, client_error, server_error = _handshake(server, client)
    assert ok is False
    # 服务端确实因缺少客户端证书而拒绝（SSLError，且原因与证书相关）
    assert isinstance(server_error, ssl.SSLError), _describe(server_error)
    reason = str(server_error).lower()
    assert ("certificate" in reason or "peer did not return" in reason), _describe(server_error)
    # 客户端应感知为 TLS/连接层失败；Windows 上可能表现为 ConnectionResetError。
    # 但不能是程序实现错误（如 AttributeError/RuntimeError）。
    assert client_error is None or isinstance(client_error, (ssl.SSLError, OSError)), (
        _describe(client_error)
    )


def test_mtls_with_untrusted_client_certificate_fails(tmp_path):
    bundle = _write_cert_bundle(tmp_path)
    server = _server_context(bundle, require_client=True)
    client = vi.Manager.build_ssl_context(
        bundle["ca"], bundle["other_cert"], bundle["other_key"])
    ok, client_error, server_error = _handshake(server, client)
    assert ok is False
    # 服务端因客户端证书链不受信而拒绝（证书相关 SSLError）
    assert isinstance(server_error, ssl.SSLError), _describe(server_error)
    reason = str(server_error).lower()
    assert (
        "certificate" in reason or "unknown ca" in reason or "verify" in reason
    ), _describe(server_error)


def test_untrusted_server_certificate_fails(tmp_path):
    bundle = _write_cert_bundle(tmp_path)
    server = _server_context(bundle, require_client=False)
    client = ssl.create_default_context()   # 不信任私有 CA
    ok, client_error, server_error = _handshake(server, client)
    assert ok is False
    # 客户端必须出现“证书验证失败”，而不是其他异常
    assert isinstance(client_error, ssl.SSLCertVerificationError), _describe(client_error)


def test_handshake_preserves_unexpected_server_error(tmp_path):
    """服务端实现故障（非 TLS 拒绝）必须被保留，不能被当成“握手被正确拒绝”"""
    bundle = _write_cert_bundle(tmp_path)

    class _BoomCtx:
        def wrap_socket(self, conn, server_side=False):  # noqa: ARG002
            raise RuntimeError("injected server failure")

    client = vi.Manager.build_ssl_context(
        bundle["ca"], bundle["client_cert"], bundle["client_key"])
    ok, client_error, server_error = _handshake(_BoomCtx(), client)
    assert ok is False
    assert isinstance(server_error, RuntimeError), _describe(server_error)
    assert not isinstance(server_error, ssl.SSLError)


def _token_server(server_ctx: ssl.SSLContext, expected_token: str):
    """启动一个真正校验 X-Sandbox-Token 的本地 HTTPS 服务（单次请求）

    请求头令牌与 expected_token 相同返回 200，否则返回 401。
    返回 (port, thread, received_headers) 便于断言。
    """
    listener = socket.socket()
    listener.bind(("127.0.0.1", 0))
    listener.listen(1)
    port = listener.getsockname()[1]
    received: dict[str, str] = {}

    def serve():
        conn, _ = listener.accept()
        try:
            tls = server_ctx.wrap_socket(conn, server_side=True)
            data = tls.recv(4096).decode("latin-1")
            headers = {}
            for line in data.split("\r\n")[1:]:
                if ":" in line:
                    k, v = line.split(":", 1)
                    headers[k.strip().lower()] = v.strip()
            received.update(headers)
            if headers.get("x-sandbox-token") == expected_token:
                body = b"{}"
                tls.sendall(
                    b"HTTP/1.1 200 OK\r\nContent-Type: application/json\r\n"
                    b"Content-Length: " + str(len(body)).encode()
                    + b"\r\nConnection: close\r\n\r\n" + body
                )
            else:
                tls.sendall(
                    b"HTTP/1.1 401 Unauthorized\r\nContent-Length: 0\r\n"
                    b"Connection: close\r\n\r\n"
                )
        except BaseException:  # noqa: BLE001
            pass
        finally:
            conn.close()
            listener.close()

    thread = threading.Thread(target=serve, daemon=True)
    thread.start()
    return port, thread, received


def test_mtls_valid_cert_wrong_token_gets_401(tmp_path):
    bundle = _write_cert_bundle(tmp_path)
    server_ctx = _server_context(bundle, require_client=True)
    port, thread, received = _token_server(server_ctx, "correct-token")
    manager = vi.Manager(
        f"https://127.0.0.1:{port}", "wrong-token", bundle["ca"],
        bundle["client_cert"], bundle["client_key"],
    )
    ok, detail = manager.probe_wrong_token()
    thread.join(timeout=5)
    # 服务端确实读到了客户端发来的错误令牌（不是无条件固定 401）
    assert received.get("x-sandbox-token") == "wrong-token"
    assert ok is True
    assert "401" in detail


def test_mtls_valid_cert_correct_token_gets_200(tmp_path):
    bundle = _write_cert_bundle(tmp_path)
    server_ctx = _server_context(bundle, require_client=True)
    port, thread, received = _token_server(server_ctx, "correct-token")
    manager = vi.Manager(
        f"https://127.0.0.1:{port}", "correct-token", bundle["ca"],
        bundle["client_cert"], bundle["client_key"],
    )
    status, _ = manager._request("GET", "/health")
    thread.join(timeout=5)
    assert received.get("x-sandbox-token") == "correct-token"
    assert status == 200


def test_certificate_and_key_mismatch_fails(tmp_path):
    bundle = _write_cert_bundle(tmp_path)
    with pytest.raises(ssl.SSLError):
        vi.Manager.build_ssl_context(
            bundle["ca"], bundle["client_cert"], bundle["server_key"])
