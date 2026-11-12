"""全局配置（pydantic-settings 从 .env 读取）"""
import os
from pathlib import Path
from typing import List

from pydantic import model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

# 项目根（backend/ 目录），无论从哪个 CWD 启动都能找到 .env
_PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
_DEFAULT_ENV_FILE = _PROJECT_ROOT / ".env"

# 允许通过 ZD_ENV_FILE 显式指定 env 文件路径（相对路径按当前工作目录解析）。
# 测试会把它指向一个不存在的临时文件，从而彻底不读取 backend/.env。
_ENV_FILE = Path(os.environ.get("ZD_ENV_FILE", str(_DEFAULT_ENV_FILE)))

_DEFAULT_JWT_SECRET = "change-me-in-production"


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=str(_ENV_FILE),
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # 应用
    app_name: str = "智导实训"
    app_env: str = "development"
    debug: bool = True

    # 服务
    host: str = "0.0.0.0"
    port: int = 8000
    cors_origins: List[str] = ["http://localhost:5173"]

    # 数据库
    database_url: str = "sqlite:///./zd_shixun.db"

    # 首次启动引导（数据库为空时创建的唯一管理员账号，不是演示数据）
    admin_username: str = "admin"
    admin_password: str = "demo123"

    # JWT
    jwt_secret_key: str = _DEFAULT_JWT_SECRET
    jwt_algorithm: str = "HS256"
    access_token_expire_minutes: int = 1440

    # 注册控制
    allow_public_register: bool = False  # 默认关闭公开注册，仅管理员可创建账号

    # AI 模型（首期 Stub 模式不使用）
    ai_api_base_url: str = ""
    ai_api_key: str = ""
    ai_vision_model: str = ""

    @model_validator(mode="after")
    def _validate_jwt_secret(self) -> "Settings":
        """生产环境强制使用强 JWT 密钥，避免令牌可被伪造"""
        is_default = (not self.jwt_secret_key) or self.jwt_secret_key == _DEFAULT_JWT_SECRET
        if self.app_env != "development":
            if is_default or len(self.jwt_secret_key) < 16:
                raise ValueError(
                    "生产环境必须设置强 JWT_SECRET_KEY（至少 16 字符，不能为默认值）。\n"
                    "请在 .env 中设置：JWT_SECRET_KEY=<随机字符串>\n"
                    "可用：python -c \"import secrets; print(secrets.token_urlsafe(32))\""
                )
        elif is_default:
            # 开发环境：明确警告，但不阻断启动
            import warnings
            warnings.warn(
                "JWT_SECRET_KEY 仍为默认值，仅可用于本地开发。"
                "生产部署前必须修改。",
                stacklevel=2,
            )
        return self


settings = Settings()

