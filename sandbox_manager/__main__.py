"""启动入口：python -m sandbox_manager

必须显式配置管理令牌、固定镜像 digest 与 TLS 证书，否则拒绝启动。
生产环境不会以明文 HTTP 启动，也不会在校验失败后自动降级。
"""
from __future__ import annotations

import logging
import ssl

import uvicorn

from .config import ManagerConfig
from .server import create_app

logger = logging.getLogger(__name__)


def build_uvicorn_kwargs(cfg: ManagerConfig) -> dict:
    """根据已校验的配置构造 uvicorn 启动参数

    规则（由 ManagerConfig.validate 保证，这里再次显式判断，不做降级）：
      - 配置了证书 → 强制 HTTPS；配置了客户端 CA → 强制双向 TLS；
      - 未配置证书 → 只允许 allow_insecure_http + 回环地址的明文 HTTP；
      - 其余情况直接拒绝启动。
    """
    kwargs: dict = {
        "host": cfg.host,
        "port": cfg.port,
        "log_level": "info",
    }
    if cfg.tls_cert_file:
        kwargs["ssl_certfile"] = cfg.tls_cert_file
        kwargs["ssl_keyfile"] = cfg.tls_key_file
        if cfg.tls_client_ca_file:
            kwargs["ssl_ca_certs"] = cfg.tls_client_ca_file
            kwargs["ssl_cert_reqs"] = ssl.CERT_REQUIRED
        return kwargs

    if not cfg.allow_insecure_http:
        # 兜底：即使有人绕过 validate，也绝不以明文 HTTP 启动
        raise SystemExit("拒绝以明文 HTTP 启动：请配置 TLS 证书或显式允许本机开发模式")

    logger.warning("开发模式：沙箱管理接口以明文 HTTP 监听 %s（仅限本机回环）", cfg.host)
    return kwargs


def main() -> None:
    cfg = ManagerConfig.from_env()  # 配置不合法会在此处直接失败
    app = create_app(config=cfg)
    uvicorn.run(app, **build_uvicorn_kwargs(cfg))


if __name__ == "__main__":
    main()
