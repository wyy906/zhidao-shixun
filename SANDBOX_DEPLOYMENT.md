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
- **执行节点必须独立部署**：专用 Linux 虚拟机/主机，不得与 FastAPI 业务后端、数据库、Redis 同机。
- 业务后端只能通过 HTTPS（生产强制）+ 管理令牌调用管理器，建议同时启用双向 TLS；
  **不得只依赖“IP 在局域网内”作为认证**。
- 管理接口默认只监听 `127.0.0.1`；跨机部署时必须绑定受防火墙保护的内网地址，
  并且**只允许业务后端服务器访问**该端口。
- 业务后端是**唯一**允许调用管理接口的服务；不得向学生网段、公网或桌面端暴露。
- Docker Socket 只对管理器进程可见，绝不挂载进学生代码执行容器，也不向业务网络暴露 Docker API。
- 学生代码容器不加入任何业务网络（`network_mode=none`）。

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
2. 本地镜像必须与固定引用一致：
   - `repo@sha256:<manifest-digest>`：校验本地镜像 `RepoDigests` 中存在该 digest
     （Registry Manifest Digest 与本地 Image ID 是两种不同摘要，**不能直接比较**）；
   - 本地 `sha256:<image-id>`：校验镜像 ID 完全相等。
   不匹配（镜像被替换、未按该 digest 拉取、RepoDigests 缺失）会返回
   `image_digest_mismatch` 并拒绝执行。
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
# 实例标识：用于容器标签与重启清理。单节点推荐单实例；
# 多实例必须显式设置且互不相同（默认取主机名）。
ZD_SANDBOX_INSTANCE_ID=zd-sandbox-01

# 资源限制（管理员配置，学生不可修改）
ZD_SANDBOX_CPU=0.5
ZD_SANDBOX_MEMORY_MB=128
ZD_SANDBOX_TIMEOUT=10
ZD_SANDBOX_PIDS=32
ZD_SANDBOX_DISK_MB=16
ZD_SANDBOX_OUTPUT_BYTES=65536
ZD_SANDBOX_INPUT_BYTES=65536
ZD_SANDBOX_MAX_CONCURRENT=2
# 排队任务上限；0 表示自动 = 4 × 最大并发。超限返回 queue_full（HTTP 429）
ZD_SANDBOX_MAX_PENDING=0

# 可选：内网 TLS / 双向 TLS
# 生产环境**必须**配置证书；缺少证书或证书不可读时管理器拒绝启动。
# 本机开发可显式改为 ZD_SANDBOX_ALLOW_INSECURE_HTTP=true，且只允许监听回环地址。
ZD_SANDBOX_TLS_CERT=/etc/zd-sandbox/server.crt
ZD_SANDBOX_TLS_KEY=/etc/zd-sandbox/server.key
ZD_SANDBOX_TLS_CLIENT_CA=/etc/zd-sandbox/ca.crt
# 仅本机开发测试使用；生产保持 false（不会自动降级为 HTTP）
ZD_SANDBOX_ALLOW_INSECURE_HTTP=false
# 可选：强制 seccomp / AppArmor / gVisor
# ZD_SANDBOX_SECCOMP=/etc/zd-sandbox/seccomp.json
# ZD_SANDBOX_APPARMOR=zd-sandbox
# ZD_SANDBOX_RUNTIME=runsc
```

> 证书/私钥必须成对配置；配置了 `ZD_SANDBOX_TLS_CLIENT_CA` 即为双向 TLS，
> 缺少证书、私钥或 CA 不可读都会导致启动失败。明文 HTTP 仅限 `127.0.0.1 / ::1 / localhost`
> 且必须显式设置 `ZD_SANDBOX_ALLOW_INSECURE_HTTP=true`，不存在证书失败后自动降级的路径。

```bash
sudo chmod 600 /etc/zd-sandbox/manager.env
sudo chown zd-sandbox:zd-sandbox /etc/zd-sandbox/manager.env
sudo cp /opt/zd-sandbox/sandbox_manager/systemd/zd-sandbox.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable --now zd-sandbox
sudo systemctl status zd-sandbox
```

> gVisor / AppArmor / seccomp 是**可配置的增强项**：配置后管理器会在 `/health` 与每次提交前
> 检查运行时是否存在、profile 文件是否可读、AppArmor 是否启用；创建容器后还会核对
> Docker `HostConfig.SecurityOpt` 中确实记录了对应选项。**但 inspect 只能证明配置被记录，
> 不能证明内核已加载并强制执行**——后者必须在执行节点用 `scripts/verify_isolation.py`
> 和实际攻击脚本验证，未验证前不得宣称“seccomp/AppArmor 已生效”。

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
# 业务后端侧并发保护：超限返回 429（不创建任务）
CODE_MAX_CONCURRENT_REQUESTS=8
CODE_MAX_CONCURRENT_PER_USER=1
```

注意事项：

- **非回环地址必须使用 HTTPS**：`http://10.0.0.20` 这类配置会在启动时被拒绝。
  仅本机开发可设 `SANDBOX_ALLOW_INSECURE_HTTP=true` 且目标为 `127.0.0.1 / ::1 / localhost`。
- `SANDBOX_MANAGER_CLIENT_CERT` 与 `_CLIENT_KEY` 必须同时配置或同时留空；
  只配置其中一个会导致启动失败，不存在静默降级为单向 TLS 的路径。
- 任何情况下都保留证书校验，不支持 `verify=False`。
- 业务后端**不会**在配置缺失时回退本机执行；未配置或不可用一律返回
  `503 {"detail": "代码执行环境暂不可用，请稍后重试。"}`。
- 并发超限返回 `429`，文案为“当前代码运行请求过多，请稍后重试。”
- 管理器队列满（HTTP 429）同样映射为业务后端 429，并以 `error_code=queue_full` 记录任务。
- 异步 HTTP 连接池由 FastAPI lifespan 在应用关闭时释放（`SandboxClient.aclose()`），
  不需要手工重启进程清理连接。
- 不允许把 `AI_API_KEY`、JWT 密钥、数据库连接串传给执行容器；容器环境变量只有学生代码本身。
- 业务后端不需要 Docker，也不需要挂载 Docker Socket。

## 7. 管理接口

所有接口都需要 `X-Sandbox-Token`。

网络暴露（必须）：

```bash
# 例：只允许业务后端服务器访问管理端口（ufw）
sudo ufw deny 8443/tcp
sudo ufw allow from <业务后端IP> to any port 8443 proto tcp
```

- 默认监听 `127.0.0.1`，由本机反向代理终止 TLS；跨机时绑定内网地址并配置上述防火墙规则。
- 业务后端是唯一调用方；学生浏览器、桌面端、公网一律不可达。
- 管理接口不提供任何“调试模式”“跳过认证”参数。

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
| 可写目录 | 仅 `/workspace`（12MB）、`/tmp`（4MB）与 `/dev/shm`（8MB），tmpfs、`noexec,nosuid,nodev`，合计 24MB；其中业务可写磁盘仍为 16MB |
| 宿主机挂载 | 无（`volumes={}`、`devices=[]`） |
| 网络 | `network_mode=none` + `network_disabled=true`（无公网 / 局域网 / 业务服务） |
| 端口映射 | 无 |
| CPU | `nano_cpus=500000000`（0.5 核） |
| 内存 | `mem_limit=128m`，`memswap_limit=128m`（禁用 swap） |
| 进程数 | `pids_limit=32`（限制 fork bomb） |
| 初始化 | `init=true`（回收僵尸进程） |
| 输出 | Docker json-file 日志轮转 `max-size=64k, max-file=1`（总存储 64KB）；返回时流式读取，stdout / stderr 各 32KB 上限，达到上限立即停止读取 |
| 生命周期 | 任务结束（成功/超时/取消/异常）一律 `remove(force=True)`，含全部子进程 |
| 启动自检 | 创建后回查 `Config` / `HostConfig`：运行用户、tmpfs 容量与 `noexec/nosuid/nodev`、`ShmSize`、日志驱动与轮转上限、端口映射、设备与挂载、CPU/内存/进程数、`CapAdd` 为空、`Init=true`、`SecurityOpt` 必须精确包含 `no-new-privileges:true`（及可选 seccomp、AppArmor）、运行时、镜像；任一不符立即删除容器并拒绝执行 |
| 队列 | 固定 `max_concurrent` 个 daemon 工作线程；内部 deque 长度不超过 `max_pending`；取消排队任务会立即从队列移除 |
| 结果校验 | 执行器返回的状态、stdout/stderr 类型、退出码、耗时均校验；畸形结果统一 `failed/internal_error` |
| 残留清理 | 管理器启动时只删除带 `zd.sandbox=1` **且** `zd.sandbox.instance=<本实例>` 标签的容器（上次异常退出遗留）；清理失败则拒绝启动 |

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
- 管理器重启 / 异常退出：启动时扫描并删除**本实例**遗留容器，过滤条件为
  `zd.sandbox=1` + `zd.sandbox.instance=<ZD_SANDBOX_INSTANCE_ID>`；
  其他实例、无实例标签的旧容器、其他服务的容器不会被误删。
- **清理失败会阻断启动**：Docker 不可用或容器删除失败时，管理器进程启动失败
  （`sandbox startup cleanup failed: <error_code>`），不会带着未知残留容器继续服务。
- 单节点推荐单实例运行；多实例部署必须为每个实例配置不同 `ZD_SANDBOX_INSTANCE_ID`。
- 旧版本（仅 `zd.sandbox=1` 标签）的残留容器需手动清理：

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
| 任务一直 `queued` | 并发或排队已满（默认 2 / 8） | 等待或调整 `ZD_SANDBOX_MAX_CONCURRENT` / `ZD_SANDBOX_MAX_PENDING`（管理员） |
| 提交返回 429 `queue_full` | 排队任务达到上限 | 业务后端同样返回 429（“当前代码运行请求过多”），任务记录 `error_code=queue_full`；稍后重试 |
| 取消后仍显示占位 | 仅取消排队任务会立即移出内部队列；运行中任务需等执行器退出 | 运行中取消由执行器在超时或下一个检查点终止 |
| 任务 `timeout` | 代码超时（上限 10s） | 学生优化代码；不允许提高上限 |
| 任务 `resource_exceeded` | 内存 / 进程 / 磁盘 / 输出超限 | 学生减少资源占用 |
| 401 unauthorized | 令牌不一致 | 核对两端令牌 |
| TLS 握手失败 | 证书域名 / CA 不匹配 | 使用节点 IP/域名签发证书并配置 CA |

## 15. 已知限制

- 本仓库开发环境为 Windows，未在真实 Linux 执行节点完成验收；
  所有“真实隔离已验证”的结论必须以 `verify_isolation.py` 的实机输出为准。
- Docker 默认 seccomp profile 由 Docker 提供；自定义 profile 需自行维护。
- 首版镜像只含标准库，第三方库需管理员重新构建镜像。

## 16. 数据库初始化（开发 / 生产）

| 环境 | 策略 |
|---|---|
| 开发（`APP_ENV=development`，`DB_AUTO_CREATE` 未设置） | 启动时 `create_all` 自动建表 |
| 生产（`APP_ENV=production` 或 `DB_AUTO_CREATE=false`） | **不自动建表**；缺表则拒绝启动并提示 `alembic upgrade head` |
| 显式 `DB_AUTO_CREATE=true` | 允许自动建表（仅建议本地开发） |

生产部署顺序：

```bash
cd backend
alembic upgrade head      # 必须成功
uvicorn app.main:app ...  # 缺表会直接启动失败
```

`code_tasks` 迁移文件：`backend/alembic/versions/20261112_0001_add_code_tasks.py`
（幂等：`create_all` 已建表时跳过；`downgrade` 可回滚）。
