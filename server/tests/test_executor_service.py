"""Docker 隔离执行服务核心单元测试（V2-04B 阶段 B）。

全部为 Mock 单元测试（FakeDriver），只验证服务层生命周期/安全门禁/错误分类逻辑；
绝不构成真实 Docker 集成验证（真实 Docker 集成测试保持 BLOCKED，
等待具备 Docker Engine 的环境）。
"""

import dataclasses
from pathlib import Path

import pytest

from app.services.executor.base import (
    DockerUnavailableError,
    ExecutionRequest,
    UnsafeExecutionRequest,
)
from app.services.executor.driver import ContainerSpec
from app.services.executor.models import ExecutionOutcome, ExecutionTask, FailureKind
from app.services.executor.service import SandboxExecutionService

EXECUTOR_DIR = Path(__file__).resolve().parents[1] / "app" / "services" / "executor"

DIGEST_OK = "sha256:" + "a" * 64


_DEFAULT_ENGINE = {"version": "27.0.0"}


class FakeDriver:
    """脚本化假驱动：记录调用与规格，返回预设结果。"""

    def __init__(self, engine=_DEFAULT_ENGINE, digest=DIGEST_OK, run_results=None, run_error=None):
        self.engine = engine
        self.digest = digest
        self.run_results = list(run_results or [])
        self.run_error = run_error
        self.specs: list[ContainerSpec] = []
        self.removed_containers = 0

    def engine_info(self):
        return self.engine

    def image_digest(self, image_ref):
        return self.digest

    def run(self, spec):
        self.specs.append(spec)
        self.removed_containers += 1  # 驱动契约：任何路径都移除容器
        if self.run_error is not None:
            raise self.run_error
        if self.run_results:
            item = self.run_results.pop(0)
            if isinstance(item, Exception):
                raise item
            return item
        from app.services.executor.driver import DriverRunResult

        return DriverRunResult(
            exit_code=0, stdout=b"hello\n", stderr=b"", timed_out=False,
            container_id="cid-fake",
        )


def make_task(code: str = "print('hello')", timeout: int = 5) -> ExecutionTask:
    return ExecutionTask(
        user_id="u1", experiment_id="exp1", task_id="t1",
        request=ExecutionRequest(language="python", code=code, timeout_seconds=timeout),
    )


def make_service(driver, **kwargs) -> SandboxExecutionService:
    return SandboxExecutionService(driver=driver, expected_digest=DIGEST_OK, **kwargs)


# ---------- 配置边界 ----------


def test_container_spec_fixes_security_baseline() -> None:
    spec = ContainerSpec(
        image_ref="python:3.12-slim",
        command=("python", "-I", "-u", "-c", "print(1)"),
        user="65534:65534", timeout_seconds=5, mem_limit="256m", cpus=1.0,
        pids_limit=64,
    )
    assert spec.network_mode == "none"
    assert spec.read_only is True
    assert "ALL" in spec.cap_drop
    assert "no-new-privileges" in spec.security_opt
    assert not spec.user.startswith("root")
    assert spec.workdir == "/sandbox"


def test_container_spec_rejects_disabled_baseline() -> None:
    base = dict(
        image_ref="python:3.12-slim", command=("python", "-c", "1"),
        user="65534:65534", timeout_seconds=5, mem_limit="256m", cpus=1.0,
        pids_limit=64,
    )
    with pytest.raises(ValueError, match="none"):
        ContainerSpec(**base, network_mode="host")
    with pytest.raises(ValueError, match="只读"):
        ContainerSpec(**base, read_only=False)
    with pytest.raises(ValueError, match="root"):
        ContainerSpec(**{**base, "user": "root"})
    with pytest.raises(ValueError, match="capabilities"):
        ContainerSpec(**base, cap_drop=())
    with pytest.raises(ValueError, match="no-new-privileges"):
        ContainerSpec(**base, security_opt=())


def test_container_spec_has_no_bind_mount_field() -> None:
    """任意挂载参数拒绝：规格中根本不存在宿主机挂载入口（结构级防护）。"""
    fields = {f.name for f in dataclasses.fields(ContainerSpec)}
    assert not {"mounts", "volumes", "binds", "devices", "privileged"} & fields


def test_execution_request_has_no_container_parameter_surface() -> None:
    """任意镜像/容器参数拒绝：用户请求模型不含 image/容器配置字段。"""
    fields = {f.name for f in dataclasses.fields(ExecutionRequest)}
    assert not {"image", "container", "network", "volumes", "mem_limit", "cpus"} & fields


def test_execution_task_requires_metadata() -> None:
    with pytest.raises(UnsafeExecutionRequest, match="user_id"):
        ExecutionTask(user_id=" ", experiment_id="e", task_id="t",
                      request=ExecutionRequest(language="python", code="1"))


# ---------- 镜像 digest 门禁 ----------


def test_digest_not_locked_fails_closed() -> None:
    driver = FakeDriver()
    service = SandboxExecutionService(driver=driver, expected_digest=None)
    outcome = service.execute(make_task())
    assert outcome.status == "error"
    assert outcome.failure_kind is FailureKind.IMAGE_DIGEST_NOT_LOCKED
    assert outcome.result is None
    assert driver.specs == []  # 未真正创建容器


def test_digest_mismatch_fails_closed() -> None:
    driver = FakeDriver(digest="sha256:" + "b" * 64)
    service = make_service(driver)
    outcome = service.execute(make_task())
    assert outcome.failure_kind is FailureKind.IMAGE_DIGEST_MISMATCH
    assert driver.specs == []


def test_image_missing_fails_closed() -> None:
    driver = FakeDriver(digest=None)
    service = make_service(driver)
    outcome = service.execute(make_task())
    assert outcome.failure_kind is FailureKind.IMAGE_NOT_FOUND
    assert driver.specs == []


# ---------- Docker 不可用 ----------


def test_docker_unavailable_fails_closed_without_host_fallback() -> None:
    driver = FakeDriver(engine=None)
    service = make_service(driver)
    outcome = service.execute(make_task())
    assert outcome.status == "error"
    assert outcome.failure_kind is FailureKind.DOCKER_UNAVAILABLE
    assert "宿主机回退" in outcome.failure_detail
    assert driver.specs == []


# ---------- 生命周期与结果采集 ----------


def test_successful_execution_returns_completed_result() -> None:
    driver = FakeDriver()
    service = make_service(driver)
    outcome = service.execute(make_task(code="print('hello')"))
    assert outcome.status == "completed"
    assert outcome.result.exit_code == 0
    assert outcome.result.stdout == "hello\n"
    assert outcome.result.stderr == ""
    assert outcome.result.timed_out is False
    assert outcome.container_id == "cid-fake"
    assert outcome.duration_ms is not None
    # 代码经命令向量传入，无 shell、无 bind mount
    spec = driver.specs[0]
    assert spec.command[0:3] == ("python", "-I", "-u")
    assert spec.command[3] == "-c"
    assert spec.command[4] == "print('hello')"


def test_nonzero_exit_is_completed_not_error() -> None:
    """Python 运行失败（非零退出码）是 completed，不是执行器错误。"""
    from app.services.executor.driver import DriverRunResult

    driver = FakeDriver(run_results=[DriverRunResult(
        exit_code=1, stdout=b"", stderr=b"ValueError\n", timed_out=False,
        container_id="cid-2")])
    service = make_service(driver)
    outcome = service.execute(make_task())
    assert outcome.status == "completed"
    assert outcome.result.exit_code == 1
    assert outcome.result.stderr == "ValueError\n"
    assert outcome.failure_kind is None


def test_timeout_is_flagged_not_disguised() -> None:
    from app.services.executor.driver import DriverRunResult

    driver = FakeDriver(run_results=[DriverRunResult(
        exit_code=None, stdout=b"", stderr=b"", timed_out=True, container_id="cid-3")])
    service = make_service(driver)
    outcome = service.execute(make_task())
    assert outcome.status == "timeout"
    assert outcome.result.timed_out is True
    assert outcome.failure_kind is None


def test_output_limit_truncation() -> None:
    from app.services.executor.driver import DriverRunResult

    big = b"x" * (65536 + 10)
    driver = FakeDriver(run_results=[DriverRunResult(
        exit_code=0, stdout=big, stderr=b"", timed_out=False, container_id="cid-4")])
    service = make_service(driver)
    outcome = service.execute(make_task())
    assert outcome.result.truncated is True
    assert len(outcome.result.stdout.encode("utf-8")) <= 65536


def test_container_create_failure_is_structured_error() -> None:
    driver = FakeDriver(run_error=RuntimeError("create failed: image pull error"))
    service = make_service(driver)
    outcome = service.execute(make_task())
    assert outcome.status == "error"
    assert outcome.failure_kind is FailureKind.EXECUTION_INTERNAL_ERROR
    assert outcome.result is None  # Docker 异常绝不伪装成运行结果
    assert "create failed" in outcome.failure_detail


def test_workdir_isolated_per_container() -> None:
    """每次任务独立容器；工作目录为容器内 tmpfs 路径，无宿主机路径。"""
    driver = FakeDriver()
    service = make_service(driver)
    service.execute(make_task())
    service.execute(make_task(code="print(2)"))
    assert len(driver.specs) == 2
    assert driver.specs[0].command[4] != driver.specs[1].command[4]
    for spec in driver.specs:
        assert spec.workdir == "/sandbox"
        assert all(p.startswith("/") for p in spec.tmpfs)


def test_executor_error_mapped_to_internal_error() -> None:
    driver = FakeDriver(run_error=UnsafeExecutionRequest("bad spec"))
    service = make_service(driver)
    outcome = service.execute(make_task())
    assert outcome.failure_kind is FailureKind.EXECUTION_INTERNAL_ERROR


# ---------- 静态安全检查 ----------


@pytest.mark.parametrize("filename", ["base.py", "service.py", "docker_adapter.py",
                                      "driver.py", "models.py"])
def test_no_host_execution_fallback_in_executor_sources(filename: str) -> None:
    """宿主机执行回退不存在：执行器源码不得引入 subprocess/os.system/os.popen。"""
    source = (EXECUTOR_DIR / filename).read_text(encoding="utf-8")
    assert "import subprocess" not in source
    assert "os.system" not in source
    assert "os.popen" not in source


def test_docker_sdk_import_is_lazy_in_adapter() -> None:
    """Docker SDK 惰性导入：业务进程导入 adapter 模块本身不会加载 docker 包。"""
    source = (EXECUTOR_DIR / "docker_adapter.py").read_text(encoding="utf-8")
    module_top = source.split("\nclass ")[0]
    assert "import docker" not in module_top
    assert "import docker" in source.split("\nclass ")[1]


def test_base_placeholder_still_refuses_without_service() -> None:
    """占位执行器保持拒绝语义（未接执行服务的调用方拿不到任何执行能力）。"""
    from app.services.executor.base import DockerCodeExecutor

    with pytest.raises(DockerUnavailableError):
        DockerCodeExecutor().run(ExecutionRequest(language="python", code="print(1)"))


def test_docker_sdk_driver_tolerates_missing_sdk() -> None:
    """无 docker SDK 环境：驱动可构造、engine_info 如实返回 None、run fail-closed——
    执行服务因此能在无 Docker 机器上启动并诚实报告（C2 集成修正）。"""
    import importlib.util

    from app.services.executor.docker_adapter import DockerSdkDriver

    if importlib.util.find_spec("docker") is not None:
        pytest.skip("docker SDK 已安装，容错路径不适用（该环境应有真实引擎）")
    driver = DockerSdkDriver()
    assert driver.engine_info() is None
    assert driver.image_digest("python:3.12-slim") is None
    spec = ContainerSpec(
        image_ref="python:3.12-slim",
        command=("python", "-I", "-u", "-c", "print(1)"),
        user="65534:65534", timeout_seconds=5, mem_limit="256m", cpus=1.0,
        pids_limit=64,
    )
    with pytest.raises(DockerUnavailableError, match="无宿主机回退"):
        driver.run(spec)
