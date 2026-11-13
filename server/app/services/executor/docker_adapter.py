"""Docker SDK 驱动实现（V2-04B 阶段 B）。

Docker SDK（docker 包）在此模块内惰性导入——本模块只有被独立执行服务加载时
才会引入 Docker SDK；FastAPI 业务进程只应依赖 base/driver/service/models 的抽象，
绝不导入本模块（V2-04A 架构：Docker socket 访问能力只存在于独立执行边界）。

安全实现要点：
- containers.create 使用命令向量（无 shell）；
- network_mode="none"、read_only=True、非 root、cap_drop=ALL、
  no-new-privileges、tmpfs 工作目录、无 bind mount；
- 超时：wait(timeout) 读超时 → kill → timed_out=True（绝不伪装成普通退出码）；
- 无论成功/超时/异常，容器一律 remove(force=True) 清理。
"""

from typing import Mapping

from app.services.executor.base import DockerUnavailableError
from app.services.executor.driver import ContainerDriver, ContainerSpec, DriverRunResult


class DockerSdkDriver(ContainerDriver):
    """基于 docker SDK 的真实驱动。仅由独立执行服务进程实例化。"""

    def __init__(self) -> None:
        try:
            import docker  # 惰性导入：业务进程不导入本模块即可不加载 SDK
        except ImportError as exc:  # pragma: no cover - 未安装 SDK 时
            raise DockerUnavailableError("docker SDK 未安装，无法驱动容器执行") from exc
        self._sdk = docker
        self._client = docker.from_env()

    def engine_info(self) -> Mapping[str, str] | None:
        try:
            self._client.ping()
            version = self._client.version()
            return {"version": str(version.get("Version", ""))}
        except Exception:  # noqa: BLE001 - daemon 不在/网络失败等一律视为不可用
            return None

    def image_digest(self, image_ref: str) -> str | None:
        try:
            image = self._client.images.get(image_ref)
        except Exception:  # noqa: BLE001 - ImageNotFound 等一律视为不存在
            return None
        digests = [d for d in image.attrs.get("RepoDigests", []) if "@" in d]
        if not digests:
            return None
        return digests[0].split("@", 1)[1]

    def run(self, spec: ContainerSpec) -> DriverRunResult:
        from requests.exceptions import ReadTimeout  # docker SDK 依赖 requests

        container = None
        timed_out = False
        status_code: int | None = None
        try:
            container = self._client.containers.create(
                image=spec.image_ref,
                command=list(spec.command),
                user=spec.user,
                network_mode=spec.network_mode,
                read_only=spec.read_only,
                mem_limit=spec.mem_limit,
                nano_cpus=int(spec.cpus * 1_000_000_000),
                pids_limit=spec.pids_limit,
                cap_drop=list(spec.cap_drop),
                security_opt=list(spec.security_opt),
                tmpfs=dict(spec.tmpfs),
                working_dir=spec.workdir,
                environment={"PYTHONUNBUFFERED": "1"},
                stdin_open=False,
                tty=False,
                detach=True,
            )
            container.start()
            try:
                wait_result = container.wait(timeout=spec.timeout_seconds)
                status_code = int(wait_result.get("StatusCode", -1))
            except ReadTimeout:
                timed_out = True
                try:
                    container.kill()
                except Exception:  # noqa: BLE001 - 已死的容器无需 kill
                    pass
                wait_result = container.wait(timeout=10)
                status_code = int(wait_result.get("StatusCode", -1))
            out_b, err_b = container.logs(stdout=True, stderr=True, demux=True)
            return DriverRunResult(
                exit_code=status_code,
                stdout=out_b or b"",
                stderr=err_b or b"",
                timed_out=timed_out,
                container_id=container.id,
            )
        finally:
            if container is not None:
                try:
                    container.remove(force=True)
                except Exception:  # noqa: BLE001 - 清理失败由调用方通过日志观察
                    pass
