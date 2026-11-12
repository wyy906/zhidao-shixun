"""沙箱管理客户端传输安全测试（不访问网络）

覆盖：
  - 非回环 HTTP 被拒绝；回环 HTTP 仅在显式开发开关下允许；
  - 客户端证书 / 私钥必须成对；
  - 完整 mTLS 配置正确传递给 httpx；
  - 畸形响应按安全失败处理；
  - 启动配置校验。
"""
import asyncio

import httpx
import pytest

from app.services import sandbox_client
from app.services.sandbox_client import (
    SandboxBadResponse,
    SandboxBusy,
    SandboxClient,
    SandboxUnavailable,
    ensure_sandbox_configuration,
)

BASE_HTTPS = "https://sandbox.internal:8443"


def _client(**overrides) -> SandboxClient:
    data = {
        "base_url": BASE_HTTPS,
        "token": "test-token",
        "ca_file": "",
        "client_cert": "",
        "client_key": "",
        "request_timeout": 5.0,
        "allow_insecure_http": False,
    }
    data.update(overrides)
    return SandboxClient(**data)


def test_https_configuration_accepted():
    client = _client()
    client.validate_config()
    kwargs = client._client_kwargs()
    assert kwargs["verify"] is True  # 保留证书校验，绝不为 False
    assert kwargs["cert"] is None


def test_non_loopback_http_rejected():
    client = _client(base_url="http://10.0.0.5:8443")
    with pytest.raises(SandboxUnavailable, match="insecure"):
        client.validate_config()


def test_loopback_http_requires_explicit_dev_flag():
    client = _client(base_url="http://127.0.0.1:8443")
    with pytest.raises(SandboxUnavailable):
        client.validate_config()

    dev = _client(base_url="http://127.0.0.1:8443", allow_insecure_http=True)
    dev.validate_config()

    localhost = _client(base_url="http://localhost:8443", allow_insecure_http=True)
    localhost.validate_config()


def test_insecure_flag_does_not_allow_remote_hosts():
    client = _client(base_url="http://192.168.1.9:8443", allow_insecure_http=True)
    with pytest.raises(SandboxUnavailable):
        client.validate_config()


def test_half_mtls_configuration_rejected(tmp_path):
    cert = tmp_path / "client.crt"
    cert.write_text("dummy", encoding="utf-8")
    with pytest.raises(SandboxUnavailable, match="together"):
        _client(client_cert=str(cert)).validate_config()
    with pytest.raises(SandboxUnavailable, match="together"):
        _client(client_key=str(cert)).validate_config()


def test_full_mtls_configuration_passed_to_http_client(tmp_path):
    ca = tmp_path / "ca.crt"
    cert = tmp_path / "client.crt"
    key = tmp_path / "client.key"
    for path in (ca, cert, key):
        path.write_text("dummy", encoding="utf-8")

    client = _client(ca_file=str(ca), client_cert=str(cert), client_key=str(key))
    client.validate_config()
    kwargs = client._client_kwargs()
    assert kwargs["verify"] == str(ca)
    assert kwargs["cert"] == (str(cert), str(key))


def test_missing_certificate_file_rejected(tmp_path):
    client = _client(ca_file=str(tmp_path / "missing-ca.crt"))
    with pytest.raises(SandboxUnavailable, match="not found"):
        client.validate_config()


def test_unconfigured_client_is_allowed():
    client = SandboxClient(base_url="", token="")
    client.validate_config()  # 未启用执行节点时不阻断启动，接口返回 503


def test_invalid_json_response_is_bad_response():
    request = httpx.Request("GET", BASE_HTTPS + "/v1/jobs/x")
    resp = httpx.Response(200, content=b"<html>not json</html>", request=request)
    with pytest.raises(SandboxBadResponse):
        SandboxClient._parse_response(resp, "GET", "/v1/jobs/x")


def test_non_object_json_is_bad_response():
    request = httpx.Request("GET", BASE_HTTPS + "/v1/jobs/x")
    resp = httpx.Response(200, json=["not", "an", "object"], request=request)
    with pytest.raises(SandboxBadResponse):
        SandboxClient._parse_response(resp, "GET", "/v1/jobs/x")


def test_error_status_does_not_echo_body():
    request = httpx.Request("GET", BASE_HTTPS + "/v1/jobs/x")
    resp = httpx.Response(
        500, content=b'{"error": "/srv/zd/secrets"}', request=request
    )
    with pytest.raises(SandboxUnavailable) as exc:
        SandboxClient._parse_response(resp, "GET", "/v1/jobs/x")
    assert "/srv/zd" not in str(exc.value)


def test_queue_full_status_maps_to_busy():
    request = httpx.Request("POST", BASE_HTTPS + "/v1/jobs")
    resp = httpx.Response(
        429,
        json={"detail": {"status": "busy", "error": "queue_full"}},
        request=request,
    )
    with pytest.raises(SandboxBusy):
        SandboxClient._parse_response(resp, "POST", "/v1/jobs")


def test_async_client_pool_is_closed_idempotently():
    transport = httpx.MockTransport(lambda request: httpx.Response(200, json={}))
    client = _client(transport=transport)

    async def flow():
        client._get_async_client()
        assert client._async_client is not None
        await client.aclose()
        assert client._async_client is None
        await client.aclose()  # 重复关闭不报错

    asyncio.run(flow())


def test_app_lifespan_closes_sandbox_pool(monkeypatch):
    import app.main as main_module

    transport = httpx.MockTransport(lambda request: httpx.Response(200, json={}))
    client = _client(transport=transport)
    monkeypatch.setattr(sandbox_client, "_client", client)

    class _DB:
        def close(self):
            pass

    monkeypatch.setattr(main_module, "initialize_database", lambda: None)
    monkeypatch.setattr(main_module, "_ensure_admin", lambda: None)
    monkeypatch.setattr(main_module, "_fail_interrupted_tasks", lambda db: None)
    monkeypatch.setattr(main_module, "SessionLocal", lambda: _DB())
    monkeypatch.setattr(main_module, "ensure_sandbox_configuration", lambda: None)

    async def scenario():
        async with main_module.lifespan(main_module.app):
            client._get_async_client()
            assert client._async_client is not None
        assert client._async_client is None

    asyncio.run(scenario())


def test_startup_validation_rejects_insecure_manager(monkeypatch):
    bad = _client(base_url="http://10.0.0.5:8443")
    monkeypatch.setattr(sandbox_client, "_client", bad)
    with pytest.raises(SandboxUnavailable):
        ensure_sandbox_configuration()


def test_startup_validation_accepts_secure_manager(monkeypatch):
    good = _client()
    monkeypatch.setattr(sandbox_client, "_client", good)
    ensure_sandbox_configuration()


def test_async_submit_get_cancel_flow():
    seen: list[tuple[str, str]] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append((request.method, request.url.path))
        assert request.headers["X-Sandbox-Token"] == "test-token"
        if request.method == "POST":
            return httpx.Response(202, json={"job_id": "j1", "status": "queued"})
        if request.method == "DELETE":
            return httpx.Response(200, json={"job_id": "j1", "status": "cancelled"})
        return httpx.Response(200, json={"job_id": "j1", "status": "succeeded"})

    client = _client(transport=httpx.MockTransport(handler))

    async def flow():
        submitted = await client.asubmit("print(1)", 1)
        job = await client.aget_job("j1")
        cancelled = await client.acancel("j1")
        await client._get_async_client().aclose()
        return submitted, job, cancelled

    submitted, job, cancelled = asyncio.run(flow())
    assert submitted["job_id"] == "j1"
    assert job["status"] == "succeeded"
    assert cancelled["status"] == "cancelled"
    assert seen == [
        ("POST", "/v1/jobs"),
        ("GET", "/v1/jobs/j1"),
        ("DELETE", "/v1/jobs/j1"),
    ]


def test_async_transport_error_is_unavailable():
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("boom", request=request)

    client = _client(transport=httpx.MockTransport(handler))

    async def flow():
        await client.asubmit("print(1)", 1)

    with pytest.raises(SandboxUnavailable):
        asyncio.run(flow())
