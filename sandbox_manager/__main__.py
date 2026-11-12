"""启动入口：python -m sandbox_manager

必须显式配置管理令牌与固定镜像 digest，否则拒绝启动。
"""
from __future__ import annotations

import ssl

import uvicorn

from .config import ManagerConfig
from .server import create_app


def main() -> None:
    cfg = ManagerConfig.from_env()  # 配置不合法会在此处直接失败
    app = create_app(config=cfg)
    kwargs = {
        "host": cfg.host,
        "port": cfg.port,
        "log_level": "info",
    }
    if cfg.tls_cert_file and cfg.tls_key_file:
        kwargs["ssl_certfile"] = cfg.tls_cert_file
        kwargs["ssl_keyfile"] = cfg.tls_key_file
        if cfg.tls_client_ca_file:
            kwargs["ssl_ca_certs"] = cfg.tls_client_ca_file
            kwargs["ssl_cert_reqs"] = ssl.CERT_REQUIRED
    uvicorn.run(app, **kwargs)


if __name__ == "__main__":
    main()
