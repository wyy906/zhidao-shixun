# 沙箱执行镜像（首版只含 Python 标准库）
#
# 固定方式：
#   1) 固定基础镜像版本（推荐再用 digest 固定，见 SANDBOX_DEPLOYMENT.md）
#   2) 构建后用 scripts/build_image.sh 得到镜像 ID / 仓库 digest，
#      把该 digest 写入执行节点的 ZD_SANDBOX_IMAGE
#
# 不允许在运行时 pip install：镜像中直接移除包管理器。
ARG PYTHON_BASE=python:3.12.7-slim
FROM ${PYTHON_BASE}

RUN python -m pip uninstall -y pip setuptools wheel 2>/dev/null || true \
    && rm -rf /root/.cache /var/lib/apt/lists/* /tmp/*

# 默认以非 root 运行（管理器创建容器时还会再次显式指定 user=65534:65534）
USER 65534:65534
WORKDIR /workspace

CMD ["python", "-c", "print('zd sandbox image ready')"]
