#!/usr/bin/env bash
# 构建固定版本的沙箱执行镜像，并输出可直接写入 ZD_SANDBOX_IMAGE 的 digest 引用
#
# 用法：
#   ./build_image.sh [镜像tag] [基础镜像]
#   PYTHON_BASE=python:3.12.7-slim@sha256:... ./build_image.sh zd-sandbox-python:3.12
set -euo pipefail

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
TAG="${1:-zd-sandbox-python:3.12}"
BASE="${2:-${PYTHON_BASE:-python:3.12.7-slim}}"

echo "[1/3] 构建镜像 ${TAG}（基础镜像 ${BASE}）"
docker build --pull --build-arg "PYTHON_BASE=${BASE}" -t "${TAG}" "${HERE}/../sandbox_image"

echo "[2/3] 本地镜像 ID"
IMAGE_ID="$(docker inspect --format '{{.Id}}' "${TAG}")"
echo "    ${IMAGE_ID}"

echo "[3/3] 仓库 digest（推送私有仓库后可用）"
if REPO_DIGEST="$(docker inspect --format '{{index .RepoDigests 0}}' "${TAG}" 2>/dev/null)" && [[ -n "${REPO_DIGEST}" ]]; then
  echo "    ${REPO_DIGEST}"
else
  echo "    （本地构建镜像没有 RepoDigest；可先推送到私有仓库再 inspect，"
  echo "      或直接使用上面的本地镜像 ID 作为固定引用）"
fi

cat <<'EOF'

把下列配置写入执行节点（/etc/zd-sandbox/manager.env）：
  ZD_SANDBOX_IMAGE=<上面的 digest 或本地镜像 ID>
  ZD_SANDBOX_TOKEN=<随机长令牌>
提示：本地镜像 ID 仅在构建它的那台执行节点上有效；多节点部署请推送到私有仓库并使用
      repo@sha256:... 形式的 digest。
EOF
