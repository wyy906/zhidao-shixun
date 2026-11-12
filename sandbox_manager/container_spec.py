"""执行容器的安全配置（纯函数，可在无 Docker 环境下单元测试）

每个任务一个容器，配置必须满足：
  - 非 root 用户、禁止特权、drop ALL capabilities、no-new-privileges、seccomp
  - 根文件系统只读，只提供本次任务独立的容量受限 tmpfs
  - 网络模式固定 none（禁公网 / 局域网 / 业务服务）
  - CPU / 内存 / 进程数 / 磁盘 / 输出全部限额
  - 不挂载任何宿主机目录或设备，不映射端口
"""
from __future__ import annotations

import base64
from dataclasses import dataclass

# 从环境变量读取代码并执行，避免把代码写进镜像或宿主机目录
BOOTSTRAP_CODE = (
    "import base64,os\n"
    "src=base64.b64decode(os.environ['ZD_CODE_B64'])\n"
    "exec(compile(src,'main.py','exec'),{'__name__':'__main__','__builtins__':__builtins__})"
)

SANDBOX_UID = "65534:65534"  # nobody:nogroup


@dataclass(frozen=True)
class SandboxLimits:
    cpu_cores: float = 0.5
    memory_mb: int = 128
    timeout_seconds: int = 10
    pids_limit: int = 32
    disk_mb: int = 16
    output_bytes: int = 65536
    input_bytes: int = 65536
    max_concurrent: int = 2


def _log_max_size(output_bytes: int) -> str:
    # Docker 日志轮转上限：容器输出超过上限时由 Docker 截断，避免写满宿主机磁盘
    return f"{max(1, output_bytes // 1024)}k"


def _tmpfs_sizes(disk_mb: int) -> tuple[int, int]:
    """把临时磁盘总额拆给 /tmp 与 /workspace（合计不超过 disk_mb）"""
    tmp_mb = min(4, max(1, disk_mb // 4))
    work_mb = max(1, disk_mb - tmp_mb)
    return tmp_mb, work_mb


def build_container_kwargs(
    image: str,
    code: str,
    limits: SandboxLimits,
    runtime: str = "",
    seccomp_profile: str = "",
    apparmor_profile: str = "",
) -> dict:
    """构造 docker-py `containers.create(**kwargs)` 的参数"""
    tmp_mb, work_mb = _tmpfs_sizes(limits.disk_mb)
    tmpfs_opts = "rw,noexec,nosuid,nodev,mode=1777"

    security_opt = ["no-new-privileges:true"]
    if seccomp_profile:
        security_opt.append(f"seccomp={seccomp_profile}")
    if apparmor_profile:
        security_opt.append(f"apparmor={apparmor_profile}")

    kwargs: dict = {
        "image": image,
        "command": ["python", "-I", "-B", "-c", BOOTSTRAP_CODE],
        "environment": {
            # 只传学生自己的代码；绝不传业务端密钥 / 数据库连接串
            "ZD_CODE_B64": base64.b64encode(code.encode("utf-8")).decode("ascii"),
        },
        # ===== 网络：完全禁网，学生不能通过任何参数覆盖 =====
        "network_mode": "none",
        "network_disabled": True,
        # ===== 身份与权限 =====
        "user": SANDBOX_UID,
        "privileged": False,
        "cap_drop": ["ALL"],
        "security_opt": security_opt,
        # ===== 文件系统：只读根 + 独立 tmpfs，无宿主机挂载 =====
        "read_only": True,
        "working_dir": "/workspace",
        "tmpfs": {
            "/tmp": f"{tmpfs_opts},size={tmp_mb}m",
            "/workspace": f"{tmpfs_opts},size={work_mb}m",
        },
        "volumes": {},
        "devices": [],
        # ===== 资源限制 =====
        "mem_limit": f"{limits.memory_mb}m",
        # memswap == mem：禁止使用 swap，避免内存超限后仍可分配
        "memswap_limit": f"{limits.memory_mb}m",
        "nano_cpus": int(limits.cpu_cores * 1_000_000_000),
        "pids_limit": limits.pids_limit,
        "init": True,  # 回收僵尸进程，防止容器内残留子进程
        # ===== 输出限制：json-file 日志轮转，超出即截断 =====
        "log_config": {
            "Type": "json-file",
            "Config": {"max-size": _log_max_size(limits.output_bytes), "max-file": "1"},
        },
        # ===== 生命周期：由管理器显式回收 =====
        "detach": True,
        "auto_remove": False,
        "labels": {"zd.sandbox": "1"},
    }
    if runtime:
        kwargs["runtime"] = runtime
    return kwargs


def verify_container_security(host_config: dict, limits: SandboxLimits, runtime: str = "") -> None:
    """容器创建后回查 Docker 实际生效的 HostConfig

    如果运行时不支持某项限制（例如 PidsLimit / NanoCpus），这里必须发现并拒绝执行，
    绝不能“以为限制已经生效”就放行。失败时抛 RuntimeError，由调用方回收容器。
    """
    problems: list[str] = []

    def _check(name: str, actual, expected) -> None:
        if actual != expected:
            problems.append(f"{name}={actual!r}(期望 {expected!r})")

    _check("NetworkMode", host_config.get("NetworkMode"), "none")
    _check("ReadonlyRootfs", bool(host_config.get("ReadonlyRootfs")), True)
    _check("Privileged", bool(host_config.get("Privileged")), False)

    mem_bytes = limits.memory_mb * 1024 * 1024
    _check("Memory", host_config.get("Memory"), mem_bytes)
    _check("MemorySwap", host_config.get("MemorySwap"), mem_bytes)
    _check("NanoCpus", int(host_config.get("NanoCpus") or 0), int(limits.cpu_cores * 1_000_000_000))
    _check("PidsLimit", int(host_config.get("PidsLimit") or 0), limits.pids_limit)

    cap_drop = [str(c).upper() for c in (host_config.get("CapDrop") or [])]
    if "ALL" not in cap_drop:
        problems.append(f"CapDrop={cap_drop!r}(未包含 ALL)")

    security_opt = host_config.get("SecurityOpt") or []
    if not any("no-new-privileges" in str(opt) for opt in security_opt):
        problems.append("SecurityOpt 未包含 no-new-privileges")

    if host_config.get("Binds"):
        problems.append("存在宿主机目录挂载")
    if host_config.get("Devices"):
        problems.append("存在宿主机设备映射")

    tmpfs = host_config.get("Tmpfs") or {}
    for path in ("/tmp", "/workspace"):
        if path not in tmpfs:
            problems.append(f"缺少受限 tmpfs: {path}")

    if runtime:
        _check("Runtime", host_config.get("Runtime"), runtime)

    if problems:
        raise RuntimeError("容器安全配置未生效: " + "; ".join(problems))
