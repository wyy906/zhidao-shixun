"""桌面端配置：只读环境变量，无任何密钥；后端地址是唯一外部依赖。"""

import os
from dataclasses import dataclass


@dataclass(frozen=True)
class DesktopSettings:
    api_base_url: str
    request_timeout_seconds: float


def load_settings() -> DesktopSettings:
    return DesktopSettings(
        api_base_url=os.environ.get("ZD_API_BASE_URL", "http://127.0.0.1:8000"),
        request_timeout_seconds=float(os.environ.get("ZD_REQUEST_TIMEOUT_SECONDS", "3")),
    )
