"""容器安全配置单元测试（无需 Docker，任何平台可运行）

这些测试只能证明“请求的容器参数是正确的”，**不能**证明真实运行时已生效。
真实隔离必须在 Linux 执行节点上用 scripts/verify_isolation.py 验证。
"""
import base64

import pytest

from sandbox_manager.container_spec import (
    BOOTSTRAP_CODE,
    SandboxLimits,
    build_container_kwargs,
    verify_container_security,
)

IMAGE = "zd-sandbox-python@sha256:" + "a" * 64


def _kwargs(**overrides):
    limits = SandboxLimits()
    return build_container_kwargs(IMAGE, "print('hi')", limits, **overrides)


def test_network_is_completely_disabled():
    kw = _kwargs()
    assert kw["network_mode"] == "none"
    assert kw["network_disabled"] is True
    # 不映射任何端口
    assert "ports" not in kw or not kw["ports"]


def test_no_privileged_and_drops_all_capabilities():
    kw = _kwargs()
    assert kw["privileged"] is False
    assert kw["cap_drop"] == ["ALL"]
    assert "no-new-privileges:true" in kw["security_opt"]


def test_runs_as_non_root():
    kw = _kwargs()
    assert kw["user"] == "65534:65534"
    assert not kw["user"].startswith("0")


def test_filesystem_is_read_only_with_limited_tmpfs():
    kw = _kwargs()
    assert kw["read_only"] is True
    assert kw["volumes"] == {}
    assert kw["devices"] == []
    assert set(kw["tmpfs"]) == {"/tmp", "/workspace"}
    total_mb = 0
    for opts in kw["tmpfs"].values():
        assert "size=" in opts
        assert "noexec" in opts
        total_mb += int(opts.split("size=")[1].split("m")[0])
    # 临时磁盘总额不得超过配置上限（16MB）
    assert total_mb <= SandboxLimits().disk_mb


def test_resource_limits():
    kw = _kwargs()
    limits = SandboxLimits()
    assert kw["mem_limit"] == f"{limits.memory_mb}m"
    assert kw["memswap_limit"] == f"{limits.memory_mb}m"  # 禁用 swap
    assert kw["pids_limit"] == limits.pids_limit
    assert kw["nano_cpus"] == int(limits.cpu_cores * 1_000_000_000)
    assert kw["init"] is True


def test_output_is_capped_by_docker_log_rotation():
    kw = _kwargs()
    assert kw["log_config"]["Config"]["max-size"] == "64k"
    assert kw["log_config"]["Config"]["max-file"] == "1"


def test_code_is_passed_via_environment_only():
    code = "print('sandbox')\n"
    kw = build_container_kwargs(IMAGE, code, SandboxLimits())
    assert set(kw["environment"]) == {"ZD_CODE_B64"}
    assert base64.b64decode(kw["environment"]["ZD_CODE_B64"]).decode() == code
    assert "--network" not in " ".join(kw["command"])
    assert "-I" in kw["command"] and "-B" in kw["command"]
    assert kw["command"][-1] == BOOTSTRAP_CODE


def test_seccomp_apparmor_and_runtime_are_opt_in():
    kw = _kwargs(
        seccomp_profile="/etc/zd-sandbox/seccomp.json",
        apparmor_profile="zd-sandbox",
        runtime="runsc",
    )
    assert "seccomp=/etc/zd-sandbox/seccomp.json" in kw["security_opt"]
    assert "apparmor=zd-sandbox" in kw["security_opt"]
    assert kw["runtime"] == "runsc"


def test_no_auto_remove_so_exit_code_can_be_read():
    kw = _kwargs()
    assert kw["auto_remove"] is False
    assert kw["detach"] is True


# ===========================================================================
# 回查 Docker 实际生效参数（防止“以为生效其实没生效”）
# ===========================================================================
def _attrs(image=IMAGE, **host_overrides) -> dict:
    limits = SandboxLimits()
    host = {
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
    }
    host.update(host_overrides)
    return {"Config": {"User": "65534:65534", "Image": image}, "HostConfig": host}


def test_verify_accepts_expected_container_attrs():
    verify_container_security(_attrs(), SandboxLimits())
    verify_container_security(_attrs(), SandboxLimits(), image=IMAGE)


@pytest.mark.parametrize("overrides", [
    {"NetworkMode": "bridge"},
    {"ReadonlyRootfs": False},
    {"Privileged": True},
    {"Memory": 1024 ** 3},
    {"MemorySwap": -1},
    {"NanoCpus": 0},
    {"PidsLimit": 0},
    {"CapDrop": []},
    {"SecurityOpt": []},
    {"Binds": ["/:/host"]},
    {"Devices": [{"PathOnHost": "/dev/sda"}]},
    {"PortBindings": {"8080/tcp": [{"HostPort": "8080"}]}},
    {"PublishAllPorts": True},
    {"Tmpfs": {}},
    {"LogConfig": {"Type": "none", "Config": {}}},
    {"LogConfig": {"Type": "json-file", "Config": {"max-size": "1g", "max-file": "1"}}},
    {"LogConfig": {"Type": "json-file", "Config": {"max-size": "64k", "max-file": "10"}}},
])
def test_verify_rejects_weak_container_attrs(overrides):
    with pytest.raises(RuntimeError):
        verify_container_security(_attrs(**overrides), SandboxLimits())


def test_verify_checks_tmpfs_flags_and_capacity():
    bad_flags = _attrs(Tmpfs={
        "/tmp": "rw,size=4m",
        "/workspace": "rw,noexec,nosuid,nodev,size=12m",
    })
    with pytest.raises(RuntimeError):
        verify_container_security(bad_flags, SandboxLimits())

    too_large = _attrs(Tmpfs={
        "/tmp": "rw,noexec,nosuid,nodev,size=64m",
        "/workspace": "rw,noexec,nosuid,nodev,size=64m",
    })
    with pytest.raises(RuntimeError):
        verify_container_security(too_large, SandboxLimits())


def test_verify_checks_running_user_and_image():
    attrs = _attrs()
    attrs["Config"]["User"] = "0:0"
    with pytest.raises(RuntimeError):
        verify_container_security(attrs, SandboxLimits())

    with pytest.raises(RuntimeError):
        verify_container_security(_attrs(image="other@sha256:" + "f" * 64),
                                  SandboxLimits(), image=IMAGE)


def test_verify_checks_configured_runtime():
    verify_container_security(_attrs(Runtime="runsc"), SandboxLimits(), runtime="runsc")
    with pytest.raises(RuntimeError):
        verify_container_security(_attrs(Runtime="runc"), SandboxLimits(), runtime="runsc")
