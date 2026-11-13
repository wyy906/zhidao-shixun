"""业务后端生产预检脚本的单元测试（不联网、不读真实 .env）"""
from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import pytest

_SCRIPT = Path(__file__).resolve().parents[2] / "scripts" / "backend_preflight.py"
_spec = importlib.util.spec_from_file_location("backend_preflight", _SCRIPT)
preflight = importlib.util.module_from_spec(_spec)
assert _spec.loader is not None
# dataclass 装饰器要求模块已注册到 sys.modules，必须先注册再执行
sys.modules[_spec.name] = preflight
_spec.loader.exec_module(preflight)

STRONG = "x" * 40


def _prod_env(**overrides: str) -> dict[str, str]:
    env = {
        "APP_ENV": "production",
        "DEBUG": "false",
        "JWT_SECRET_KEY": STRONG,
        "ADMIN_PASSWORD": "Str0ng-Admin-Pass",
        "ALLOW_PUBLIC_REGISTER": "false",
        "DATABASE_URL": "postgresql+psycopg://user:pass@db:5432/zd",
        "DB_AUTO_CREATE": "false",
        "CORS_ORIGINS": '["https://zd.example.com"]',
        "CODE_EXECUTION_ENABLED": "false",
        "AI_API_BASE_URL": "",
        "AI_API_KEY": "",
        "AI_VISION_MODEL": "",
    }
    env.update(overrides)
    return env


def _levels(results: list) -> dict[str, int]:
    counts = {"PASS": 0, "FAIL": 0, "WARN": 0}
    for item in results:
        counts[item.level] += 1
    return counts


def test_fully_compliant_production_env_has_no_fail():
    results = preflight.evaluate(_prod_env())
    assert _levels(results)["FAIL"] == 0


def test_development_defaults_are_rejected():
    env = {
        "APP_ENV": "development",
        "DEBUG": "true",
        "JWT_SECRET_KEY": "change-me-in-production-please-use-a-long-random-string",
        "ADMIN_PASSWORD": "demo123",
        "DB_AUTO_CREATE": "true",
        "CORS_ORIGINS": "",
    }
    messages = [item.message for item in preflight.evaluate(env) if item.level == "FAIL"]
    joined = " ".join(messages)
    assert "APP_ENV" in joined
    assert "DEBUG" in joined
    assert "JWT_SECRET_KEY" in joined
    assert "ADMIN_PASSWORD" in joined
    assert "DB_AUTO_CREATE" in joined
    assert "CORS_ORIGINS" in joined


def test_sandbox_enabled_requires_url_and_token():
    env = _prod_env(CODE_EXECUTION_ENABLED="true")
    messages = [item.message for item in preflight.evaluate(env) if item.level == "FAIL"]
    assert any("SANDBOX_MANAGER_URL" in message for message in messages)
    assert any("SANDBOX_MANAGER_TOKEN" in message for message in messages)


def test_sandbox_plain_http_non_loopback_is_rejected():
    env = _prod_env(
        CODE_EXECUTION_ENABLED="true",
        SANDBOX_MANAGER_URL="http://10.0.0.20:8443",
        SANDBOX_MANAGER_TOKEN=STRONG,
    )
    results = preflight.evaluate(env)
    assert any(
        item.level == "FAIL" and "HTTPS" in item.message for item in results
    )


def test_sandbox_loopback_plain_http_requires_explicit_switch(tmp_path):
    env = _prod_env(
        CODE_EXECUTION_ENABLED="true",
        SANDBOX_MANAGER_URL="http://127.0.0.1:8443",
        SANDBOX_MANAGER_TOKEN=STRONG,
        SANDBOX_MANAGER_CA_FILE="",
        SANDBOX_MANAGER_CLIENT_CERT="",
        SANDBOX_MANAGER_CLIENT_KEY="",
    )
    results = preflight.evaluate(env, tmp_path)
    assert any(item.level == "FAIL" for item in results)

    env["SANDBOX_ALLOW_INSECURE_HTTP"] = "true"
    results = preflight.evaluate(env, tmp_path)
    assert not any(item.level == "FAIL" for item in results)
    assert any(item.level == "WARN" for item in results)


def test_wildcard_cors_is_rejected():
    results = preflight.evaluate(_prod_env(CORS_ORIGINS='["*"]'))
    assert any(
        item.level == "FAIL" and "通配符" in item.message for item in results
    )


def test_load_env_ignores_comments_and_strips_quotes(tmp_path):
    env_file = tmp_path / "prod.env"
    env_file.write_text(
        "# comment\n\nAPP_ENV=production\nexport ADMIN_PASSWORD='Sp ace-Pass-123'\n",
        encoding="utf-8",
    )
    env = preflight.load_env(env_file)
    assert env["APP_ENV"] == "production"
    assert env["ADMIN_PASSWORD"] == "Sp ace-Pass-123"


def test_main_returns_exit_code_1_for_missing_file(tmp_path):
    assert preflight.main(["--env-file", str(tmp_path / "missing.env")]) == 1


def test_main_returns_exit_code_2_when_only_warnings(tmp_path, capsys):
    env_file = tmp_path / "prod.env"
    env_file.write_text(
        "\n".join(
            [
                "APP_ENV=production",
                "DEBUG=false",
                f"JWT_SECRET_KEY={STRONG}",
                "ADMIN_PASSWORD=Str0ng-Admin-Pass",
                "ALLOW_PUBLIC_REGISTER=false",
                "DATABASE_URL=sqlite:///./zd.db",
                "DB_AUTO_CREATE=false",
                'CORS_ORIGINS=["https://zd.example.com"]',
                "CODE_EXECUTION_ENABLED=false",
            ]
        )
        + "\n",
        encoding="utf-8",
    )
    assert preflight.main(["--env-file", str(env_file)]) == 2
    output = capsys.readouterr().out
    assert "FAIL=0" in output


@pytest.mark.parametrize("key", ["ADMIN_PASSWORD", "JWT_SECRET_KEY"])
def test_secret_values_never_printed(tmp_path, capsys, key):
    secret = "SuperSecretValue-1234567890-abcdef"
    env_file = tmp_path / "prod.env"
    env_file.write_text(
        "\n".join(
            [
                "APP_ENV=production",
                "DEBUG=false",
                f"JWT_SECRET_KEY={secret}",
                f"ADMIN_PASSWORD={secret}",
                "DATABASE_URL=postgresql+psycopg://u:p@db:5432/zd",
                "DB_AUTO_CREATE=false",
                'CORS_ORIGINS=["https://zd.example.com"]',
                "CODE_EXECUTION_ENABLED=false",
            ]
        )
        + "\n",
        encoding="utf-8",
    )
    preflight.main(["--env-file", str(env_file)])
    output = capsys.readouterr().out
    assert secret not in output
