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

### 2.1 节点就绪检查（部署前必须全部通过）

```bash
# 1) 系统与内核
lsb_release -a
uname -r

# 2) Docker 版本与服务状态（建议 Docker Engine 24+）
docker version --format 'client={{.Client.Version}} server={{.Server.Version}}'
systemctl is-active docker

# 3) cgroup v2（CPU / 内存 / PID 限额依赖 cgroup）
stat -fc %T /sys/fs/cgroup        # 期望输出 cgroup2fs
test -f /sys/fs/cgroup/cpu.max && echo cgroup-v2-ok

# 4) AppArmor（如计划启用）
cat /sys/module/apparmor/parameters/enabled   # 期望 Y

# 5) 端口占用（8443 不应被其他服务占用）
ss -lntp | grep 8443 || echo "8443 free"
```

> 以上任一项不满足时不要继续部署；cgroup v1 节点请先升级或调整内核启动参数启用 cgroup v2。

## 3. Docker 安装与加固

```bash
sudo apt update && sudo apt install -y docker.io
sudo systemctl enable --now docker

# 创建专用账号，仅授予 docker 组权限（不要用 root 运行管理器）
sudo useradd -r -s /usr/sbin/nologin -G docker zd-sandbox
sudo -u zd-sandbox docker version --format '{{.Server.Version}}'   # 验证 docker 组权限可用
```

> Docker Socket 等价于宿主机 root 权限：`zd-sandbox` 账号只应存在于专用执行节点，
> 不得在该节点运行其他业务服务。<br>
> 如需 gVisor：按官方文档安装 `runsc` 并在 `/etc/docker/daemon.json` 的 `runtimes` 中注册，
> 再用 `docker info --format '{{json .Runtimes}}'` 确认存在。

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

仅预装 Python 标准库（首版不预装第三方教学库）。先把仓库检出到执行节点：

```bash
sudo mkdir -p /opt/zhidao-shixun
sudo chown "$USER":"$USER" /opt/zhidao-shixun
git clone https://github.com/wyy906/zhidao-shixun.git /opt/zhidao-shixun
REPO=/opt/zhidao-shixun          # 如仓库在其他路径，修改为实际路径

# 构建镜像（需要节点能拉取 Python 基础镜像）
sudo bash "$REPO/sandbox_manager/scripts/build_image.sh" zd-sandbox-python:3.12
```

脚本会输出镜像 ID 或仓库 digest。**必须**把 digest 写入执行节点配置：

- 单节点：可用本地镜像 ID（`sha256:...`）。
- 多节点 / 可重建环境：推送到私有仓库，使用 `repo@sha256:...`。

验证输出与本地镜像一致：

```bash
docker inspect --format '{{.Id}}' zd-sandbox-python:3.12
docker inspect --format '{{json .RepoDigests}}' zd-sandbox-python:3.12
```

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
REPO=${REPO:-/opt/zhidao-shixun}   # 仓库检出路径，如不同请修改
# 依赖：python3-venv（Ubuntu 默认未安装）
sudo apt update && sudo apt install -y python3-venv

sudo mkdir -p /opt/zd-sandbox /etc/zd-sandbox
sudo cp -r "$REPO/sandbox_manager" /opt/zd-sandbox/
sudo cp "$REPO/SANDBOX_DEPLOYMENT.md" /opt/zd-sandbox/   # systemd Documentation 路径
sudo python3 -m venv /opt/zd-sandbox/venv
sudo /opt/zd-sandbox/venv/bin/pip install -r /opt/zd-sandbox/sandbox_manager/requirements.txt
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

常用运维命令：

```bash
sudo systemctl start zd-sandbox     # 启动
sudo systemctl stop zd-sandbox      # 停止（业务端随后返回 503）
sudo systemctl restart zd-sandbox   # 重启（启动时会清理本实例残留容器）
journalctl -u zd-sandbox -n 200 --no-pager   # 查看最近日志
journalctl -u zd-sandbox -f                  # 实时日志
```

> gVisor / AppArmor / seccomp 是**可配置的增强项**：配置后管理器会在 `/health` 与每次提交前
> 检查运行时是否存在、profile 文件是否可读、AppArmor 是否启用；创建容器后还会核对
> Docker `HostConfig.SecurityOpt` 中确实记录了对应选项。**但 inspect 只能证明配置被记录，
> 不能证明内核已加载并强制执行**——后者必须在执行节点用 `scripts/verify_isolation.py`
> 和实际攻击脚本验证，未验证前不得宣称“seccomp/AppArmor 已生效”。

### 5.1 HTTPS / 双向 TLS 证书生成与验证

以下命令在**执行节点**用 bash 执行；把 `10.0.0.20` 换成执行节点真实内网 IP/DNS。

```bash
sudo mkdir -p /etc/zd-sandbox/tls && cd /etc/zd-sandbox/tls

# 1) 私有 CA（10 年）
sudo openssl req -x509 -newkey rsa:4096 -nodes -days 3650 \
  -keyout ca.key -out ca.crt -subj "/CN=ZD-Sandbox-CA"

# 2) 服务端证书（含 IP SAN；必须与实际访问地址一致）
sudo openssl req -newkey rsa:3072 -nodes -keyout server.key -out server.csr \
  -subj "/CN=zd-sandbox"
sudo openssl x509 -req -in server.csr -CA ca.crt -CAkey ca.key -CAcreateserial \
  -days 825 -out server.crt \
  -extfile <(printf "subjectAltName=IP:10.0.0.20,DNS:zd-sandbox.local\nextendedKeyUsage=serverAuth")

# 3) 业务后端客户端证书（双向 TLS）
sudo openssl req -newkey rsa:3072 -nodes -keyout client.key -out client.csr \
  -subj "/CN=zhidao-backend"
sudo openssl x509 -req -in client.csr -CA ca.crt -CAkey ca.key -CAcreateserial \
  -days 825 -out client.crt \
  -extfile <(printf "extendedKeyUsage=clientAuth")

# 4) 权限：管理器账号可读，其他用户不可读
sudo chown zd-sandbox:zd-sandbox server.crt server.key ca.crt
sudo chmod 640 ca.crt server.crt
sudo chmod 600 server.key ca.key
```

`manager.env` 对应配置：

```ini
ZD_SANDBOX_HOST=10.0.0.20        # 跨机访问时绑定内网地址
ZD_SANDBOX_TLS_CERT=/etc/zd-sandbox/tls/server.crt
ZD_SANDBOX_TLS_KEY=/etc/zd-sandbox/tls/server.key
ZD_SANDBOX_TLS_CLIENT_CA=/etc/zd-sandbox/tls/ca.crt   # 配置后强制双向 TLS
```

验证（在业务后端所在机器）：

```bash
# 单向握手 + 服务端证书校验（应输出 Verify return code: 0 (ok)）
openssl s_client -connect 10.0.0.20:8443 -CAfile ca.crt \
  -verify_ip 10.0.0.20 -verify_return_error </dev/null

# 无客户端证书访问双向 TLS 端口：应握手失败（预期失败）
curl -sS https://10.0.0.20:8443/health --cacert ca.crt || echo "mTLS 拒绝无客户端证书（预期）"

# 带客户端证书 + 错误令牌：应 HTTP 401（预期失败）
curl -sS -o /dev/null -w '%{http_code}\n' https://10.0.0.20:8443/health \
  --cacert ca.crt --cert client.crt --key client.key -H 'X-Sandbox-Token: wrong'

# 带客户端证书 + 正确令牌：应 200
curl -sS https://10.0.0.20:8443/health \
  --cacert ca.crt --cert client.crt --key client.key \
  -H "X-Sandbox-Token: $ZD_SANDBOX_TOKEN" | python3 -m json.tool
```

> 任何握手失败都不存在自动降级为 HTTP 的分支；管理器与业务后端都会直接拒绝请求。

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
| 结果校验 | 执行器返回的状态、stdout/stderr 类型、退出码、耗时、error_code、error_message 均严格校验（拒绝 bool 冒充整数）；畸形结果统一 `failed/internal_error`；业务后端在保存前再次完整校验，校验失败不会写成 succeeded |
| 残留清理 | 管理器启动时只删除带 `zd.sandbox=1` **且** `zd.sandbox.instance=<本实例>` 标签的容器（上次异常退出遗留）；清理失败则拒绝启动 |

超时 / 取消通过 `container.kill()` 终止整个容器，而不是只杀最外层 Python 进程。

## 9. 网络隔离验证

```bash
cd /opt/zd-sandbox
TOKEN='<与 manager.env 中 ZD_SANDBOX_TOKEN 一致>'
./venv/bin/python sandbox_manager/scripts/verify_isolation.py \
  --url https://10.0.0.20:8443 --token "$TOKEN" \
  --ca /etc/zd-sandbox/tls/ca.crt \
  --on-execution-node --confirm-manager-docker-same-host --docker-check local \
  --client-cert /etc/zd-sandbox/tls/client.crt \
  --client-key /etc/zd-sandbox/tls/client.key \
  --expect-mtls \
  --invalid-client-cert /tmp/bad-client.crt \
  --invalid-client-key /tmp/bad-client.key \
  --lan-host 10.0.0.5 --lan-port 3306 \
  --backend-host 10.0.0.10 --backend-port 8000 \
  --host-file /tmp/zd_host_probe.txt \
  --expected-cpu 0.5 --expected-memory-mb 128 --expected-pids 32 \
  --expected-swap-mb 0 \
  --output-limit 32768 --output-total-limit 65536
```

参数说明：

| 参数 | 作用 |
|---|---|
| `--on-execution-node` | **操作人员的人工声明**，不是密码学身份认证，也不能单独让身份检查通过。声明脚本直接运行在 Docker 执行节点 |
| `--confirm-manager-docker-same-host` | **人工核验声明**：已确认“管理器实际使用的 Docker Engine 就是本机执行节点”。只有它 + `--on-execution-node` + 本机 Docker 可用三者同时成立，节点身份/标记文件/残留容器检查才执行，否则一律 SKIP（结论 INCOMPLETE） |
| `--docker-check local\|skip` | `local` 表示本机 Docker CLI 就是执行节点，检查 `label=zd.sandbox=1` 残留容器；否则 SKIP |
| `--client-cert` / `--client-key` | 双向 TLS 客户端证书，必须成对；私钥不会输出 |
| `--expect-mtls` | 声明服务端强制 mTLS，执行四项验证：合法证书成功、无证书拒绝、错误证书拒绝、不受信服务端证书失败 |
| `--invalid-client-cert` / `--invalid-client-key` | mTLS 负向测试用的错误证书；缺失时该项为必检 SKIP（结论 INCOMPLETE） |
| `--expected-cpu` / `--expected-memory-mb` / `--expected-pids` | 从 cgroup v2 实际值校验限额，CPU 会同时校验 quota 与 period 比例 |
| `--expected-swap-mb` | 校验 `/sys/fs/cgroup/memory.swap.max`；本项目 `memory_swap == memory`，期望 `0`（`max` 视为未限制，不算通过） |
| `--output-limit` | 单流（stdout 或 stderr）输出上限，默认 `32768`（32KB） |
| `--output-total-limit` | stdout + stderr 合计上限，默认 `65536`（64KB） |

> 在**执行节点本机**运行时也可用 `--url https://127.0.0.1:8443`（需证书包含对应名称/IP）。
> `--host-file` 必须是执行节点上**专门创建的无敏感内容测试文件**（例如
> `/tmp/zd_host_probe.txt`），不要指向真实 `.env` 或真实密钥文件。

**执行节点身份确认（人工前置）**：

本架构中管理器与 Docker Engine 位于**同一执行节点**（见 §2 拓扑）；Docker Socket
只对本机管理器可见（§3）。但 `--on-execution-node` 只是操作人员的声明，本机
`docker info` 成功也**不能**证明管理器使用的就是本机 Docker Engine。因此必须：

1. 通过 SSH 登录到该执行节点（即运行管理器、持有 `/var/run/docker.sock` 的机器）；
2. 在该机器上逐项核对：
   - 沙箱管理器实际运行位置（进程 / systemd 单元所在主机）；
   - 管理器的 Docker 连接配置（`ZD_SANDBOX_DOCKER_HOST` 或等价配置）；
   - Docker Engine 的实际地址（`docker info`、`/var/run/docker.sock` 指向）；
   - Docker Socket 是否就是**该节点本机** Socket；
   - 若设置了 `DOCKER_HOST`、`DOCKER_CONTEXT`、远程 TCP 端点或自定义 Socket，
     必须确认管理器使用的是同一个 Engine，否则不得视为同节点；
3. 确认无误后，在命令中显式加上 `--confirm-manager-docker-same-host` 再运行脚本。

若未进行上述人工确认（或本机 Docker 不可用），节点身份、宿主机标记文件、容器
残留检查一律 SKIP，结论为 INCOMPLETE（退出码 2），**不得视为通过**。该确认是
**人工核验声明**，不提供任何密码学身份认证。

判定与输出：

- 每项输出 `[PASS] / [FAIL] / [SKIP]`，可选项目额外标注“（可选）”。
- **PASS**：所有必检项通过。
- **FAIL**：任一必检项失败。
- **INCOMPLETE**：无 FAIL，但存在必检项 SKIP（标记文件机器不确定、Docker CLI 不在节点、
  缺少客户端证书、cgroup 不可读等）。SKIP **不等于**通过。
- 退出码：`0` = PASS；`1` = FAIL；`2` = INCOMPLETE（非零）。

脚本覆盖：

- 错误令牌必须由服务端返回 HTTP 401 才算通过；网络、TLS、DNS 异常一律记为 FAIL
- 公网 / 局域网 / 业务端口不可达：测试代码成功执行并输出结构化 `NET_RESULT`；
  只有明确“连接未建立”的错误才作为阻断证据：
  - `ENETUNREACH(101)` / `EHOSTUNREACH(113)`、`EACCES(13)` / `EPERM(1)` → PASS
  - `ConnectionRefusedError(111)` → **FAIL**（主机可达、仅端口无服务，不能证明隔离）
  - `timeout(110)`、`gaierror`（DNS 解析失败）、未知异常 → **FAIL**
  - 连接成功、缺少 `NET_RESULT`、任务失败 → FAIL；输出记录异常类型与 errno 作为判定依据
- 执行节点身份：必须 `--on-execution-node` + `--confirm-manager-docker-same-host` +
  本机 Docker 可用三者齐备才记“人工核验通过”；缺失任一条件该项 SKIP，
  **不提供密码学身份认证**
- 宿主机标记文件、业务项目文件 / `.env` 不可读：仅在人工确认节点身份后才创建标记
  文件并执行；未确认时为必检 SKIP，不进行宿主机文件隔离测试
- 任务工作目录独立且为空、非 root（`UID: 65534`）、根文件系统只读、仅回环网卡
- cgroup v2 实际限额：CPU quota/period 比例、内存字节数、`memory.swap.max`（期望 0）、
  PID 数；文件不可读时该项 SKIP，不得当作通过
- 无限循环超时、内存超限、fork 受限、磁盘受限
- 输出截断：分别提交大量 stdout、大量 stderr 两个独立任务，校验各自字节数、任务终态、
  非空输出，且实际字节数须**接近单流上限**（≥ 上限的 90%，防止“只返回少量字节”假通过）；
  **另提交第三个独立任务在同一 Python 进程内同时产生 5MB stdout 与 5MB stderr**，
  用该单任务的 `stdout_bytes + stderr_bytes` 校验 `--output-total-limit`，要求两通道都接近
  单流上限、合计接近且不超过总上限+截断标记容差（不得把两个不同任务的输出相加冒充合计；
  任一通道为空/明显不足、任务异常终止、合计过低均不算通过）
- 任务结束后无残留容器（需 `--docker-check local` 且已人工确认节点身份）

> ⚠️ 该脚本包含破坏性测试，只能在**专用、可销毁的测试节点**运行。

## 10. 文件隔离验证

脚本会在**人工确认执行节点身份后**于宿主机 `/tmp/zd_verify_marker_<pid>` 写入临时标记文件，
要求容器内不可读取，测试结束自动删除；未确认节点身份时不创建标记文件，该项为 SKIP。
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
| `/health` 503 `image_digest_mismatch` | 本地镜像与配置的 digest / 镜像 ID 不一致（镜像被替换） | 重新按固定 digest 拉取或重建，更新配置 |
| 启动报 `sandbox startup cleanup failed` | Docker 不可用或残留容器删除失败 | 先修复 Docker，再手动检查 `docker ps -a --filter label=zd.sandbox=1` |
| 启动报 `token_not_configured` / 401 | 令牌为空或两端不一致 | 核对 `manager.env` 与业务后端 `SANDBOX_MANAGER_TOKEN` |
| `/health` 503 `seccomp_profile_missing` | 配置了 seccomp 但文件不存在 | 放置 profile 或清空 `ZD_SANDBOX_SECCOMP` |
| 启动报证书/私钥不可读 | 文件权限或属主错误 | `chown zd-sandbox`，证书 `640`、私钥 `600` |
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

## 17. 实机安全验收清单（S-01 ~ S-15）

> **当前状态：全部未执行。** 本仓库开发机为 Windows，未安装 Docker，也没有可连接的
> Linux 执行节点，因此没有任何一项可以标记为“通过”。本节只定义在真实节点上的
> 执行命令、预期结果和证据要求；**不得用单元测试或配置检查替代实机结论**。

执行前准备（在业务后端所在机器或执行节点本机执行；以下变量按实际替换）：

```bash
BASE=https://10.0.0.20:8443
TOKEN='<manager.env 中的 ZD_SANDBOX_TOKEN>'
CA=/etc/zd-sandbox/tls/ca.crt
CERT=/etc/zd-sandbox/tls/client.crt
KEY=/etc/zd-sandbox/tls/client.key
API="curl -sS --cacert $CA --cert $CERT --key $KEY -H \"X-Sandbox-Token: $TOKEN\""

# 提交一个保持 8 秒的任务，供 docker inspect 观察运行中的容器
JOB=$(curl -sS --cacert "$CA" --cert "$CERT" --key "$KEY" \
  -H "X-Sandbox-Token: $TOKEN" -H 'Content-Type: application/json' \
  -X POST "$BASE/v1/jobs" \
  -d '{"code":"import time\ntime.sleep(8)","timeout":8}' \
  | python3 -c 'import sys,json;print(json.load(sys.stdin)["job_id"])')
CID=$(docker ps -q --filter label=zd.sandbox=1 | head -n1)
echo "job=$JOB container=$CID"
```

| 编号 | 验收目标 | 执行命令 | 预期结果 | 实际结果 | 证据保存位置 | 状态 |
|---|---|---|---|---|---|---|
| S-01 | 容器网络隔离（无公网 / 局域网 / 业务端口） | `verify_isolation.py ... --lan-host <IP> --lan-port <端口> --backend-host <IP> --backend-port 8000`；`docker inspect $CID --format '{{.HostConfig.NetworkMode}}'` | 公网/局域网/业务端口均不可达为 PASS；仅接受 `ENETUNREACH/EHOSTUNREACH/EACCES/EPERM` 证据，`ConnectionRefused`、DNS 失败、超时、未知异常均为 FAIL；`NetworkMode=none` | 未执行 | `S-01.txt` | 未执行 |
| S-02 | 文件系统隔离（宿主机 / 业务文件不可读） | 在**执行节点**运行 `verify_isolation.py ... --on-execution-node --host-file /tmp/zd_host_probe.txt`；`docker inspect $CID --format '{{json .Mounts}}'` | 标记文件/业务文件读取被拒绝（`READ_DENIED`）；`Mounts=[]`；非执行节点运行时该项为 SKIP | 未执行 | `S-02.txt` | 未执行 |
| S-03 | 根文件系统只读 | `verify_isolation.py`；`docker inspect $CID --format '{{.HostConfig.ReadonlyRootfs}}'` | `MOUNT_OPTS: ro...` 为 PASS；`ReadonlyRootfs=true` | 未执行 | `S-03.txt` | 未执行 |
| S-04 | 非 root 身份运行 | `verify_isolation.py`；`docker inspect $CID --format '{{.Config.User}}'` | `UID: 65534` 为 PASS；`User=65534:65534` | 未执行 | `S-04.txt` | 未执行 |
| S-05 | 无额外挂载与设备 | `docker inspect $CID --format '{{json .Mounts}} {{json .HostConfig.Devices}}'` | `[] []` | 未执行 | `S-05.txt` | 未执行 |
| S-06 | 无端口映射 | `docker ps --format '{{.Ports}}' --filter label=zd.sandbox=1`；`docker inspect $CID --format '{{json .HostConfig.PortBindings}}'` | 端口列为空；绑定为 `{}` 或 `null` | 未执行 | `S-06.txt` | 未执行 |
| S-07 | CPU 限制 0.5 核 | `docker inspect $CID --format '{{.HostConfig.NanoCpus}}'`；`verify_isolation.py` | `500000000`；cgroup `CPU_MAX: 50000 100000` | 未执行 | `S-07.txt` | 未执行 |
| S-08 | 内存与交换限制 128MB | `docker inspect $CID --format '{{.HostConfig.Memory}} {{.HostConfig.MemorySwap}}'`；`verify_isolation.py --expected-swap-mb 0` | `134217728 134217728`；`MEM_MAX: 134217728`；`SWAP_MAX: 0`（`max` 不算通过） | 未执行 | `S-08.txt` | 未执行 |
| S-09 | PID 数量限制 32 | `docker inspect $CID --format '{{.HostConfig.PidsLimit}}'`；`verify_isolation.py` | `32`；`PIDS_MAX: 32`；fork 测试 PASS | 未执行 | `S-09.txt` | 未执行 |
| S-10 | 临时磁盘限制（tmpfs 合计 24MB，业务 16MB） | `docker inspect $CID --format '{{json .HostConfig.Tmpfs}}'`；`verify_isolation.py` | 含 `/workspace`、`/tmp`、`/dev/shm` 与容量/`noexec,nosuid,nodev`；磁盘测试 PASS | 未执行 | `S-10.txt` | 未执行 |
| S-11 | 执行超时与进程终止 | `verify_isolation.py`（无限循环用例） | `无限循环被超时终止` 为 PASS | 未执行 | `S-11.txt` | 未执行 |
| S-12 | stdout/stderr 输出截断 64KB | `verify_isolation.py --output-limit 32768 --output-total-limit 65536` | `stdout 输出被截断` 与 `stderr 输出被截断` 均为 PASS，各自实际字节数须 **接近且不超过** 32868；`stdout+stderr 合计输出限制（同一任务）` 为 PASS（两通道都接近单流上限、合计接近且 ≤ 65636） | 未执行 | `S-12.txt` | 未执行 |
| S-13 | 任务完成后容器清理 | 在**执行节点**运行 `verify_isolation.py ... --on-execution-node --confirm-manager-docker-same-host --docker-check local`；`docker ps -aq --filter label=zd.sandbox=1` | 输出为空；`任务结束后无残留容器` 为 PASS；未人工确认节点身份或 Docker CLI 不属于执行节点时为 SKIP（结论 INCOMPLETE） | 未执行 | `S-13.txt` | 未执行 |
| S-14 | 并发与队列限制（2 并发 / 8 排队） | 并行提交 16 个 `time.sleep(5)` 任务：`seq 16 \| xargs -P16 -I{} curl ... /v1/jobs`；随后 `docker ps` | 至少 1 个 HTTP 429 `queue_full`；接受数 ≤ 10；无残留容器 | 未执行 | `S-14.txt` | 未执行 |
| S-15 | HTTPS / mTLS 身份认证与证书错误处理 | 见 §5.1；或 `verify_isolation.py ... --client-cert ... --client-key ... --expect-mtls --invalid-client-cert ... --invalid-client-key ...` | 合法证书 200；无客户端证书 / 错误证书 / 不受信服务端证书均被拒绝；错误令牌 401；整体退出码 0 或 2（含 SKIP 时不得视为通过）。本地临时 TLS 单元测试（含“证书与私钥不匹配初始化失败”）仅证明客户端逻辑，**不能替代本节实机结论** | 未执行 | `S-15.txt` | 未执行 |

状态填写规则：

- **未执行**：尚未在真实节点运行（当前默认值）。
- **通过**：命令输出与预期完全一致，且证据文件已保存。
- **失败**：输出与预期不符；必须记录差异并修复后重跑，不能改预期迁就现状。
- **阻塞**：缺少节点 / Docker / 证书 / 网络条件，需负责人提供环境。

> 仅凭 `docker inspect` 的配置字段不能证明内核已强制执行（尤其 seccomp / AppArmor）。
> 必须同时有 `verify_isolation.py` 的实际运行输出或独立的攻击脚本证据。

## 18. 验收证据保存

```bash
STAMP=$(date +%Y%m%d-%H%M)
EVID=/var/log/zd-sandbox-acceptance/$STAMP
sudo mkdir -p "$EVID"

# 示例：保存 S-01 的脚本输出（其余项同理，改文件名）
./venv/bin/python sandbox_manager/scripts/verify_isolation.py \
  --url "$BASE" --token "$TOKEN" --ca "$CA" \
  --on-execution-node --confirm-manager-docker-same-host --docker-check local \
  --lan-host 10.0.0.5 --lan-port 3306 \
  --backend-host 10.0.0.10 --backend-port 8000 \
  --host-file /tmp/zd_host_probe.txt \
  2>&1 | sudo tee "$EVID/S-01.txt"

# 保存管理器日志片段
sudo journalctl -u zd-sandbox --since "1 hour ago" --no-pager | sudo tee "$EVID/manager-journal.txt"

# 保存版本与环境信息
{ docker version; docker info --format '{{json .SecurityOptions}}'; uname -a; } \
  2>&1 | sudo tee "$EVID/environment.txt"
```

要求：

- 证据文件保存在执行节点的 `/var/log/zd-sandbox-acceptance/`，**不要提交到 Git**。
- 证据中不得包含真实令牌、证书私钥、服务器密码或真实用户数据；令牌在粘贴前替换为 `<redacted>`。
- `TEST_REPORT.md` 只记录汇总结论、执行日期、节点版本和证据文件路径，不复制敏感内容。
- 每项验收完成后，同步更新 §17 的“实际结果 / 证据保存位置 / 状态”三列。

---

## 19. 验收判定细节补充（2026-11-13）

### 19.1 mTLS 与 TLS 1.3 的判定语义

服务端配置 `ZD_SANDBOX_TLS_CLIENT_CA` 后会以 `CERT_REQUIRED` 校验客户端证书。
在 **TLS 1.3** 下，服务端的拒绝告警在客户端握手完成之后才到达，客户端看到的往往是
`http.client.RemoteDisconnected` / 连接被重置，而不是 `ssl.SSLError`。

因此 `verify_isolation.py` 的判定规则是：

- **算作拒绝**：明确的 `SSLError`，或“TLS 已建立但服务端关闭连接、未返回任何 HTTP 响应字节”。
- **不算作拒绝**：DNS 解析失败（`gaierror`）、`ConnectionRefused`、超时、证书/私钥配置错误、
  以及其他未知异常。
- 负向结论只有在**同一客户端证书的正向请求返回 200** 时才可归因；正向失败时负向结果判 FAIL。

不要用 `openssl s_client` 的“握手完成”来判断 mTLS 未生效——请以实际 HTTP 响应是否返回为准。

### 19.2 输出截断与日志轮转

容器日志驱动仍保留 `max-size=64k / max-file=1` 作为磁盘上限。但**不能依赖 json-file
读取学生输出**：5MB 级突发会把日志反复轮转覆盖（实测可只剩几十字节）。

管理器改为在容器启动前建立 `attach` 流，用有界缓冲实时读取 stdout/stderr：

- 每流最多保留 `output_bytes/2`，超出部分继续读走但不保留（避免容器写入阻塞）；
- 总输出不超过 `output_bytes`；
- 仅在 attach 失败时才回退到 json-file 读取。

因此 S-12 的验收标准是：**实际返回字节数应接近单流上限**，而不是“非空且不超上限”。

### 19.2.1 输出采集失败（`output_capture_failed`）

当 attach 读取**已获得部分数据后中断**、读取线程在限期内未退出，或日志回退本身失败时，
管理器返回 `output_capture_failed`，任务不标记为成功，容器仍会被强制回收：

- **不得**把部分输出当作完整结果返回；
- 只有“未读到任何数据”才允许回退 `docker logs`；
- 回退日志仍受 stdout/stderr 各自字节上限约束。

排查该错误时先看管理器日志中的 attach 异常类型与容器是否已回收，不要直接放宽输出限制。


### 19.3 WSL2 环境部署（仅用于准备与本地复验）

本项目曾在本机 WSL2 完成一次实跑，命令与生产节点一致，但请注意：

- 镜像可本地构建并以 `sha256:<image-id>` 固定（`image_verify.py` 支持本地 Image ID）；
- WSL2 **没有 AppArmor**，必须将 `ZD_SANDBOX_APPARMOR` 留空；
- WSL2 不是独立生产节点，其结果**不得**作为生产安全验收结论。
