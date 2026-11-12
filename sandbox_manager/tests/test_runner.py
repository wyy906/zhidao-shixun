"""DockerRunner 生命周期测试（FakeDocker，无需 Docker）

验证：成功 / 超时 / 取消 / 启动失败 / 安全参数不符时都会强制回收容器；
管理器重启后的残留容器清理；固定镜像校验。
"""
import threading
import types

import pytest

from sandbox_manager.config import ManagerConfig
from sandbox_manager.container_spec import SandboxLimits
from sandbox_manager.runner import DockerRunner, SandboxError

IMAGE_REF = "zd-sandbox-python@sha256:" + "a" * 64
IMAGE_ID = "sha256:" + "c" * 64


def _valid_attrs() -> dict:
    limits = SandboxLimits()
    return {
        "Config": {"User": "65534:65534", "Image": IMAGE_REF},
        "HostConfig": {
            "NetworkMode": "none",
            "ReadonlyRootfs": True,
            "Privileged": False,
            "Memory": limits.memory_mb * 1024 * 1024,
            "MemorySwap": limits.memory_mb * 1024 * 1024,
            "NanoCpus": int(limits.cpu_cores * 1_000_000_000),
            "PidsLimit": limits.pids_limit,
            "CapDrop": ["ALL"],
            "SecurityOpt": ["no-new-privileges:true"],
            "Binds": None,
            "Devices": [],
            "PortBindings": {},
            "PublishAllPorts": False,
            "Tmpfs": {
                "/tmp": "rw,noexec,nosuid,nodev,mode=1777,size=4m",
                "/workspace": "rw,noexec,nosuid,nodev,mode=1777,size=12m",
            },
            "LogConfig": {"Type": "json-file", "Config": {"max-size": "64k", "max-file": "1"}},
            "Runtime": "runc",
        },
        "State": {"Running": False, "ExitCode": 0, "OOMKilled": False},
    }


class FakeContainer:
    def __init__(self, attrs=None, start_error=None, never_stop=False,
                 remove_error=None, exit_code=0, oom=False):
        self._attrs = attrs or _valid_attrs()
        self.start_error = start_error
        self.never_stop = never_stop
        self.remove_error = remove_error
        self._exit_code = exit_code
        self._oom = oom
        self.removed = False
        self.killed = False

    @property
    def attrs(self):
        return self._attrs

    def start(self):
        if self.start_error:
            raise self.start_error
        self._attrs["State"] = {
            "Running": self.never_stop, "ExitCode": self._exit_code, "OOMKilled": self._oom,
        }

    def reload(self):
        return None

    def wait(self, timeout=None):
        return {"StatusCode": self._attrs["State"].get("ExitCode", 0)}

    def kill(self):
        self.killed = True
        self._attrs["State"] = {"Running": False, "ExitCode": 137, "OOMKilled": False}

    def logs(self, stdout=True, stderr=False, timestamps=False):
        return b"hello\n" if stdout else b""

    def remove(self, force=False):
        if self.remove_error:
            raise self.remove_error
        self.removed = True


class FakeImage:
    def __init__(self, image_id=IMAGE_ID, repo_digests=None):
        self.id = image_id
        self.attrs = {"RepoDigests": [IMAGE_REF] if repo_digests is None else repo_digests}


class FakeDocker:
    def __init__(self, container=None, image=None, listed=None):
        self.container = container or FakeContainer()
        self.image = image or FakeImage()
        self.listed = listed or []
        self.created_kwargs = None
        self.containers = types.SimpleNamespace(
            create=self._create, list=self._list_containers,
        )
        self.images = types.SimpleNamespace(get=lambda ref: self.image)

    def ping(self):
        return True

    def info(self):
        return {"Runtimes": {"runc": {}}, "DefaultRuntime": "runc"}

    def _create(self, **kwargs):
        self.created_kwargs = kwargs
        return self.container

    def _list_containers(self, all=True, filters=None):
        return self.listed


def _runner(fake: FakeDocker) -> DockerRunner:
    cfg = ManagerConfig(token="test-token", image=IMAGE_REF, allow_insecure_http=True)
    runner = DockerRunner(cfg)
    runner._client = fake
    return runner


# ===========================================================================
# 正常 / 超时 / 取消 / 失败都必须回收容器
# ===========================================================================
def test_success_removes_container():
    container = FakeContainer()
    runner = _runner(FakeDocker(container))
    result = runner.run_job("print(1)", timeout=1)
    assert result["status"] == "succeeded"
    assert result["stdout"] == "hello\n"
    assert container.removed is True


def test_start_failure_removes_container():
    container = FakeContainer(start_error=RuntimeError("boom"))
    runner = _runner(FakeDocker(container))
    with pytest.raises(SandboxError) as exc:
        runner.run_job("print(1)", timeout=1)
    assert exc.value.code == "container_error"
    assert container.removed is True


def test_timeout_kills_and_removes_container():
    container = FakeContainer(never_stop=True)
    runner = _runner(FakeDocker(container))
    result = runner.run_job("while True: pass", timeout=0.05)
    assert result["status"] == "timeout"
    assert container.killed is True
    assert container.removed is True


def test_cancel_kills_and_removes_container():
    container = FakeContainer(never_stop=True)
    event = threading.Event()
    event.set()
    runner = _runner(FakeDocker(container))
    result = runner.run_job("print(1)", timeout=5, cancel_event=event)
    assert result["status"] == "cancelled"
    assert container.killed is True
    assert container.removed is True


def test_oom_maps_to_resource_exceeded():
    container = FakeContainer(exit_code=137, oom=True)
    runner = _runner(FakeDocker(container))
    result = runner.run_job("x = bytearray(10**9)", timeout=1)
    assert result["status"] == "resource_exceeded"
    assert container.removed is True


def test_security_mismatch_removes_container_and_refuses():
    attrs = _valid_attrs()
    attrs["HostConfig"]["NetworkMode"] = "bridge"
    container = FakeContainer(attrs=attrs)
    runner = _runner(FakeDocker(container))
    with pytest.raises(SandboxError) as exc:
        runner.run_job("print(1)", timeout=1)
    assert exc.value.code == "security_config_not_applied"
    assert container.removed is True


def test_cleanup_failure_is_reported():
    container = FakeContainer(remove_error=RuntimeError("busy"))
    runner = _runner(FakeDocker(container))
    with pytest.raises(SandboxError) as exc:
        runner.run_job("print(1)", timeout=1)
    assert exc.value.code == "cleanup_failed"


# ===========================================================================
# 残留容器清理（管理器重启后）
# ===========================================================================
def test_cleanup_stale_containers_removes_all_labeled():
    containers = [FakeContainer(), FakeContainer()]
    runner = _runner(FakeDocker(listed=containers))
    assert runner.cleanup_stale_containers() == 2
    assert all(c.removed for c in containers)


def test_cleanup_stale_containers_failure_is_reported():
    containers = [FakeContainer(remove_error=RuntimeError("busy"))]
    runner = _runner(FakeDocker(listed=containers))
    with pytest.raises(SandboxError) as exc:
        runner.cleanup_stale_containers()
    assert exc.value.code == "cleanup_failed"


# ===========================================================================
# 固定镜像引用校验接入 check_ready
# ===========================================================================
def test_check_ready_accepts_registry_digest():
    runner = _runner(FakeDocker())
    info = runner.check_ready()
    assert info["image_verification"] == "registry-digest"


def test_check_ready_accepts_local_image_id():
    cfg = ManagerConfig(token="test-token", image=IMAGE_ID, allow_insecure_http=True)
    runner = DockerRunner(cfg)
    runner._client = FakeDocker(image=FakeImage(image_id=IMAGE_ID))
    assert runner.check_ready()["image_verification"] == "local-image-id"


def test_check_ready_rejects_local_image_id_mismatch():
    cfg = ManagerConfig(token="test-token", image=IMAGE_ID, allow_insecure_http=True)
    runner = DockerRunner(cfg)
    runner._client = FakeDocker(image=FakeImage(image_id="sha256:" + "d" * 64))
    with pytest.raises(SandboxError) as exc:
        runner.check_ready()
    assert exc.value.code == "image_digest_mismatch"


def test_check_ready_rejects_replaced_registry_image():
    runner = _runner(FakeDocker(image=FakeImage(repo_digests=["zd-sandbox-python@sha256:" + "e" * 64])))
    with pytest.raises(SandboxError) as exc:
        runner.check_ready()
    assert exc.value.code == "image_digest_mismatch"
