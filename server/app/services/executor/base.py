"""代码执行器接口（V2-02 占位，V2-04 实现 Docker 隔离执行）。

D-1 决策（AI_COLLABORATION.md §7/§10）：学生代码是不可信输入，只能进入受限容器执行。
安全基线：默认禁网、非 root、只读根文件系统、临时工作目录、CPU/内存/PID/时间/输出限制、
不挂载宿主机敏感目录、不把 Docker socket 暴露给业务进程。除 image / 工作目录外，
其余基线不允许通过配置关闭。

本阶段不实现任何宿主机直接执行路径；Docker 不可用或未实现时，调用方得到显式错误，
禁止静默回退到宿主机执行。
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass

MAX_CODE_BYTES = 65536
MAX_TIMEOUT_SECONDS = 20
MAX_OUTPUT_BYTES = 65536


class ExecutorError(Exception):
    """执行器错误基类。"""


class DockerUnavailableError(ExecutorError):
    """Docker 不可用或执行器尚未实现。调用方必须显式处理，不得回退宿主机执行。"""


class UnsafeExecutionRequest(ExecutorError):
    """执行请求或安全配置违反基线。"""


@dataclass(frozen=True)
class ExecutionRequest:
    """一次不可信代码执行请求。"""

    language: str
    code: str
    timeout_seconds: int = 10

    def __post_init__(self) -> None:
        if self.language != "python":
            raise UnsafeExecutionRequest(f"暂不支持语言：{self.language}（当前仅 python）")
        if not self.code.strip():
            raise UnsafeExecutionRequest("代码为空")
        if len(self.code.encode("utf-8")) > MAX_CODE_BYTES:
            raise UnsafeExecutionRequest(f"代码超过 {MAX_CODE_BYTES} 字节上限")
        if not (0 < self.timeout_seconds <= MAX_TIMEOUT_SECONDS):
            raise UnsafeExecutionRequest(f"timeout_seconds 必须在 (0, {MAX_TIMEOUT_SECONDS}] 内")


@dataclass(frozen=True)
class ExecutionResult:
    """一次执行的结果。"""

    exit_code: int | None
    stdout: str
    stderr: str
    timed_out: bool
    truncated: bool


@dataclass(frozen=True)
class DockerSandboxConfig:
    """Docker 沙箱安全基线（D-1）。除 image / workdir 外均不可关闭。"""

    image: str = "python:3.12-slim"
    workdir: str = "/sandbox"
    network_disabled: bool = True
    read_only_rootfs: bool = True
    non_root_user: str = "65534:65534"
    mem_limit: str = "256m"
    cpus: float = 1.0
    pids_limit: int = 64
    max_output_bytes: int = MAX_OUTPUT_BYTES
    timeout_seconds: int = 10
    no_docker_socket: bool = True

    def __post_init__(self) -> None:
        if not self.network_disabled:
            raise ValueError("Docker 安全基线不可关闭：必须禁网（D-1）")
        if not self.read_only_rootfs:
            raise ValueError("Docker 安全基线不可关闭：根文件系统必须只读（D-1）")
        if not self.no_docker_socket:
            raise ValueError("Docker 安全基线不可关闭：禁止挂载 Docker socket（D-1）")
        if self.non_root_user in ("", "root", "0:0"):
            raise ValueError("Docker 安全基线不可关闭：必须以非 root 用户运行（D-1）")
        if not (0 < self.timeout_seconds <= MAX_TIMEOUT_SECONDS):
            raise ValueError(f"timeout_seconds 必须在 (0, {MAX_TIMEOUT_SECONDS}] 内")
        if self.max_output_bytes > MAX_OUTPUT_BYTES:
            raise ValueError(f"max_output_bytes 不得超过 {MAX_OUTPUT_BYTES}")


class CodeExecutor(ABC):
    """执行器抽象。实现必须保证不可信代码不接触宿主机主进程。"""

    @abstractmethod
    def run(self, request: ExecutionRequest) -> ExecutionResult:
        """执行代码并返回结果。实现方负责超时、输出截断与资源限制。"""


class DockerCodeExecutor(CodeExecutor):
    """V2-04 交付容器执行。当前阶段显式拒绝一切执行请求。"""

    def __init__(self, config: DockerSandboxConfig | None = None) -> None:
        self.config = config or DockerSandboxConfig()

    def run(self, request: ExecutionRequest) -> ExecutionResult:
        raise DockerUnavailableError(
            "Docker 执行器尚未实现（V2-04 交付）。按 D-1 决策，不提供宿主机回退执行。"
        )
