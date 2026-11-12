"""固定镜像引用校验测试（Registry Manifest Digest ≠ Image ID）"""
import pytest

from sandbox_manager.image_verify import verify_image_reference

IMAGE_ID = "sha256:" + "c" * 64
MANIFEST = "sha256:" + "a" * 64
REGISTRY_REF = f"zd-sandbox-python@{MANIFEST}"


def test_local_image_id_match():
    assert verify_image_reference(IMAGE_ID, IMAGE_ID, []) == "local-image-id"


def test_local_image_id_mismatch():
    other = "sha256:" + "d" * 64
    with pytest.raises(ValueError, match="镜像 ID 不匹配"):
        verify_image_reference(IMAGE_ID, other, [])


def test_registry_digest_match_uses_repo_digests_not_image_id():
    # manifest digest 与本地 image id 本来就不同，不能直接比较
    assert verify_image_reference(REGISTRY_REF, IMAGE_ID, [REGISTRY_REF]) == "registry-digest"
    # RepoDigests 可能带完整仓库域名
    prefixed = "docker.io/zd-sandbox-python@" + MANIFEST
    assert verify_image_reference(REGISTRY_REF, IMAGE_ID, [prefixed]) == "registry-digest"


def test_registry_digest_rejects_replaced_image():
    other_digest = "sha256:" + "e" * 64
    with pytest.raises(ValueError, match="RepoDigests"):
        verify_image_reference(REGISTRY_REF, IMAGE_ID, [f"zd-sandbox-python@{other_digest}"])


def test_registry_digest_rejects_missing_repo_digests():
    with pytest.raises(ValueError, match="RepoDigests"):
        verify_image_reference(REGISTRY_REF, IMAGE_ID, [])


def test_registry_digest_rejects_wrong_digest():
    wrong_ref = "zd-sandbox-python@sha256:" + "f" * 64
    with pytest.raises(ValueError, match="RepoDigests"):
        verify_image_reference(wrong_ref, IMAGE_ID, [REGISTRY_REF])


def test_rejects_tag_or_invalid_image_id():
    with pytest.raises(ValueError):
        verify_image_reference("zd-sandbox-python:3.12", IMAGE_ID, [])
    with pytest.raises(ValueError, match="格式异常"):
        verify_image_reference(IMAGE_ID, "not-a-digest", [])
