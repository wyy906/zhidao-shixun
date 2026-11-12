"""沙箱管理器启动配置测试：TLS 强制、mTLS 完整性、HTTP 仅限本机开发"""
import ssl

import pytest

from sandbox_manager.__main__ import build_uvicorn_kwargs
from sandbox_manager.config import ManagerConfig

TOKEN = "test-token"
IMAGE = "zd-sandbox-python@sha256:" + "b" * 64


def _cfg(**overrides) -> ManagerConfig:
    data = {"token": TOKEN, "image": IMAGE, "allow_insecure_http": True}
    data.update(overrides)
    return ManagerConfig(**data)


def _cert_files(tmp_path):
    cert = tmp_path / "server.crt"
    key = tmp_path / "server.key"
    ca = tmp_path / "ca.crt"
    for path in (cert, key, ca):
        path.write_text("dummy", encoding="utf-8")
    return str(cert), str(key), str(ca)


# ===========================================================================
# 明文 HTTP 仅允许本机开发
# ===========================================================================
def test_production_requires_tls():
    cfg = _cfg(allow_insecure_http=False)
    with pytest.raises(ValueError, match="HTTPS"):
        cfg.validate()


def test_insecure_http_allowed_only_on_loopback():
    _cfg(host="127.0.0.1").validate()
    _cfg(host="localhost").validate()
    with pytest.raises(ValueError, match="回环"):
        _cfg(host="0.0.0.0").validate()
    with pytest.raises(ValueError, match="回环"):
        _cfg(host="10.0.0.5").validate()


# ===========================================================================
# TLS / 双向 TLS 完整性
# ===========================================================================
def test_tls_files_must_exist_and_pair(tmp_path):
    cert, key, ca = _cert_files(tmp_path)

    _cfg(tls_cert_file=cert, tls_key_file=key).validate()
    _cfg(tls_cert_file=cert, tls_key_file=key, tls_client_ca_file=ca).validate()

    with pytest.raises(ValueError, match="同时配置"):
        _cfg(tls_cert_file=cert).validate()
    with pytest.raises(ValueError, match="同时配置"):
        _cfg(tls_key_file=key).validate()
    with pytest.raises(ValueError, match="同时配置"):
        _cfg(tls_client_ca_file=ca, tls_cert_file=cert, tls_key_file="").validate()
    with pytest.raises(ValueError, match="双向 TLS"):
        _cfg(tls_client_ca_file=ca, tls_cert_file="", tls_key_file="").validate()
    with pytest.raises(ValueError, match="不存在"):
        _cfg(tls_cert_file=str(tmp_path / "missing.crt"),
             tls_key_file=str(tmp_path / "missing.key")).validate()


# ===========================================================================
# uvicorn 启动参数：不存在“证书失败后自动降级为 HTTP”
# ===========================================================================
def test_uvicorn_uses_tls_when_configured(tmp_path):
    cert, key, ca = _cert_files(tmp_path)
    kwargs = build_uvicorn_kwargs(_cfg(tls_cert_file=cert, tls_key_file=key))
    assert kwargs["ssl_certfile"] == cert
    assert kwargs["ssl_keyfile"] == key
    assert "ssl_ca_certs" not in kwargs

    kwargs = build_uvicorn_kwargs(
        _cfg(tls_cert_file=cert, tls_key_file=key, tls_client_ca_file=ca)
    )
    assert kwargs["ssl_ca_certs"] == ca
    assert kwargs["ssl_cert_reqs"] == ssl.CERT_REQUIRED


def test_uvicorn_dev_http_has_no_tls():
    kwargs = build_uvicorn_kwargs(_cfg(host="127.0.0.1"))
    assert "ssl_certfile" not in kwargs


def test_uvicorn_refuses_plain_http_without_explicit_dev_flag():
    cfg = _cfg(allow_insecure_http=False)
    with pytest.raises(SystemExit):
        build_uvicorn_kwargs(cfg)


def test_from_env_reads_tls_and_dev_flag(tmp_path, monkeypatch):
    cert, key, ca = _cert_files(tmp_path)
    monkeypatch.setenv("ZD_SANDBOX_TOKEN", TOKEN)
    monkeypatch.setenv("ZD_SANDBOX_IMAGE", IMAGE)
    monkeypatch.setenv("ZD_SANDBOX_TLS_CERT", cert)
    monkeypatch.setenv("ZD_SANDBOX_TLS_KEY", key)
    monkeypatch.setenv("ZD_SANDBOX_TLS_CLIENT_CA", ca)
    monkeypatch.setenv("ZD_SANDBOX_ALLOW_INSECURE_HTTP", "false")
    cfg = ManagerConfig.from_env()
    assert cfg.tls_cert_file == cert
    assert cfg.allow_insecure_http is False
