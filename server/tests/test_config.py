"""配置安全测试：不读取真实 .env、不存在密钥类字段。"""

from app.core.config import Settings


def test_settings_reads_env_with_prefix(monkeypatch) -> None:
    monkeypatch.setenv("ZD_PORT", "8123")
    monkeypatch.setenv("ZD_APP_ENV", "test")
    settings = Settings(_env_file=None)  # 不读取真实 .env，防止本地配置影响测试
    assert settings.port == 8123
    assert settings.app_env == "test"


def test_settings_has_no_secret_fields() -> None:
    dangerous_names = {"password", "secret", "token", "api_key", "private_key"}
    field_names = {name.lower() for name in Settings.model_fields}
    assert not (field_names & dangerous_names), f"配置中出现密钥类字段：{field_names & dangerous_names}"
