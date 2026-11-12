"""沙箱管理接口客户端（业务后端 → 独立 Linux 执行节点）

业务后端**不执行**学生代码，也不持有 Docker 权限 / Docker Socket：
本模块只通过 HTTPS（推荐内网 TLS 或双向 TLS）+ 管理令牌，把经过校验的任务
转发给独立沙箱管理器，并轮询任务结果。

任何异常（未配置、连接失败、认证失败、响应异常）都统一抛出 SandboxUnavailable，
由接口层安全失败（503），**绝不回退到本机执行**。

传输安全约束：
  - 非回环地址必须使用 https；明文 http 仅允许显式开启
    `SANDBOX_ALLOW_INSECURE_HTTP=true` 且目标为 127.0.0.1 / ::1 / localhost；
  - 客户端证书与私钥必须成对配置，缺失时拒绝启动；
  - 不允许关闭证书校验（verify=False），内网自签证书必须通过 CA 文件显式信任。
"""
from __future__ import annotations

import logging
import os
import threading
from urllib.parse import urlsplit

import httpx

from app.core.config import settings

logger = logging.getLogger(__name__)

# 面向学生/前端的统一安全提示：不暴露服务器路径、Docker 细节或密钥
SAFE_UNAVAILABLE_MESSAGE = "代码执行环境暂不可用，请稍后重试。"

_LOOPBACK_HOSTS = {"127.0.0.1", "::1", "localhost"}


class SandboxUnavailable(RuntimeError):
    """沙箱管理器不可用或配置不完整（内部异常，不直接回显给学生）"""


class SandboxBadResponse(SandboxUnavailable):
    """管理器返回了无法解析 / 不符合约定的数据"""


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
        allow_insecure_http: bool | None = None,
        transport: httpx.BaseTransport | None = None,
    ):
        self._base_url = (base_url if base_url is not None else settings.sandbox_manager_url).rstrip("/")
        self._token = token if token is not None else settings.sandbox_manager_token
        self._ca_file = ca_file if ca_file is not None else settings.sandbox_manager_ca_file
        self._client_cert = client_cert if client_cert is not None else settings.sandbox_manager_client_cert
        self._client_key = client_key if client_key is not None else settings.sandbox_manager_client_key
        self._timeout = (
            request_timeout if request_timeout is not None else settings.sandbox_request_timeout_seconds
        )
        self._allow_insecure_http = (
            allow_insecure_http
            if allow_insecure_http is not None
            else settings.sandbox_allow_insecure_http
        )
        self._transport = transport
        self._async_client: httpx.AsyncClient | None = None
        self._async_lock = threading.Lock()

    # ------------------------------------------------------------------
    # 配置校验
    # ------------------------------------------------------------------
    @property
    def configured(self) -> bool:
        return bool(self._base_url or self._token)

    def validate_config(self) -> None:
        """校验传输安全配置；未配置执行节点时直接返回（接口层会返回 503）"""
        if not self.configured:
            return
        if not self._base_url or not self._token:
            raise SandboxUnavailable("sandbox manager url/token not configured")

        parts = urlsplit(self._base_url)
        if parts.scheme not in {"http", "https"} or not parts.hostname:
            raise SandboxUnavailable("invalid sandbox manager url")
        if parts.scheme == "http":
            host = (parts.hostname or "").lower()
            if not self._allow_insecure_http or host not in _LOOPBACK_HOSTS:
                raise SandboxUnavailable(
                    "insecure sandbox manager url rejected "
                    "(https required unless local loopback dev mode is enabled)"
                )

        if bool(self._client_cert) != bool(self._client_key):
            raise SandboxUnavailable("client cert and key must be configured together")
        for path, label in (
            (self._ca_file, "ca"),
            (self._client_cert, "client cert"),
            (self._client_key, "client key"),
        ):
            if path and not os.path.isfile(path):
                raise SandboxUnavailable(f"sandbox {label} file not found")

    # ------------------------------------------------------------------
    # HTTP 客户端
    # ------------------------------------------------------------------
    def _client_kwargs(self) -> dict:
        # 不允许关闭证书校验：内网自签证书必须通过 CA 文件显式信任
        verify: str | bool = self._ca_file or True
        cert = None
        if self._client_cert and self._client_key:
            cert = (self._client_cert, self._client_key)
        kwargs: dict = {
            "base_url": self._base_url,
            "verify": verify,
            "cert": cert,
            "timeout": httpx.Timeout(
                connect=min(2.0, self._timeout),
                read=self._timeout,
                write=self._timeout,
                pool=self._timeout,
            ),
            "limits": httpx.Limits(max_connections=8, max_keepalive_connections=4),
        }
        if self._transport is not None:
            kwargs["transport"] = self._transport
        return kwargs

    def _get_async_client(self) -> httpx.AsyncClient:
        if self._async_client is None:
            with self._async_lock:
                if self._async_client is None:
                    self._async_client = httpx.AsyncClient(**self._client_kwargs())
        return self._async_client

    def close(self) -> None:
        """关闭复用的异步连接池（进程退出或测试清理时调用）"""
        client, self._async_client = self._async_client, None
        if client is not None:
            try:
                import asyncio

                asyncio.get_running_loop().create_task(client.aclose())
            except RuntimeError:
                # 没有运行中的事件循环时尽力关闭
                pass

    # ------------------------------------------------------------------
    # 响应解析
    # ------------------------------------------------------------------
    @staticmethod
    def _parse_response(resp: httpx.Response, method: str, path: str) -> dict:
        if resp.status_code >= 400:
            # 只记录状态码，不回显管理器响应体，避免把内部细节带给前端
            logger.warning("沙箱管理器返回异常状态（%s %s）: %s", method, path, resp.status_code)
            raise SandboxUnavailable(f"sandbox manager returned {resp.status_code}")
        try:
            data = resp.json()
        except ValueError as exc:
            logger.warning("沙箱管理器返回非 JSON（%s %s）", method, path)
            raise SandboxBadResponse("sandbox manager returned invalid json") from exc
        if not isinstance(data, dict):
            logger.warning("沙箱管理器返回非对象 JSON（%s %s）", method, path)
            raise SandboxBadResponse("sandbox manager returned unexpected payload")
        return data

    # ------------------------------------------------------------------
    # 同步调用（保留给管理/诊断脚本与既有测试）
    # ------------------------------------------------------------------
    def _request(self, method: str, path: str, payload: dict | None = None) -> dict:
        self.validate_config()
        headers = {"X-Sandbox-Token": self._token}
        try:
            with httpx.Client(**self._client_kwargs()) as client:
                resp = client.request(method, path, json=payload, headers=headers)
        except httpx.HTTPError as exc:
            logger.warning("沙箱管理器请求失败（%s %s）: %s", method, path, exc)
            raise SandboxUnavailable("sandbox manager unreachable") from exc
        return self._parse_response(resp, method, path)

    # ------------------------------------------------------------------
    # 异步调用（接口层使用，避免阻塞事件循环）
    # ------------------------------------------------------------------
    async def _arequest(self, method: str, path: str, payload: dict | None = None) -> dict:
        self.validate_config()
        headers = {"X-Sandbox-Token": self._token}
        client = self._get_async_client()
        try:
            resp = await client.request(method, path, json=payload, headers=headers)
        except httpx.HTTPError as exc:
            logger.warning("沙箱管理器请求失败（%s %s）: %s", method, path, exc)
            raise SandboxUnavailable("sandbox manager unreachable") from exc
        return self._parse_response(resp, method, path)

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

    async def ahealth(self) -> dict:
        return await self._arequest("GET", "/health")

    async def asubmit(self, code: str, timeout: int) -> dict:
        return await self._arequest("POST", "/v1/jobs", {"code": code, "timeout": timeout})

    async def aget_job(self, job_id: str) -> dict:
        return await self._arequest("GET", f"/v1/jobs/{job_id}")

    async def acancel(self, job_id: str) -> dict:
        return await self._arequest("DELETE", f"/v1/jobs/{job_id}")


_client: SandboxClient | None = None


def get_sandbox_client() -> SandboxClient:
    """FastAPI 依赖：进程内复用一个客户端（测试中可通过 dependency_overrides 替换）"""
    global _client
    if _client is None:
        _client = SandboxClient()
    return _client


def ensure_sandbox_configuration() -> None:
    """应用启动时校验执行节点配置

    仅在已配置执行节点时检查；配置非法（明文 HTTP 指向非回环地址、
    mTLS 证书不完整、证书文件不存在）时抛出 SandboxUnavailable，
    由 main.lifespan 转为启动失败，绝不以不安全配置运行。
    """
    get_sandbox_client().validate_config()
