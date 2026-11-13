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

    # ===== 独立执行服务（V2-04B；仅执行服务进程使用，业务进程不加载 Docker SDK）=====
    executor_bind_host: str = "127.0.0.1"
    executor_bind_port: int = 8101
    # 执行服务调用令牌：为空时执行服务拒绝启动（fail-closed）；浏览器永不持有该令牌
    executor_token: str = ""
    # 固定执行镜像（服务端固定生成，用户不可指定）
    executor_image_tag: str = "python:3.12-slim"
    # 批准的镜像 digest：为空（executor_image_lock.json approval_status=pending）时
    # 执行服务拒绝一切执行（fail-closed）
    executor_image_digest: str = ""
    # 执行记录 JSONL 存储路径
    executor_records_path: str = "data/executor_records.jsonl"


@lru_cache
def get_settings() -> Settings:
    return Settings()
