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
    assert vi.judge_output("succeeded", 32768, 32768)[0] is True
    assert vi.judge_output("succeeded", 0, 32768)[0] is False
    assert vi.judge_output("failed", 100, 32768)[0] is False
    assert vi.judge_output("succeeded", 40000, 32768)[0] is False


def test_stderr_truncation_uses_same_rule():
    assert vi.judge_output("succeeded", 32768, 32768)[0] is True
    assert vi.judge_output("failed", 32768, 32768)[0] is False


def test_total_output_limit():
    assert vi.judge_total_output("succeeded", 32768, 32768, 65536)[0] is True
    assert vi.judge_total_output("succeeded", 40000, 40000, 65536)[0] is False
    assert vi.judge_total_output("succeeded", 0, 0, 65536)[0] is False
    assert vi.judge_total_output("failed", 32768, 32768, 65536)[0] is False


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
    ok, detail = vi.judge_host_marker_scope(on_execution_node=False)
    assert ok is None
    assert "无法确认" in detail


def test_docker_cli_not_on_execution_node_is_skip():
    ok, _ = vi.judge_container_residue("local", on_execution_node=False)
    assert ok is None
    ok, _ = vi.judge_container_residue("skip", on_execution_node=True)
    assert ok is None
    ok, _ = vi.judge_container_residue("local", True, output="")
    assert ok is True


def test_node_identity_cannot_be_proven_by_flag_alone():
    assert vi.judge_node_identity(False, True)[0] is None
    assert vi.judge_node_identity(True, False)[0] is None
    assert vi.judge_node_identity(True, True)[0] is True


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

    def _signed(key, cn, *, ca, is_server=False, client_auth=False):
        extra = [
            x509.SubjectKeyIdentifier.from_public_key(key.public_key()),
            x509.AuthorityKeyIdentifier.from_issuer_public_key(ca_key.public_key()),
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
            .subject_name(_name(cn)).issuer_name(ca.subject)
            .public_key(key.public_key())
            .serial_number(x509.random_serial_number())
            .not_valid_before(now - timedelta(days=1))
            .not_valid_after(now + timedelta(days=30))
        )
        for ext in extra:
            builder = builder.add_extension(ext, critical=False)
        return builder.sign(ca_key, hashes.SHA256())

    server_key = _key()
    server_cert = _signed(server_key, "127.0.0.1", ca=ca_cert, is_server=True)
    client_key = _key()
    client_cert = _signed(client_key, "zd-test-client", ca=ca_cert, client_auth=True)
    rogue_key = _key()
    rogue_cert = _signed(rogue_key, "rogue-client", ca=ca_cert, client_auth=True)
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

    paths = {
        "ca": tmp_path / "ca.crt",
        "server_cert": tmp_path / "server.crt",
        "server_key": tmp_path / "server.key",
        "client_cert": tmp_path / "client.crt",
        "client_key": tmp_path / "client.key",
        "other_cert": tmp_path / "other-client.crt",
        "other_key": tmp_path / "other-client.key",
    }
    paths["ca"].write_bytes(ca_cert.public_bytes(serialization.Encoding.PEM))
    paths["server_cert"].write_bytes(server_cert.public_bytes(serialization.Encoding.PEM))
    _write_key(paths["server_key"], server_key)
    paths["client_cert"].write_bytes(client_cert.public_bytes(serialization.Encoding.PEM))
    _write_key(paths["client_key"], client_key)
    paths["other_cert"].write_bytes(other_ca.public_bytes(serialization.Encoding.PEM))
    _write_key(paths["other_key"], other_key)
    return {k: str(v) for k, v in paths.items()}


def _server_context(bundle: dict, require_client: bool) -> ssl.SSLContext:
    ctx = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
    ctx.load_cert_chain(bundle["server_cert"], bundle["server_key"])
    ctx.maximum_version = ssl.TLSVersion.TLSv1_2
    if require_client:
        ctx.verify_mode = ssl.CERT_REQUIRED
        ctx.load_verify_locations(bundle["ca"])
    return ctx


def _handshake(server_ctx: ssl.SSLContext, client_ctx: ssl.SSLContext) -> bool:
    """本机完成一次 TLS 握手 + 一个字节往返，返回是否成功"""
    listener = socket.socket()
    listener.bind(("127.0.0.1", 0))
    listener.listen(1)
    port = listener.getsockname()[1]
    errors: list[BaseException] = []

    def serve():
        conn, _ = listener.accept()
        try:
            tls = server_ctx.wrap_socket(conn, server_side=True)
            tls.settimeout(3)
            data = tls.recv(1)
            tls.sendall(b"k" if data else b"")
        except BaseException as exc:  # noqa: BLE001
            errors.append(exc)
        finally:
            conn.close()
            listener.close()

    thread = threading.Thread(target=serve, daemon=True)
    thread.start()
    ok = False
    raw = socket.create_connection(("127.0.0.1", port), timeout=3)
    try:
        tls = client_ctx.wrap_socket(raw, server_hostname="127.0.0.1")
        tls.sendall(b"x")
        ok = tls.recv(1) == b"k"
    except BaseException:  # noqa: BLE001
        ok = False
    finally:
        raw.close()
    thread.join(timeout=5)
    return ok


def test_mtls_valid_handshake_succeeds(tmp_path):
    bundle = _write_cert_bundle(tmp_path)
    server = _server_context(bundle, require_client=True)
    client = vi.Manager.build_ssl_context(
        bundle["ca"], bundle["client_cert"], bundle["client_key"])
    assert _handshake(server, client) is True


def test_mtls_without_client_certificate_fails(tmp_path):
    bundle = _write_cert_bundle(tmp_path)
    server = _server_context(bundle, require_client=True)
    client = vi.Manager.build_ssl_context(
        bundle["ca"], None, None)
    assert _handshake(server, client) is False


def test_mtls_with_untrusted_client_certificate_fails(tmp_path):
    bundle = _write_cert_bundle(tmp_path)
    server = _server_context(bundle, require_client=True)
    client = vi.Manager.build_ssl_context(
        bundle["ca"], bundle["other_cert"], bundle["other_key"])
    assert _handshake(server, client) is False


def test_untrusted_server_certificate_fails(tmp_path):
    bundle = _write_cert_bundle(tmp_path)
    server = _server_context(bundle, require_client=False)
    client = ssl.create_default_context()   # 不信任私有 CA
    assert _handshake(server, client) is False


def test_mtls_valid_cert_wrong_token_gets_401(tmp_path):
    bundle = _write_cert_bundle(tmp_path)
    server_ctx = _server_context(bundle, require_client=True)
    listener = socket.socket()
    listener.bind(("127.0.0.1", 0))
    listener.listen(1)
    port = listener.getsockname()[1]

    def serve():
        conn, _ = listener.accept()
        try:
            tls = server_ctx.wrap_socket(conn, server_side=True)
            tls.recv(4096)
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
    manager = vi.Manager(
        f"https://127.0.0.1:{port}", "wrong", bundle["ca"],
        bundle["client_cert"], bundle["client_key"],
    )
    ok, detail = manager.probe_wrong_token()
    thread.join(timeout=5)
    assert ok is True
    assert "401" in detail


def test_certificate_and_key_mismatch_fails(tmp_path):
    bundle = _write_cert_bundle(tmp_path)
    with pytest.raises(ssl.SSLError):
        vi.Manager.build_ssl_context(
            bundle["ca"], bundle["client_cert"], bundle["server_key"])
