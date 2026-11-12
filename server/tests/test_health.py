"""健康检查与统一错误响应测试。"""

from fastapi.testclient import TestClient

from app.main import create_app
from zhidao_contracts import CONTRACT_VERSION

client = TestClient(create_app())


def test_health_ok() -> None:
    resp = client.get("/health")
    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] == "ok"
    assert body["api_version"] == "v1"
    assert body["contract_version"] == CONTRACT_VERSION


def test_contract_version_endpoint() -> None:
    resp = client.get("/api/v1/contract/version")
    assert resp.status_code == 200
    body = resp.json()
    assert body["contract_version"] == CONTRACT_VERSION
    assert "ScreenState" in body["models"]
    assert "GuideMessage" in body["models"]


def test_unknown_path_returns_unified_error() -> None:
    resp = client.get("/api/v1/definitely-not-exist")
    assert resp.status_code == 404
    assert set(resp.json()["error"].keys()) == {"code", "message", "details"}


def test_validation_error_returns_unified_error() -> None:
    resp = client.post("/health", json={"unexpected": 1})
    assert resp.status_code == 405
    assert set(resp.json()["error"].keys()) == {"code", "message", "details"}
