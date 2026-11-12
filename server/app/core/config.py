"""服务端配置。

- 全部环境变量使用 ZD_ 前缀，示例见根目录 .env.example；
- 不内置任何密钥、账号、密码；密钥类配置只在 .env / 环境变量中出现（V2-07 起）。
"""

from functools import lru_cache
from typing import Literal

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_prefix="ZD_",
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    app_name: str = "智导实训"
    app_env: Literal["development", "production", "test"] = "development"
    debug: bool = True
    host: str = "127.0.0.1"
    port: int = 8000
    log_level: Literal["DEBUG", "INFO", "WARNING", "ERROR"] = "INFO"
    cors_origins: list[str] = ["http://localhost:5173", "http://127.0.0.1:5173"]
    # V2-03 起真正启用数据库；当前仅预留配置位
    database_url: str = "sqlite:///./zhidao.db"


@lru_cache
def get_settings() -> Settings:
    return Settings()
