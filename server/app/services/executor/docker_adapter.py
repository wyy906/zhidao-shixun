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
        except ImportError:
            # docker SDK 未安装（如开发机无 Docker Desktop）：允许构造本驱动，
            # engine_info() 返回 None 如实报告"引擎不可用"，执行服务因此可以启动
            # 并在 /healthz 中诚实报告；执行仍 fail-closed（绝不宿主机回退）。
            self._sdk = None
            self._client = None
            return
        self._sdk = docker
        self._client = docker.from_env()

    def engine_info(self) -> Mapping[str, str] | None:
        if self._client is None:
            return None
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
        if self._client is None:
            raise DockerUnavailableError(
                "docker SDK 未安装，无法驱动容器执行（fail-closed，无宿主机回退）"
            )
        # 阶段 C 实测：docker-py wait(timeout=) 超时抛 ConnectionError（包裹
        # urllib3 ReadTimeoutError），而非 requests.ReadTimeout——两者都要接住。
        from requests.exceptions import ConnectionError as RequestsConnectionError
        from requests.exceptions import ReadTimeout  # noqa: F401 docker SDK 依赖 requests

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
            except (RequestsConnectionError, ReadTimeout):
                timed_out = True
                # 阶段 C 实测：wait 读超时后 Npipe 连接池中的连接处于脏状态
                # （响应未读完），复用会导致后续 kill/wait 再次 ReadTimeout——
                # 先关闭连接池（后续请求自动重建连接）再 kill。
                try:
                    self._client.api.close()
                except Exception:  # noqa: BLE001
                    pass
                try:
                    container.kill()
                except Exception:  # noqa: BLE001 - 已死的容器无需 kill
                    pass
                wait_result = container.wait(timeout=10)
                status_code = int(wait_result.get("StatusCode", -1))
            # 阶段 C 实测最终结论（R-4B-2，三次实测迭代）：
            # 1) container.logs() 无 demux 参数（TypeError）；
            # 2) attach 方案（无论 wait 后阻塞读还是 attach-before-wait 流读）
            #    对容器生命周期时序敏感——实测出现 completed/exit=0 但 stdout
            #    全空的间歇性输出丢失，不可接受；
            # 3) 最终方案：wait 完成后用 logs() 分两次按流过滤——logs 端点对
            #    停止容器回放缓存后必然 EOF，无竞态、无挂起。
            out_b = container.logs(stdout=True, stderr=False)
            err_b = container.logs(stdout=False, stderr=True)
            return DriverRunResult(
                exit_code=status_code,
                stdout=out_b if isinstance(out_b, bytes) else b"".join(out_b),
                stderr=err_b if isinstance(err_b, bytes) else b"".join(err_b),
                timed_out=timed_out,
                container_id=container.id,
            )
        finally:
            if container is not None:
                try:
                    container.remove(force=True)
                except Exception:  # noqa: BLE001 - 清理失败由调用方通过日志观察
                    pass
