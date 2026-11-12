"""执行器接口与安全基线测试（V2-02 占位实现的行为验证）。"""

import pytest

from app.services.executor.base import (
    DockerCodeExecutor,
    DockerSandboxConfig,
    DockerUnavailableError,
    ExecutionRequest,
    UnsafeExecutionRequest,
)


def test_sandbox_config_defaults_match_d1_baseline() -> None:
    config = DockerSandboxConfig()
    assert config.network_disabled is True
    assert config.read_only_rootfs is True
    assert config.no_docker_socket is True
    assert config.non_root_user not in ("", "root", "0:0")
    assert config.max_output_bytes <= 65536


def test_sandbox_config_forbids_disabling_baseline() -> None:
    with pytest.raises(ValueError, match="禁网"):
        DockerSandboxConfig(network_disabled=False)
    with pytest.raises(ValueError, match="只读"):
        DockerSandboxConfig(read_only_rootfs=False)
    with pytest.raises(ValueError, match="Docker socket"):
        DockerSandboxConfig(no_docker_socket=False)
    with pytest.raises(ValueError, match="非 root"):
        DockerSandboxConfig(non_root_user="root")


def test_execution_request_validation() -> None:
    with pytest.raises(UnsafeExecutionRequest, match="语言"):
        ExecutionRequest(language="bash", code="echo hi")
    with pytest.raises(UnsafeExecutionRequest, match="为空"):
        ExecutionRequest(language="python", code="   ")
    with pytest.raises(UnsafeExecutionRequest, match="上限"):
        ExecutionRequest(language="python", code="x" * 70000)
    with pytest.raises(UnsafeExecutionRequest, match="timeout_seconds"):
        ExecutionRequest(language="python", code="print(1)", timeout_seconds=60)
    ok = ExecutionRequest(language="python", code="print(1)")
    assert ok.language == "python"


def test_executor_refuses_execution_without_docker_fallback() -> None:
    executor = DockerCodeExecutor()
    request = ExecutionRequest(language="python", code="print(1)")
    with pytest.raises(DockerUnavailableError, match="不提供宿主机回退执行"):
        executor.run(request)
