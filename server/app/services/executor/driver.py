"""容器驱动抽象层（V2-04B 阶段 B）。

业务/服务核心只依赖 ContainerDriver 抽象与 ContainerSpec 数据；
Docker SDK 具体实现见 docker_adapter.DockerSdkDriver（惰性导入，
保证 FastAPI 业务进程永远不会加载 Docker SDK）。

ContainerSpec 的全部安全参数由服务端固定生成，字段不可由用户请求注入；
不含任何宿主机路径绑定（代码经受控命令向量传入，见 service._build_spec）。
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Mapping


@dataclass(frozen=True)
class ContainerSpec:
    """一次性容器的全部参数（服务端固定生成，不可由用户请求注入）。

    安全不变式：
    - network_mode 必须为 "none"（禁网，D-1）；
    - read_only 必须为 True（只读根文件系统，D-1）；
    - user 必须非 root；
    - cap_drop 必须丢弃全部 capabilities；
    - security_opt 必须启用 no-new-privileges；
    - 不携带任何宿主机 bind mount（禁止用户代码访问宿主机文件系统）。
    """

    image_ref: str
    command: tuple[str, ...]
    user: str
    timeout_seconds: int
    mem_limit: str
    cpus: float
    pids_limit: int
    network_mode: str = "none"
    read_only: bool = True
    cap_drop: tuple[str, ...] = ("ALL",)
    security_opt: tuple[str, ...] = ("no-new-privileges",)
    # 阶段 C 实测：tmpfs 默认 root 所有权，非 root 执行用户无写权限——
    # 必须显式 uid/gid/mode（uid/gid 与 non_root_user 的 65534 对齐）
    tmpfs: Mapping[str, str] = field(default_factory=lambda: {
        "/sandbox": "size=8m,uid=65534,gid=65534,mode=1700",
        "/tmp": "size=8m,uid=65534,gid=65534,mode=1700",
    })
    workdir: str = "/sandbox"

    def __post_init__(self) -> None:
        if self.network_mode != "none":
            raise ValueError("容器安全基线不可关闭：network_mode 必须为 none")
        if not self.read_only:
            raise ValueError("容器安全基线不可关闭：根文件系统必须只读")
        if self.user in ("", "root", "0:0"):
            raise ValueError("容器安全基线不可关闭：必须以非 root 用户运行")
        if "ALL" not in self.cap_drop:
            raise ValueError("容器安全基线不可关闭：必须丢弃全部 capabilities")
        if "no-new-privileges" not in self.security_opt:
            raise ValueError("容器安全基线不可关闭：必须启用 no-new-privileges")
        if self.image_ref in ("", None) or not self.command:
            raise ValueError("image_ref 与 command 必须由服务端提供")


@dataclass(frozen=True)
class DriverRunResult:
    """驱动层一次容器运行结果（原始字节，截断由服务层统一执行）。"""

    exit_code: int | None
    stdout: bytes
    stderr: bytes
    timed_out: bool
    container_id: str | None = None


class ContainerDriver(ABC):
    """容器驱动抽象。实现方负责容器创建/启动/等待/终止/清理的全部细节。"""

    @abstractmethod
    def engine_info(self) -> Mapping[str, str] | None:
        """探测 Docker Engine。不可用时返回 None（服务层据此 fail-closed）。"""

    @abstractmethod
    def image_digest(self, image_ref: str) -> str | None:
        """返回本地已拉取镜像的 RepoDigest（形如 sha256:...）。镜像不存在返回 None。"""

    @abstractmethod
    def run(self, spec: ContainerSpec) -> DriverRunResult:
        """按 spec 运行一次性容器并返回结果。

        实现方契约：无论成功、超时还是异常，容器都必须被移除；
        超时通过 timed_out=True 表达，绝不伪装成普通退出码。
        """
