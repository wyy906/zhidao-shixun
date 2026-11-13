"""Docker 执行器：为每个任务创建一次性容器，施加安全限制并回收

只有在独立 Linux 执行节点上才会真正运行（需要 Docker + 固定镜像）。
任何安全配置无法确认时都抛 SandboxError，由上层拒绝执行——绝不降级。
"""
from __future__ import annotations

import logging
import os
import threading
import time

from .config import ManagerConfig
from .container_spec import SandboxLimits, build_container_kwargs, verify_container_security
from .image_verify import verify_image_reference

logger = logging.getLogger(__name__)


class SandboxError(RuntimeError):
    """沙箱不可用 / 安全配置失败"""

    def __init__(self, code: str, message: str = ""):
        super().__init__(message or code)
        self.code = code


class _BoundedCapture:
    """线程安全的有界输出缓冲

    通过 attach 实时读取容器输出，避免依赖会被轮转覆盖的 json-file 日志文件。
    超出上限的数据仍然被读走（防止容器写入阻塞），但不保留，只记录截断标记。
    """

    def __init__(self, limit: int):
        self.limit = max(0, int(limit))
        self._buf = bytearray()
        self._total = 0
        self._truncated = False
        self._lock = threading.Lock()

    def feed(self, chunk: bytes) -> None:
        if not chunk:
            return
        with self._lock:
            self._total += len(chunk)
            remaining = self.limit - len(self._buf)
            if remaining > 0:
                self._buf.extend(chunk[:remaining])
                if len(chunk) > remaining:
                    self._truncated = True
            else:
                self._truncated = True

    def text(self) -> str:
        with self._lock:
            text = bytes(self._buf).decode("utf-8", "replace")
            truncated = self._truncated
        if truncated:
            return text + "\n…（输出过长，已截断）"
        return text

    @property
    def total(self) -> int:
        with self._lock:
            return self._total


class DockerRunner:
    def __init__(self, config: ManagerConfig):
        self.config = config
        self._client = None

    # ------------------------------------------------------------------
    # 就绪检查：Docker / 固定镜像 / 运行时 / 强制访问控制
    # ------------------------------------------------------------------
    def _docker(self):
        if self._client is not None:
            return self._client
        try:
            import docker  # 延迟导入：无 Docker 环境也能单元测试配置生成
        except ImportError as exc:  # pragma: no cover - 仅部署节点需要
            raise SandboxError("docker_sdk_missing", "docker python sdk 未安装") from exc
        try:
            if self.config.docker_host:
                self._client = docker.DockerClient(base_url=self.config.docker_host)
            else:
                self._client = docker.from_env()
        except Exception as exc:
            raise SandboxError("docker_unavailable", str(exc)) from exc
        return self._client

    def check_ready(self) -> dict:
        """确认本次执行所需的安全能力全部真实可用"""
        client = self._docker()
        try:
            client.ping()
        except Exception as exc:
            raise SandboxError("docker_unavailable", str(exc)) from exc

        image_ref = self.config.image
        try:
            image = client.images.get(image_ref)
        except Exception as exc:
            raise SandboxError("image_missing", f"固定镜像不存在: {image_ref}") from exc

        # 校验固定引用与本地镜像一致（Registry Manifest Digest ≠ Image ID，不能混用比较）
        try:
            verification = verify_image_reference(
                image_ref, image.id, image.attrs.get("RepoDigests") or []
            )
        except ValueError as exc:
            raise SandboxError("image_digest_mismatch", str(exc)) from exc

        info = client.info()
        runtime = self.config.runtime or ""
        if runtime:
            runtimes = info.get("Runtimes") or {}
            if runtime not in runtimes:
                raise SandboxError(
                    "runtime_unavailable",
                    f"配置的增强运行时 {runtime} 未启用（当前: {sorted(runtimes)}）",
                )
        else:
            runtime = info.get("DefaultRuntime") or "runc"

        if self.config.seccomp_profile and not os.path.isfile(self.config.seccomp_profile):
            raise SandboxError("seccomp_profile_missing", "seccomp 配置文件不存在")

        if self.config.apparmor_profile:
            try:
                with open("/sys/module/apparmor/parameters/enabled", "r", encoding="utf-8") as f:
                    enabled = f.read().strip()
            except OSError as exc:
                raise SandboxError("apparmor_unavailable", str(exc)) from exc
            if enabled != "Y":
                raise SandboxError("apparmor_unavailable", "内核未启用 AppArmor")

        return {
            "docker": True,
            "image": image_ref,
            "image_id": image.id,
            "image_verification": verification,
            "instance_id": self.config.instance_id,
            "runtime": runtime,
            "cpu_cores": self.config.cpu_cores,
            "memory_mb": self.config.memory_mb,
            "timeout_seconds": self.config.timeout_seconds,
            "pids_limit": self.config.pids_limit,
            "disk_mb": self.config.disk_mb,
            "output_bytes": self.config.output_bytes,
            "max_concurrent": self.config.max_concurrent,
        }

    def limits(self) -> SandboxLimits:
        return SandboxLimits(
            cpu_cores=self.config.cpu_cores,
            memory_mb=self.config.memory_mb,
            timeout_seconds=self.config.timeout_seconds,
            pids_limit=self.config.pids_limit,
            disk_mb=self.config.disk_mb,
            output_bytes=self.config.output_bytes,
            input_bytes=self.config.input_bytes,
            max_concurrent=self.config.max_concurrent,
            max_pending=self.config.effective_max_pending,
        )

    # ------------------------------------------------------------------
    # 残留容器清理（管理器重启 / 异常退出后）
    # ------------------------------------------------------------------
    def cleanup_stale_containers(self) -> int:
        """删除**本管理器实例**遗留的容器

        只匹配 `zd.sandbox=1` + `zd.sandbox.instance=<本实例>` 两个标签，
        因此同一节点上其他实例或其他服务的容器不会被误删。
        单节点推荐单实例运行；多实例部署必须为每个实例配置不同的
        `ZD_SANDBOX_INSTANCE_ID`。
        """
        client = self._docker()
        filters = {
            "label": [
                "zd.sandbox=1",
                f"zd.sandbox.instance={self.config.instance_id}",
            ]
        }
        try:
            containers = client.containers.list(all=True, filters=filters)
        except Exception as exc:
            raise SandboxError("cleanup_failed", str(exc)) from exc

        removed = 0
        for container in containers:
            try:
                container.remove(force=True)
                removed += 1
            except Exception as exc:
                logger.error("清理残留沙箱容器失败（未返回给学生）: %s", exc)
                raise SandboxError("cleanup_failed", str(exc)) from exc
        if removed:
            logger.warning("已清理 %s 个残留沙箱容器", removed)
        return removed

    # ------------------------------------------------------------------
    # 执行
    # ------------------------------------------------------------------
    @staticmethod
    def _kill(container) -> None:
        try:
            container.kill()
        except Exception:  # 容器可能已自然退出
            pass

    def _logs(self, container, stdout: bool, limit: int) -> str:
        """按字节上限流式读取日志

        Docker json-file 日志本身有轮转上限；这里再以流式方式读取，
        达到上限立即停止并关闭流，避免先把无限量日志读进内存再截断。
        """
        chunks: list[bytes] = []
        total = 0
        truncated = False
        stream = None
        try:
            stream = container.logs(stream=True, stdout=stdout, stderr=not stdout)
            for chunk in stream:
                if not chunk:
                    continue
                remaining = limit - total
                if len(chunk) >= remaining:
                    chunks.append(chunk[:remaining])
                    total = limit
                    truncated = True
                    break
                chunks.append(chunk)
                total += len(chunk)
        except Exception:
            return ""
        finally:
            close = getattr(stream, "close", None)
            if callable(close):
                try:
                    close()
                except Exception:
                    pass
        text = b"".join(chunks).decode("utf-8", "replace")
        if truncated:
            return text + "\n…（输出过长，已截断）"
        return text

    @staticmethod
    def _pump(container, out: _BoundedCapture, err: _BoundedCapture,
              errors: list[str]) -> None:
        """在后台线程中通过 attach 实时读取容器 stdout/stderr"""
        stream = None
        try:
            stream = container.attach(
                stream=True, logs=True, stdout=True, stderr=True, demux=True
            )
            for chunk_out, chunk_err in stream:
                if chunk_out:
                    out.feed(chunk_out)
                if chunk_err:
                    err.feed(chunk_err)
        except Exception as exc:  # attach 失败时由调用方回退到日志读取
            errors.append(type(exc).__name__)
        finally:
            close = getattr(stream, "close", None)
            if callable(close):
                try:
                    close()
                except Exception:
                    pass

    def run_job(
        self,
        code: str,
        timeout: int,
        cancel_event: threading.Event | None = None,
        job_id: str = "",
    ) -> dict:
        """运行一次任务并返回状态字典；任务结束后容器必定被回收"""
        self.check_ready()
        client = self._docker()
        kwargs = build_container_kwargs(
            image=self.config.image,
            code=code,
            limits=self.limits(),
            runtime=self.config.runtime,
            seccomp_profile=self.config.seccomp_profile,
            apparmor_profile=self.config.apparmor_profile,
            instance_id=self.config.instance_id,
            job_id=job_id,
        )
        container = client.containers.create(**kwargs)

        # 回查 Docker 实际生效的完整安全参数；任何一项未生效都拒绝执行并回收容器
        try:
            verify_container_security(
                container.attrs,
                self.limits(),
                self.config.runtime,
                self.config.image,
                self.config.seccomp_profile,
                self.config.apparmor_profile,
            )
        except RuntimeError as exc:
            try:
                container.remove(force=True)
            except Exception:
                logger.error("校验失败后清理容器也失败: %s", exc)
            raise SandboxError("security_config_not_applied", str(exc)) from exc

        timed_out = False
        cancelled = False
        started = time.monotonic()
        cleanup_failed = False
        # 启动前先建立 attach 流：实时读取输出，避免依赖会被轮转覆盖的 json-file 日志
        out_cap = _BoundedCapture(self.limits().stdout_limit)
        err_cap = _BoundedCapture(self.limits().stderr_limit)
        pump_errors: list[str] = []
        pump = threading.Thread(
            target=self._pump,
            args=(container, out_cap, err_cap, pump_errors),
            daemon=True,
        )
        pump.start()
        try:
            container.start()
            while True:
                container.reload()
                state = container.attrs.get("State", {})
                if not state.get("Running", False):
                    break
                if cancel_event is not None and cancel_event.is_set():
                    cancelled = True
                    self._kill(container)
                    break
                if time.monotonic() - started >= timeout:
                    timed_out = True
                    self._kill(container)
                    break
                time.sleep(0.2)

            try:
                container.wait(timeout=5)
            except Exception:
                # 已被 kill，等待状态刷新即可
                pass
            pump.join(timeout=10)
            container.reload()
            state = container.attrs.get("State", {})
            exit_code = state.get("ExitCode")
            oom_killed = bool(state.get("OOMKilled"))
            stdout = out_cap.text()
            stderr = err_cap.text()
            if pump_errors and not stdout and not stderr:
                # attach 不可用时回退到 json-file 日志（可能已被轮转覆盖）
                logger.warning("attach 读取输出失败(%s)，回退到日志读取", pump_errors)
                stdout = self._logs(container, stdout=True, limit=self.limits().stdout_limit)
                stderr = self._logs(container, stdout=False, limit=self.limits().stderr_limit)
            duration_ms = int((time.monotonic() - started) * 1000)
        except SandboxError:
            raise
        except Exception as exc:
            raise SandboxError("container_error", str(exc)) from exc
        finally:
            # 无论成功 / 超时 / 取消 / 异常，都必须销毁容器及其全部子进程
            try:
                container.remove(force=True)
            except Exception as exc:
                cleanup_failed = True
                logger.error("沙箱容器清理失败: %s", exc)

        if cleanup_failed:
            raise SandboxError("cleanup_failed", "容器清理失败，拒绝返回结果")

        if cancelled:
            status = "cancelled"
            exit_code = -1
        elif timed_out:
            status = "timeout"
            exit_code = -1
        elif exit_code == 0:
            status = "succeeded"
        elif oom_killed or exit_code == 137:
            status = "resource_exceeded"
        else:
            status = "failed"

        if not isinstance(exit_code, int):
            exit_code = -1

        return {
            "status": status,
            "stdout": stdout,
            "stderr": stderr,
            "exit_code": exit_code,
            "duration_ms": duration_ms,
        }
