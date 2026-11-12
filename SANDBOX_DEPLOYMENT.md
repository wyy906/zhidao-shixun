# 代码执行沙箱部署文档

> 适用版本：阶段 3-A。学生 Python 代码**只在独立 Linux 执行节点的一次性 Docker 容器中运行**，
> FastAPI 业务后端不执行学生代码，也不持有 Docker 权限。

---

## 1. 架构

```
Vue 网页端
   │  POST /api/v1/code/run（JWT）
   ▼
FastAPI 业务后端（可部署在 Windows / Linux）
   │  校验身份、代码长度、超时上限；创建 CodeTask；HTTPS + 令牌 / mTLS
   ▼
独立 Linux 执行节点
   │  sandbox_manager（systemd，专用非 root 账号）
   │  └── Docker Engine（本机 unix socket，仅管理器可访问）
   ▼
一次性 Docker 容器（每任务一个，任务结束即删除）
```

职责边界：

| 组件 | 负责 | 不负责 |
|---|---|---|
| 业务后端 | 身份认证、权限、输入校验、任务记录、结果返回 | 执行代码、访问 Docker |
| 沙箱管理器 | 接收任务、创建/监控/回收容器、资源限制 | 用户身份、业务数据 |
| 执行容器 | 只运行本次学生代码 | 网络、宿主机文件、持久化 |

**必须遵守**：
- 执行节点与业务服务器分离（独立 Linux 虚拟机，最小化安装）。
- 业务后端只能通过 HTTPS（推荐双向 TLS）+ 管理令牌调用管理器；
  **不得只依赖“IP 在局域网内”作为认证**。
- Docker Socket 只对管理器进程可见，绝不挂载进执行容器，也不向业务网络暴露 Docker API。

## 2. 执行节点环境要求

- Linux x86_64（Ubuntu 22.04/24.04 或 Debian 12 已验证路径）。
- 2 vCPU / 2GB 内存起步（并发 2 时）。
- 出网：仅允许操作系统补丁与镜像拉取；学生代码容器**无任何网络**。
- 磁盘：Docker 数据目录预留 ≥ 10GB（镜像 + 日志轮转）。
- 内核：建议启用 AppArmor；如需更强隔离可安装 gVisor（`runsc`）。
- 时间同步（chrony/systemd-timesyncd）。

## 3. Docker 安装与加固

```bash
sudo apt update && sudo apt install -y docker.io
sudo systemctl enable --now docker

# 创建专用账号，仅授予 docker 组权限（不要用 root 运行管理器）
sudo useradd -r -s /usr/sbin/nologin -G docker zd-sandbox
```

加固建议（`/etc/docker/daemon.json`）：

```json
{
  "icc": false,
  "no-new-privileges": true,
  "live-restore": true,
  "log-driver": "json-file",
  "log-opts": { "max-size": "10m", "max-file": "2" },
  "userland-proxy": false
}
```

```bash
sudo systemctl restart docker
```

> `icc=false` 禁止容器间互通；`no-new-privileges` 作为全局默认；日志轮转防止磁盘被写满。

## 4. 构建固定 Python 镜像

仅预装 Python 标准库（首版不预装第三方教学库）：

```bash
cd /opt/zd-sandbox-src
sudo bash sandbox_manager/scripts/build_image.sh zd-sandbox-python:3.12
```

脚本会输出镜像 ID 或仓库 digest。**必须**把 digest 写入执行节点配置：

- 单节点：可用本地镜像 ID（`sha256:...`）。
- 多节点 / 可重建环境：推送到私有仓库，使用 `repo@sha256:...`。

管理器启动时会检查：
1. 镜像引用必须固定到 digest；使用 tag 会**拒绝启动**。
2. 本地镜像 ID 必须与配置 digest 一致（防 tag 漂移 / 镜像被替换）。
3. 镜像不存在 → `/health` 返回 503，所有任务拒绝执行。

后续需要第三方教学库时：由管理员审核后在 `sandbox_manager/sandbox_image/Dockerfile` 中
加入固定版本依赖，重新构建并更新 digest；**不允许**学生在运行时 `pip install`。

## 5. 部署沙箱管理器

```bash
sudo mkdir -p /opt/zd-sandbox /etc/zd-sandbox
sudo cp -r sandbox_manager /opt/zd-sandbox/
cd /opt/zd-sandbox
sudo python3 -m venv venv
sudo ./venv/bin/pip install -r sandbox_manager/requirements.txt
sudo chown -R zd-sandbox:zd-sandbox /opt/zd-sandbox
```

`/etc/zd-sandbox/manager.env`（权限 `600`，属主 `zd-sandbox`）：

```ini
ZD_SANDBOX_TOKEN=<至少 32 位随机令牌>
ZD_SANDBOX_IMAGE=zd-sandbox-python@sha256:<64位digest>
# 监听：同机反代可保持 127.0.0.1；跨机调用需 0.0.0.0 + TLS
ZD_SANDBOX_HOST=127.0.0.1
ZD_SANDBOX_PORT=8443

# 资源限制（管理员配置，学生不可修改）
ZD_SANDBOX_CPU=0.5
ZD_SANDBOX_MEMORY_MB=128
ZD_SANDBOX_TIMEOUT=10
ZD_SANDBOX_PIDS=32
ZD_SANDBOX_DISK_MB=16
ZD_SANDBOX_OUTPUT_BYTES=65536
ZD_SANDBOX_INPUT_BYTES=65536
ZD_SANDBOX_MAX_CONCURRENT=2

# 可选：内网 TLS / 双向 TLS
ZD_SANDBOX_TLS_CERT=/etc/zd-sandbox/server.crt
ZD_SANDBOX_TLS_KEY=/etc/zd-sandbox/server.key
ZD_SANDBOX_TLS_CLIENT_CA=/etc/zd-sandbox/ca.crt
# 可选：强制 seccomp / AppArmor / gVisor
# ZD_SANDBOX_SECCOMP=/etc/zd-sandbox/seccomp.json
# ZD_SANDBOX_APPARMOR=zd-sandbox
# ZD_SANDBOX_RUNTIME=runsc
```

```bash
sudo chmod 600 /etc/zd-sandbox/manager.env
sudo chown zd-sandbox:zd-sandbox /etc/zd-sandbox/manager.env
sudo cp /opt/zd-sandbox/sandbox_manager/systemd/zd-sandbox.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable --now zd-sandbox
sudo systemctl status zd-sandbox
```

> gVisor / AppArmor / seccomp 是**可配置的增强项**：配置后管理器会在 `/health` 与每次提交前
> 真实检查（运行时不存在、配置文件缺失、AppArmor 未启用都会拒绝执行），不会只停留在配置文件声明。

## 6. 业务后端配置

`backend/.env`：

```ini
CODE_EXECUTION_ENABLED=true
SANDBOX_MANAGER_URL=https://10.0.0.20:8443
SANDBOX_MANAGER_TOKEN=<与执行节点一致>
# 内网自签证书需要指定 CA；双向 TLS 还需客户端证书/私钥
SANDBOX_MANAGER_CA_FILE=/etc/zd/manager-ca.crt
SANDBOX_MANAGER_CLIENT_CERT=/etc/zd/client.crt
SANDBOX_MANAGER_CLIENT_KEY=/etc/zd/client.key

CODE_RUN_TIMEOUT_SECONDS=10
CODE_MAX_INPUT_BYTES=65536
CODE_MAX_OUTPUT_BYTES=65536
```

注意事项：

- 业务后端**不会**在配置缺失时回退本机执行；未配置或不可用一律返回
  `503 {"detail": "代码执行环境暂不可用，请稍后重试。"}`。
- 不允许把 `AI_API_KEY`、JWT 密钥、数据库连接串传给执行容器；容器环境变量只有学生代码本身。
- 业务后端不需要 Docker，也不需要挂载 Docker Socket。

## 7. 管理接口

所有接口都需要 `X-Sandbox-Token`。

| 方法 | 路径 | 说明 |
|---|---|---|
| GET | `/health` | 就绪状态（Docker / 镜像 digest / 运行时 / 限制参数） |
| POST | `/v1/jobs` | 提交 `{code, timeout}`，返回 `202 {job_id, status}` |
| GET | `/v1/jobs/{job_id}` | 查询状态与结果 |
| DELETE | `/v1/jobs/{job_id}` | 取消（运行中容器被强制终止） |

任务状态：`queued / running / succeeded / failed / timeout / resource_exceeded / cancelled`。

```bash
curl -s -H "X-Sandbox-Token: $ZD_SANDBOX_TOKEN" https://127.0.0.1:8443/health | python3 -m json.tool
```

## 8. 容器安全配置（实际生效项）

每个任务创建**独立临时容器**，参数由 `sandbox_manager/container_spec.py` 生成：

| 项 | 配置 |
|---|---|
| 用户 | `65534:65534`（nobody），非 root |
| 特权 | `privileged=false` |
| Capabilities | `cap_drop=["ALL"]` |
| 提权 | `no-new-privileges:true` |
| seccomp | Docker 默认 profile；可指定自定义 profile |
| MAC | 可选 AppArmor / gVisor（配置即校验，不可用则拒绝执行） |
| 根文件系统 | `read_only=true` |
| 可写目录 | 仅 `/workspace`（12MB）与 `/tmp`（4MB），tmpfs、`noexec,nosuid,nodev`，合计 16MB |
| 宿主机挂载 | 无（`volumes={}`、`devices=[]`） |
| 网络 | `network_mode=none` + `network_disabled=true`（无公网 / 局域网 / 业务服务） |
| 端口映射 | 无 |
| CPU | `nano_cpus=500000000`（0.5 核） |
| 内存 | `mem_limit=128m`，`memswap_limit=128m`（禁用 swap） |
| 进程数 | `pids_limit=32`（限制 fork bomb） |
| 初始化 | `init=true`（回收僵尸进程） |
| 输出 | Docker json-file 日志轮转 `max-size=64k, max-file=1` + 应用层截断 |
| 生命周期 | 任务结束（成功/超时/取消/异常）一律 `remove(force=True)`，含全部子进程 |

超时 / 取消通过 `container.kill()` 终止整个容器，而不是只杀最外层 Python 进程。

## 9. 网络隔离验证

```bash
cd /opt/zd-sandbox
sudo -u zd-sandbox ZD_SANDBOX_TOKEN=<token> \
  ./venv/bin/python sandbox_manager/scripts/verify_isolation.py \
  --url https://127.0.0.1:8443 --token <token> \
  --ca /etc/zd-sandbox/ca.crt \
  --lan-host 10.0.0.5 --lan-port 3306 \
  --backend-host 10.0.0.10 --backend-port 8000
```

脚本会验证：公网不可达、局域网/数据库/业务端口不可达、宿主机标记文件不可读、
工作目录独立、无限循环超时、内存超限、fork 受限、磁盘受限、输出截断、无残留容器。

> ⚠️ 该脚本包含破坏性测试，只能在**专用、可销毁的测试节点**运行。

## 10. 文件隔离验证

脚本会自动在宿主机 `/tmp/zd_sandbox_host_marker` 写入标记文件，要求容器内不可读取；
还可用 `--host-file /opt/zhidao/backend/.env` 验证业务文件不可读。判定标准：

- 容器内 `/workspace` 为空（不与其他任务共享目录）；
- 任务结束后容器及其 tmpfs 一并销毁；
- 宿主机目录不会以任何形式挂载进容器。

## 11. 健康检查与监控

```bash
# 服务状态
systemctl status zd-sandbox
# 管理接口健康检查（含镜像 digest / 运行时 / 资源限制）
curl -s -H "X-Sandbox-Token: $TOKEN" https://127.0.0.1:8443/health | python3 -m json.tool
# 是否存在残留容器（正常应为空）
docker ps -a --filter label=zd.sandbox=1
# 查看日志
journalctl -u zd-sandbox -f
```

建议纳入监控：
- `/health` 非 200 告警（镜像缺失 / 运行时不可用 / 配置错误）。
- `docker ps -a --filter label=zd.sandbox=1` 长时间非空。
- 执行节点磁盘使用率。

## 12. 容器与临时文件清理

- 正常路径：管理器在任务结束后强制删除容器与 tmpfs。
- 异常残留（管理器崩溃、节点断电）：

```bash
docker ps -a --filter label=zd.sandbox=1 -q | xargs -r docker rm -f
```

- 管理器重启后内存中的任务记录消失；业务后端查询会得到 404 → 按“沙箱不可用”安全失败，
  不会把未完成任务当成成功。

## 13. 关闭代码执行功能

任选其一：

1. 业务后端：`CODE_EXECUTION_ENABLED=false`，`/code/run` 立即返回 503。
2. 清空 `SANDBOX_MANAGER_URL`，所有执行请求一律拒绝。
3. 执行节点：`systemctl stop zd-sandbox`，业务后端连接失败 → 503。

三种方式都不会回退到本机执行。

## 14. 故障排查

| 现象 | 可能原因 | 处理 |
|---|---|---|
| 业务端 503 | 未配置 URL/令牌、节点不可达、TLS 校验失败 | 检查 `.env`、网络、CA |
| `/health` 503 `docker_unavailable` | Docker 未启动 / 无 socket 权限 | `systemctl start docker`；确认账号在 docker 组 |
| `/health` 503 `image_missing` | 镜像未构建或 digest 不匹配 | 重新构建并更新 `ZD_SANDBOX_IMAGE` |
| `/health` 503 `runtime_unavailable` | 配置了 gVisor 但未安装 | 安装 runsc 或清空 `ZD_SANDBOX_RUNTIME` |
| `/health` 503 `apparmor_unavailable` | 内核未启用 AppArmor | 启用或清空 `ZD_SANDBOX_APPARMOR` |
| 任务一直 `queued` | 并发已满（默认 2） | 等待或调整 `ZD_SANDBOX_MAX_CONCURRENT`（管理员） |
| 任务 `timeout` | 代码超时（上限 10s） | 学生优化代码；不允许提高上限 |
| 任务 `resource_exceeded` | 内存 / 进程 / 磁盘 / 输出超限 | 学生减少资源占用 |
| 401 unauthorized | 令牌不一致 | 核对两端令牌 |
| TLS 握手失败 | 证书域名 / CA 不匹配 | 使用节点 IP/域名签发证书并配置 CA |

## 15. 已知限制

- 本仓库开发环境为 Windows，未在真实 Linux 执行节点完成验收；
  所有“真实隔离已验证”的结论必须以 `verify_isolation.py` 的实机输出为准。
- Docker 默认 seccomp profile 由 Docker 提供；自定义 profile 需自行维护。
- 首版镜像只含标准库，第三方库需管理员重新构建镜像。
