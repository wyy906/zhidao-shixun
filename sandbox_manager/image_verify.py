"""固定镜像引用校验

Docker 有两类完全不同的摘要，**不能混用**：
  - Registry Manifest Digest：`repo@sha256:...`，由仓库推送/拉取时产生，
    记录在本地镜像的 `RepoDigests` 中；
  - Image ID：`sha256:...`，是本地镜像配置 JSON 的哈希（`docker images -q` 显示的值）。

因此：
  - 配置为 Registry Digest 时，必须校验本地镜像的 RepoDigests 中包含该 digest
    （而不是拿 manifest digest 去和 image.id 比较）；
  - 配置为本地 Image ID 时，直接校验镜像 ID 完全相等；
  - 其余情况（tag、短 ID、空值）一律拒绝。
"""
from __future__ import annotations

import re

_SHA256_RE = re.compile(r"^sha256:[0-9a-f]{64}$")
_DIGEST_SUFFIX_RE = re.compile(r"@(sha256:[0-9a-f]{64})$")


def verify_image_reference(image_ref: str, image_id: str, repo_digests: list[str] | None) -> str:
    """校验固定引用与本地镜像一致；不一致时抛 ValueError

    返回 "registry-digest" 或 "local-image-id"，便于日志/健康检查区分。
    """
    ref = (image_ref or "").strip()
    local_id = (image_id or "").strip().lower()

    if not _SHA256_RE.match(local_id):
        raise ValueError(f"本地镜像 ID 格式异常: {image_id!r}")

    # 1) 本地 Image ID 固定
    if ref.startswith("sha256:"):
        if local_id != ref.lower():
            raise ValueError(f"镜像 ID 不匹配: 本地 {local_id} != 配置 {ref}")
        return "local-image-id"

    # 2) Registry Manifest Digest 固定
    match = _DIGEST_SUFFIX_RE.search(ref)
    if match:
        expected = match.group(1)
        digests = [str(d).strip().lower() for d in (repo_digests or [])]
        if not any(d.endswith("@" + expected) for d in digests):
            raise ValueError(
                "本地镜像的 RepoDigests 中不存在配置的 digest，"
                f"可能已被替换或未经该 digest 拉取: 期望 {expected}，实际 {digests}"
            )
        return "registry-digest"

    raise ValueError("镜像引用未固定到 digest（允许 repo@sha256:... 或本地 sha256:<image-id>）")
