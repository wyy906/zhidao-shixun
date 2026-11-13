"""AI 错误诊断：解析、脱敏、超时与降级"""
import json
import logging

import httpx
import pytest

from app.engines.diagnosis import diagnoser as diagnoser_module
from app.engines.diagnosis.diagnoser import ErrorDiagnoser, redact_secrets


def _diagnoser() -> ErrorDiagnoser:
    d = ErrorDiagnoser(timeout=3.0)
    d.base_url = "https://example.invalid/v1"
    d.api_key = "unit-test-key-not-real"
    d.model = "test-model"
    return d


class FakeResponse:
    def __init__(self, payload=None, status_code=200, content=None):
        self._payload = payload if payload is not None else {}
        self.status_code = status_code
        self._content = content

    def raise_for_status(self):
        if self.status_code >= 400:
            request = httpx.Request("POST", "https://example.invalid/v1/chat/completions")
            response = httpx.Response(self.status_code, request=request)
            raise httpx.HTTPStatusError("boom", request=request, response=response)

    def json(self):
        return self._payload


class FakeClient:
    response = None
    last_request = None

    def __init__(self, *args, **kwargs):
        pass

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False

    def post(self, url, json=None, headers=None):
        FakeClient.last_request = {"url": url, "json": json, "headers": headers}
        if isinstance(FakeClient.response, Exception):
            raise FakeClient.response
        return FakeClient.response


@pytest.fixture(autouse=True)
def _patch_client(monkeypatch):
    monkeypatch.setattr(diagnoser_module.httpx, "Client", FakeClient)
    FakeClient.response = None
    FakeClient.last_request = None


def _content_payload(obj: dict) -> FakeResponse:
    return FakeResponse(
        payload={"choices": [{"message": {"content": json.dumps(obj, ensure_ascii=False)}}]}
    )


def test_unavailable_without_config_returns_none():
    d = ErrorDiagnoser()
    d.base_url = ""
    d.api_key = ""
    d.model = ""
    assert d.diagnose(error_text="x") is None


def test_success_parses_response_and_redacts_secrets():
    FakeClient.response = _content_payload({
        "error_type": "语法错误",
        "suggestion": "检查第 3 行缩进",
        "possible_causes": ["缩进不正确", "缺少冒号"],
    })
    d = _diagnoser()
    result = d.diagnose(
        experiment_title="实验一",
        step_title="写代码",
        error_text="报错：key=nvapi-abcdefgh12345678，token sk-abcdefghijklmnop",
        context={"snippet": "nvapi-abcdefgh12345678"},
    )
    assert result is not None
    assert result.error_type == "语法错误"
    assert result.suggestion == "检查第 3 行缩进"
    assert result.possible_causes == ["缩进不正确", "缺少冒号"]

    sent = json.dumps(FakeClient.last_request["json"], ensure_ascii=False)
    assert "nvapi-abcdefgh12345678" not in sent
    assert "sk-abcdefghijklmnop" not in sent
    assert "[REDACTED]" in sent
    assert FakeClient.last_request["headers"]["Authorization"] == "Bearer unit-test-key-not-real"


def test_timeout_returns_none():
    FakeClient.response = httpx.TimeoutException("timeout")
    assert _diagnoser().diagnose(error_text="x") is None


def test_network_error_returns_none():
    FakeClient.response = httpx.ConnectError("refused")
    assert _diagnoser().diagnose(error_text="x") is None


def test_http_error_returns_none_and_logs_without_key(caplog):
    FakeClient.response = FakeResponse(status_code=500)
    with caplog.at_level(logging.WARNING):
        assert _diagnoser().diagnose(error_text="x") is None
    assert "unit-test-key-not-real" not in caplog.text


def test_malformed_json_returns_none():
    FakeClient.response = FakeResponse(
        payload={"choices": [{"message": {"content": "not-json"}}]}
    )
    assert _diagnoser().diagnose(error_text="x") is None


def test_missing_suggestion_returns_none():
    FakeClient.response = _content_payload({"error_type": "未知", "suggestion": ""})
    assert _diagnoser().diagnose(error_text="x") is None


def test_causes_are_limited():
    FakeClient.response = _content_payload({
        "error_type": "错误",
        "suggestion": "建议",
        "possible_causes": [f"原因{i}" for i in range(10)],
    })
    result = _diagnoser().diagnose(error_text="x")
    assert result is not None
    assert len(result.possible_causes) == 5


def test_redact_secrets_patterns():
    text = "nvapi-abcdefgh12345678 sk-abcdefghijklmnop AKIAABCDEFGHIJKLMNOP api_key=secret-value-123"
    cleaned = redact_secrets(text)
    for secret in ("nvapi-abcdefgh12345678", "sk-abcdefghijklmnop",
                   "AKIAABCDEFGHIJKLMNOP", "secret-value-123"):
        assert secret not in cleaned
    assert cleaned.count("[REDACTED]") >= 4
