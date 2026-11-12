"""沙箱管理器配置（全部由管理员通过环境变量设定，学生无法影响）"""
from __future__ import annotations

import os
import re
import socket
from dataclasses import dataclass

_DIGEST_REF_RE = re.compile(r"@sha256:[0-9a-f]{64}$")
_IMAGE_ID_RE = re.compile(r"^sha256:[0-9a-f]{64}$")
_LOOPBACK_HOSTS = {"127.0.0.1", "::1", "localhost"}


def is_loopback_host(host: str) -> bool:
    return (host or "").strip().lower() in _LOOPBACK_HOSTS


def _require_readable_file(path: str, label: str) -> None:
    if not os.path.isfile(path):
        raise ValueError(f"{label}文件不存在: {path}")
    if not os.access(path, os.R_OK):
        raise ValueError(f"{label}文件不可读: {path}")


def is_pinned_reference(image: str) -> bool:
    """镜像引用必须固定到 digest：repo@sha256:... 或本地 sha256:<image-id>"""
    return bool(_DIGEST_REF_RE.search(image) or _IMAGE_ID_RE.match(image))


def is_registry_digest(image: str) -> bool:
    return bool(_DIGEST_REF_RE.search(image))


@dataclass(frozen=True)
class ManagerConfig:
    token: str
    image: str
    host: str = "127.0.0.1"
    port: int = 8443
    # gVisor 等增强运行时（如 runsc）；配置后启动时必须真实存在，否则拒绝执行
    runtime: str = ""
    seccomp_profile: str = ""
    apparmor_profile: str = ""
    # 管理器实例标识：用于给容器打标签，重启清理时只删除本实例遗留的容器。
    # 未配置时使用主机名；多实例部署必须显式设置且互不相同。
    instance_id: str = socket.gethostname()
    # 空表示使用默认 unix:///var/run/docker.sock
    docker_host: str = ""
    # 内网 TLS / 双向 TLS（生产必须；不能只依赖“IP 在局域网内”）
    tls_cert_file: str = ""
    tls_key_file: str = ""
    tls_client_ca_file: str = ""
    # 仅允许本机开发/测试使用明文 HTTP，且必须同时监听回环地址。
    # 生产环境保持 False：缺少 TLS 证书或证书不可读时拒绝启动，不会自动降级。
    allow_insecure_http: bool = False

    cpu_cores: float = 0.5
    memory_mb: int = 128
    timeout_seconds: int = 10
    pids_limit: int = 32
    disk_mb: int = 16
    output_bytes: int = 65536
    input_bytes: int = 65536
    max_concurrent: int = 2

    def validate(self) -> None:
        if not self.token:
            raise ValueError("ZD_SANDBOX_TOKEN 必须设置（管理接口认证）")
        if not self.image:
            raise ValueError("ZD_SANDBOX_IMAGE 必须设置")
        if not (self.instance_id or "").strip():
            raise ValueError("实例标识不能为空（ZD_SANDBOX_INSTANCE_ID 或主机名）")
        if len(self.instance_id) > 128:
            raise ValueError("实例标识过长（上限 128 字符）")
        if not is_pinned_reference(self.image):
            raise ValueError(
                "ZD_SANDBOX_IMAGE 必须固定到 digest（repo@sha256:... 或 sha256:<image-id>），"
                "不允许使用可漂移的 tag"
            )
        if self.cpu_cores <= 0 or self.memory_mb <= 0 or self.timeout_seconds <= 0:
            raise ValueError("CPU / 内存 / 超时配置必须为正数")
        if self.pids_limit <= 0 or self.disk_mb <= 0:
            raise ValueError("进程数 / 磁盘配置必须为正数")
        if self.output_bytes <= 0 or self.input_bytes <= 0:
            raise ValueError("输出 / 输入上限必须为正数")
        if self.max_concurrent <= 0:
            raise ValueError("最大并发必须为正数")

        # ===== 传输安全：生产必须 HTTPS，禁止静默降级 =====
        cert, key, ca = self.tls_cert_file, self.tls_key_file, self.tls_client_ca_file
        if bool(cert) != bool(key):
            raise ValueError("TLS 证书与私钥必须同时配置（不允许只配置其中一项）")
        if ca and not (cert and key):
            raise ValueError("启用双向 TLS 必须同时配置服务端证书与私钥")
        if cert:
            _require_readable_file(cert, "TLS 证书")
            _require_readable_file(key, "TLS 私钥")
        if ca:
            _require_readable_file(ca, "客户端 CA ")

        if self.allow_insecure_http:
            if not is_loopback_host(self.host):
                raise ValueError(
                    "明文 HTTP 仅允许监听本机回环地址（127.0.0.1 / ::1 / localhost），"
                    f"当前配置: {self.host}"
                )
        elif not cert:
            raise ValueError(
                "生产环境必须启用 HTTPS（配置 ZD_SANDBOX_TLS_CERT / ZD_SANDBOX_TLS_KEY）；"
                "本机开发如需明文 HTTP，请显式设置 ZD_SANDBOX_ALLOW_INSECURE_HTTP=true "
                "并只监听回环地址"
            )

    @classmethod
    def from_env(cls) -> "ManagerConfig":
        def _int(name: str, default: int) -> int:
            return int(os.environ.get(name, default))

        def _float(name: str, default: float) -> float:
            return float(os.environ.get(name, default))

        def _bool(name: str, default: bool = False) -> bool:
            raw = os.environ.get(name)
            if raw is None:
                return default
            return raw.strip().lower() in {"1", "true", "yes", "on"}

        cfg = cls(
            token=os.environ.get("ZD_SANDBOX_TOKEN", ""),
            image=os.environ.get("ZD_SANDBOX_IMAGE", ""),
            host=os.environ.get("ZD_SANDBOX_HOST", "127.0.0.1"),
            port=_int("ZD_SANDBOX_PORT", 8443),
            runtime=os.environ.get("ZD_SANDBOX_RUNTIME", ""),
            seccomp_profile=os.environ.get("ZD_SANDBOX_SECCOMP", ""),
            apparmor_profile=os.environ.get("ZD_SANDBOX_APPARMOR", ""),
            instance_id=(
                os.environ.get("ZD_SANDBOX_INSTANCE_ID") or socket.gethostname()
            ).strip(),
            docker_host=os.environ.get("ZD_SANDBOX_DOCKER_HOST", ""),
            tls_cert_file=os.environ.get("ZD_SANDBOX_TLS_CERT", ""),
            tls_key_file=os.environ.get("ZD_SANDBOX_TLS_KEY", ""),
            tls_client_ca_file=os.environ.get("ZD_SANDBOX_TLS_CLIENT_CA", ""),
            allow_insecure_http=_bool("ZD_SANDBOX_ALLOW_INSECURE_HTTP", False),
            cpu_cores=_float("ZD_SANDBOX_CPU", 0.5),
            memory_mb=_int("ZD_SANDBOX_MEMORY_MB", 128),
            timeout_seconds=_int("ZD_SANDBOX_TIMEOUT", 10),
            pids_limit=_int("ZD_SANDBOX_PIDS", 32),
            disk_mb=_int("ZD_SANDBOX_DISK_MB", 16),
            output_bytes=_int("ZD_SANDBOX_OUTPUT_BYTES", 65536),
            input_bytes=_int("ZD_SANDBOX_INPUT_BYTES", 65536),
            max_concurrent=_int("ZD_SANDBOX_MAX_CONCURRENT", 2),
        )
        cfg.validate()
        return cfg
