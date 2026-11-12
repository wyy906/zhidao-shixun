"""与 server 的最小 HTTP 客户端。desktop 只通过 HTTP + 共享契约与服务端交互。"""

import httpx


def get_health(base_url: str, timeout_seconds: float = 3.0) -> dict:
    """请求服务端 /health。失败抛出 httpx 异常，由调用方决定如何呈现。"""
    response = httpx.get(f"{base_url.rstrip('/')}/health", timeout=timeout_seconds)
    response.raise_for_status()
    return response.json()
