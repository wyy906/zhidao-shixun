"""verify_isolation.py 判定逻辑单元测试

全部使用纯函数 / 临时文件，不连接真实管理器，也不执行 fork / 内存耗尽等危险代码。
"""
from __future__ import annotations

import importlib.util
import ssl
from pathlib import Path

import pytest

_SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "verify_isolation.py"
_spec = importlib.util.spec_from_file_location("verify_isolation", _SCRIPT)
vi = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(vi)


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


def _write_client_cert(tmp_path: Path) -> tuple[str, str]:
    from cryptography import x509
    from cryptography.hazmat.primitives import hashes, serialization
    from cryptography.hazmat.primitives.asymmetric import rsa
    from cryptography.x509.oid import NameOID
    import datetime

    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    name = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, "zd-test-client")])
    cert = (
        x509.CertificateBuilder()
        .subject_name(name)
        .issuer_name(name)
        .public_key(key.public_key())
        .serial_number(x509.random_serial_number())
        .not_valid_before(datetime.datetime.now(datetime.timezone.utc) - datetime.timedelta(days=1))
        .not_valid_after(datetime.datetime.now(datetime.timezone.utc) + datetime.timedelta(days=1))
        .sign(key, hashes.SHA256())
    )
    cert_path = tmp_path / "client.crt"
    key_path = tmp_path / "client.key"
    cert_path.write_bytes(cert.public_bytes(serialization.Encoding.PEM))
    key_path.write_bytes(
        key.private_bytes(
            serialization.Encoding.PEM,
            serialization.PrivateFormat.PKCS8,
            serialization.NoEncryption(),
        )
    )
    return str(cert_path), str(key_path)


def test_mtls_client_certificate_loads(tmp_path):
    cert, key = _write_client_cert(tmp_path)
    ctx = vi.Manager.build_ssl_context(None, cert, key)
    assert isinstance(ctx, ssl.SSLContext)


def test_mtls_missing_client_certificate_cannot_pass(tmp_path):
    cert, key = _write_client_cert(tmp_path)
    config = type("Args", (), {
        "client_cert": None,
        "client_key": None,
        "invalid_client_cert": None,
        "invalid_client_key": None,
        "url": "https://127.0.0.1:1",
        "token": "x",
        "ca": None,
    })()
    recorded = []
    vi._check_mtls(None, config, lambda n, ok, d, required=True: recorded.append((n, ok)))
    assert any(ok is False for _, ok in recorded)


def test_cert_without_key_is_rejected():
    with pytest.raises(ValueError):
        vi.Manager.build_ssl_context(None, "client.crt", None)


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


def test_network_requires_explicit_unreachable_evidence():
    assert vi.judge_network("failed", "", "boom")[0] is False
    assert vi.judge_network("succeeded", "", "")[0] is False
    assert vi.judge_network("succeeded", "NET_REACHABLE", "")[0] is False
    assert vi.judge_network("succeeded", "NET_BLOCKED ConnectionRefusedError 111", "")[0] is True


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
    assert vi.judge_output("failed", 10, 65536)[0] is False
    assert vi.judge_output("succeeded", 0, 65536)[0] is False
    assert vi.judge_output("succeeded", 32768, 65536)[0] is True
    assert vi.judge_output("succeeded", 70000, 65536)[0] is False
