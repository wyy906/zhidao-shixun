"""沙箱管理接口客户端（业务后端 → 独立 Linux 执行节点）

业务后端**不执行**学生代码，也不持有 Docker 权限 / Docker Socket：
本模块只通过 HTTPS（推荐内网 TLS 或双向 TLS）+ 管理令牌，把经过校验的任务
转发给独立沙箱管理器，并轮询任务结果。

任何异常（未配置、连接失败、认证失败、响应异常）都统一抛出 SandboxUnavailable，
由接口层安全失败（503），**绝不回退到本机执行**。
"""
from __future__ import annotations

import logging

import httpx

from app.core.config import settings

logger = logging.getLogger(__name__)

# 面向学生/前端的统一安全提示：不暴露服务器路径、Docker 细节或密钥
SAFE_UNAVAILABLE_MESSAGE = "代码执行环境暂不可用，请稍后重试。"


class SandboxUnavailable(RuntimeError):
    """沙箱管理器不可用或配置不完整（内部异常，不直接回显给学生）"""


class SandboxClient:
    """调用独立执行节点的沙箱管理器"""

    def __init__(
        self,
        base_url: str | None = None,
        token: str | None = None,
        ca_file: str | None = None,
        client_cert: str | None = None,
        client_key: str | None = None,
        request_timeout: float | None = None,
    ):
        self._base_url = (base_url if base_url is not None else settings.sandbox_manager_url).rstrip("/")
        self._token = token if token is not None else settings.sandbox_manager_token
        self._ca_file = ca_file if ca_file is not None else settings.sandbox_manager_ca_file
        self._client_cert = client_cert if client_cert is not None else settings.sandbox_manager_client_cert
        self._client_key = client_key if client_key is not None else settings.sandbox_manager_client_key
        self._timeout = (
            request_timeout if request_timeout is not None else settings.sandbox_request_timeout_seconds
        )

    # ------------------------------------------------------------------
    # 内部
    # ------------------------------------------------------------------
    def _ensure_configured(self) -> None:
        if not self._base_url or not self._token:
            raise SandboxUnavailable("sandbox manager url/token not configured")

    def _http(self) -> httpx.Client:
        # 不允许关闭证书校验：内网自签证书必须通过 CA 文件显式信任
        verify: str | bool = self._ca_file or True
        cert = None
        if self._client_cert and self._client_key:
            cert = (self._client_cert, self._client_key)
        return httpx.Client(
            base_url=self._base_url,
            verify=verify,
            cert=cert,
            timeout=self._timeout,
        )

    def _request(self, method: str, path: str, payload: dict | None = None) -> dict:
        self._ensure_configured()
        headers = {"X-Sandbox-Token": self._token}
        try:
            with self._http() as client:
                resp = client.request(method, path, json=payload, headers=headers)
        except httpx.HTTPError as exc:
            logger.warning("沙箱管理器请求失败（%s %s）: %s", method, path, exc)
            raise SandboxUnavailable("sandbox manager unreachable") from exc

        if resp.status_code >= 400:
            # 只记录状态码，不回显管理器响应体，避免把内部细节带给前端
            logger.warning("沙箱管理器返回异常状态（%s %s）: %s", method, path, resp.status_code)
            raise SandboxUnavailable(f"sandbox manager returned {resp.status_code}")

        try:
            data = resp.json()
        except ValueError as exc:
            raise SandboxUnavailable("sandbox manager returned invalid json") from exc
        if not isinstance(data, dict):
            raise SandboxUnavailable("sandbox manager returned unexpected payload")
        return data

    # ------------------------------------------------------------------
    # 对外的管理接口
    # ------------------------------------------------------------------
    def health(self) -> dict:
        return self._request("GET", "/health")

    def submit(self, code: str, timeout: int) -> dict:
        return self._request("POST", "/v1/jobs", {"code": code, "timeout": timeout})

    def get_job(self, job_id: str) -> dict:
        return self._request("GET", f"/v1/jobs/{job_id}")

    def cancel(self, job_id: str) -> dict:
        return self._request("DELETE", f"/v1/jobs/{job_id}")


_client: SandboxClient | None = None


def get_sandbox_client() -> SandboxClient:
    """FastAPI 依赖：进程内复用一个客户端（测试中可通过 dependency_overrides 替换）"""
    global _client
    if _client is None:
        _client = SandboxClient()
    return _client
