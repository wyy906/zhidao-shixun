# 生产就绪评估（M4）

> 本文件记录的是**生产化准备**与**WSL2 本机可验证部分**的真实结果。
> 本机没有独立 Linux 生产节点、没有正式镜像 Registry、WSL2 无 AppArmor/gVisor、
> 没有生产网络拓扑，因此**不能把本文任何结论当作生产验收通过**。
> 生产验收必须以独立节点 + 正式 digest 重新执行本文第 5、6 节。

- 评估日期：2026-11-13
- 分支：`trae-dev`
- 节点：WSL2 Ubuntu 24.04（kernel 6.18.58.1-microsoft-standard-WSL2），Docker Engine 29.1.3
- 管理器：`zd-sandbox` 服务，`127.0.0.1:8443` mTLS，实例 ID `wsl-ubuntu2404-node1`
- 镜像：本地构建并固定为本地 Image ID `sha256:f6ce001f…`（**不是** Registry digest）

## 1. 结论摘要

| 项目 | 结果 | 性质 |
|---|---|---|
| 生产预检脚本 `production_preflight.sh` | PASS=20 / FAIL=1 / BLOCK=0（退出码 1） | 本机实测 |
| 多实例隔离（实例 A + 实例 B） | PASS=10 / FAIL=0 | 本机实测 |
| Docker 不可用 fail-closed | 退出码 3，端口未提供服务 | 本机实测 |
| Docker 停止 → 管理器联动停止 | 停止传播生效，端口关闭 | 本机实测 |
| Docker 重启 → 管理器联动恢复 | `PartOf=docker.service` 生效（PASS=7/FAIL=0） | 本机实测 |
| AppArmor | FAIL（WSL2 内核不提供） | **生产阻塞项** |
| 正式 Registry digest | 未具备（仅本地 image id） | **生产阻塞项** |
| gVisor / runsc | 未安装（可选增强） | 生产建议项 |
| 独立 Linux 生产节点验收 | 未执行 | **生产阻塞项** |
| 生产网络拓扑 / 防火墙 / 监控 | 未具备 | **生产阻塞项** |

**结论：生产化准备已完成，生产验收未通过。**

## 2. 生产拓扑（目标形态）

```
[学生/教师浏览器] → [业务后端 business-server :8000]
                              │  内网 mTLS（客户端证书 + 服务端 CA 校验）
                              ▼
                    [执行节点 execution-node :8443]
                              │  仅 zd-sandbox 账号可读 Docker Socket
                              ▼
                    [Docker Engine] → 一次性容器（network=none）
```

硬性要求：

1. **业务服务器与执行节点分离**，执行节点不承载业务、不存数据库、不放学生数据。
2. 8443 **只允许业务后端所在 IP 访问**；禁止对学生网段、桌面端或公网开放。
3. 生产必须 HTTPS + 双向 TLS；`ZD_SANDBOX_ALLOW_INSECURE_HTTP=true` 只允许回环开发。
4. 镜像必须固定到 `repo@sha256:<digest>`；本地 `sha256:<image-id>` 仅限本机验证。
5. Docker Socket 只授予 `zd-sandbox` 服务账号，绝不挂载进学生代码容器。
6. 执行节点开启 AppArmor（并配置 profile）；建议叠加 gVisor/runsc。

## 3. 生产前置条件清单

| 编号 | 条件 | 当前状态 |
|---|---|---|
| P-01 | 独立 x86_64 Linux 节点（Ubuntu 22.04/24.04） | 未具备（仅 WSL2） |
| P-02 | cgroup v2 + Docker cgroup driver=systemd | WSL2 PASS，生产待复核 |
| P-03 | AppArmor 启用 | **FAIL（WSL2 不可用）** |
| P-04 | 镜像推送 Registry 并取得 `repo@sha256:` digest | 未具备 |
| P-05 | 内网 CA、服务端证书、客户端证书、私钥 600/640 | WSL2 自签 PASS，生产待签发 |
| P-06 | 防火墙仅放行后端 → 8443 | 未配置 |
| P-07 | `ZD_SANDBOX_INSTANCE_ID` 显式且唯一 | WSL2 PASS |
| P-08 | 专用非 root 账号 `zd-sandbox` + docker 组 | WSL2 PASS |
| P-09 | systemd 加固（NoNewPrivileges/ProtectSystem 等） | WSL2 PASS |
| P-10 | Docker 数据目录剩余 ≥ 10GB | WSL2 PASS（951GB） |
| P-11 | 备份/回滚策略与镜像 digest 升级流程 | 文档见第 6 节，未演练 |
| P-12 | 监控与告警（health、残留容器、磁盘） | 未具备 |

## 4. 本轮实测证据（WSL2 本机）

### 4.1 生产预检

命令（root）：

```bash
bash sandbox_manager/scripts/production_preflight.sh
```

结果：`PASS=20 FAIL=1 BLOCK=0`，退出码 `1`。

- 唯一 FAIL：`AppArmor 未启用（生产建议启用并配置 profile）` —— WSL2 内核不提供 AppArmor，
  属预期阻塞，不是脚本误判。
- 其余关键项 PASS：cgroup v2、Docker 29.1.3、socket、manager.env 640、
  令牌长度 ≥32、镜像引用已固定、证书与私钥权限、客户端 CA、实例标识、服务账号、
  systemd NoNewPrivileges、磁盘余量、无残留容器。
- 说明：预检把「本地 `sha256:<image-id>`」判为 PASS，因为脚本按代码约定校验固定引用；
  **生产上线另需 Registry digest，见 P-04**。

### 4.2 多实例隔离

在同一节点同时运行两个管理器实例：

| 实例 | 端口 | `ZD_SANDBOX_INSTANCE_ID` |
|---|---|---|
| A | 8443 | `wsl-ubuntu2404-node1`（systemd 服务） |
| B | 8543 | `wsl-ubuntu2404-node2`（临时进程，验证后已停止） |

结果：`PASS=10 FAIL=0`。

1. A、B `/health` 均 `ok`。
2. 两个实例并发提交任务，均 `succeeded`（A：`print`，B：`sys.version_info`）。
3. 人为创建两个带标签的假残留容器（分别属于 A、B 的实例标签）。
4. 重启实例 B 后：
   - **A 标签容器未被删除**（`zd.sandbox.instance` 过滤生效，无跨实例误删）；
   - **B 标签容器被 B 启动清理删除**；
   - A 仍然健康。
5. 验证结束后 B 进程、假容器均已清理，无残留。

结论：多实例必须显式配置互不相同的 `ZD_SANDBOX_INSTANCE_ID`；启动清理只影响本实例。

### 4.3 故障注入：Docker 不可用（fail-closed）

将 `ZD_SANDBOX_DOCKER_HOST` 指向不存在的 socket 后启动管理器：

- 进程**非 0 退出（退出码 3）**，不会进入可服务状态；
- 日志：`RuntimeError: sandbox startup cleanup failed: docker_unavailable`；
- 对 8544 的 `/health` 请求失败（端口未提供服务）；
- 日志中未出现 `token/secret/password` 字样。

结论：Docker 异常时管理器拒绝启动，符合 fail-closed 设计，不存在“带未知残留继续服务”的路径。

### 4.4 故障注入：停止 Docker Engine

`systemctl stop docker.socket docker.service` 后：

- `zd-sandbox` 变为 `inactive`（`Requires=docker.service` 传播停止）；
- 8443 无监听，无管理器进程。

恢复时确认了一个**运维行为**：

- **启动 Docker 不会自动启动 `zd-sandbox`**（`Requires=` 只传播停止，不传播启动）；
- 需显式 `systemctl start zd-sandbox`，之后 `/health` 恢复 `ok`，残留容器数 0。

### 4.5 Docker 重启联动恢复（本轮新增）

单元新增 `PartOf=docker.service` 后实测（`PASS=7 FAIL=0`）：

1. 更新单元并 `daemon-reload`，重启管理器后 `/health` 正常。
2. `systemctl restart docker.service` → **`zd-sandbox` 自动恢复运行**，`/health` 正常。
3. `systemctl stop docker.socket docker.service` → 管理器联动停止。
4. `systemctl start docker.socket docker.service` → 管理器**不会自动启动**
   （systemd 依赖只传播停止/重启，不传播启动），手动启动后 `/health` 正常、残留容器 0。

> 运维要求：Docker 完整停止后再启动时，必须显式 `systemctl start zd-sandbox`；
> 建议把它写入同一运维脚本/Ansible 任务，并纳入监控告警。

## 5. 生产部署与验收流程

1. 按 `SANDBOX_DEPLOYMENT.md` 第 2~5 节安装 Docker、创建 `zd-sandbox`、部署管理器。
2. 构建镜像并推送到内部 Registry，记录 `repo@sha256:<digest>`，写入 `manager.env`。
3. 运行 `production_preflight.sh`，**必须 FAIL=0**；AppArmor、digest 任一 FAIL 不得上线。
4. 执行 `sandbox_manager/scripts/verify_isolation.py` 全量 S-01~S-15，要求 FAIL=0、SKIP=0。
5. 执行业务后端到执行节点的 mTLS 联通与错误令牌 401 验证。
6. 逐个执行本文第 4.2~4.4 的隔离与故障注入，结果存档。
7. 保存证据（命令、输出、时间、节点指纹），归档到验收目录。

### 上线门槛（全部满足才可称“生产就绪”）

- [ ] 独立 Linux 节点 + 本文第 3 节 P-01~P-12 全部具备
- [ ] `production_preflight.sh` FAIL=0（含 AppArmor、Registry digest）
- [ ] `verify_isolation.py` FAIL=0、SKIP=0
- [ ] 多实例隔离与故障注入在**生产节点**复测通过
- [ ] 防火墙、监控、备份与回滚演练完成

## 6. 运行手册（Runbook）

### 启动 / 停止

```bash
systemctl start zd-sandbox    # 需 Docker 已运行
systemctl stop zd-sandbox
systemctl status zd-sandbox --no-pager
journalctl -u zd-sandbox -n 100 --no-pager
```

### 健康检查

```bash
curl -sS --cacert ca.crt --cert client.crt --key client.key \
  -H "X-Sandbox-Token: $ZD_SANDBOX_TOKEN" \
  https://<exec-node>:8443/health
```

预期 `{"status":"ok", ...}`；返回 503 表示 Docker/镜像/运行时不可用，业务后端会拒绝执行代码。

### 镜像 digest 升级

1. 构建并推送新镜像，取得新 `repo@sha256:`。
2. 更新 `/etc/zd-sandbox/manager.env` 的 `ZD_SANDBOX_IMAGE`。
3. `systemctl restart zd-sandbox`；确认 `/health` 正常且 `docker ps -a --filter label=zd.sandbox=1` 为空。
4. 回滚：改回旧 digest 并重启。

### 故障处置

| 现象 | 处理 |
|---|---|
| `/health` 503 `docker_unavailable` | 检查 Docker 与 socket；修复后重启 `zd-sandbox` |
| `/health` 503 镜像相关 | 确认 digest 镜像已拉取、引用与本地一致 |
| 启动即退出（exit 3） | 查看 journal，多为清理失败或 Docker 不可用，**不要绕过** |
| 残留容器 | `docker ps -a --filter label=zd.sandbox=1`；确认属于本实例后再清理 |
| Docker 重启后业务不可用 | 手动 `systemctl start zd-sandbox`（见 4.4） |

## 7. 已验证 / 未验证边界

**已在 WSL2 本机验证：**

- 启动清理的实例标签隔离（无跨实例误删）
- 多实例并发执行
- Docker 不可用时 fail-closed
- Docker 停止的联动行为与恢复步骤
- Docker 重启的管理器联动恢复（`PartOf=docker.service`）
- systemd 加固项、证书权限、令牌长度、磁盘余量、无残留

**未验证 / 阻塞：**

- AppArmor / gVisor 实际生效（WSL2 不支持，生产必须补）
- 正式 Registry digest 与拉取链路
- 独立 Linux 节点上的 S-01~S-15 全量验收
- 生产防火墙、跨机 mTLS、网络拓扑
- 长稳压测、故障恢复演练、监控告警
- WSL2 存在 localhost 转发限制（NAT 模式），与生产无关，仅记录为环境特性

## 8. 本次新增工具

- `sandbox_manager/scripts/production_preflight.sh`：只读生产预检，root 运行，
  不输出任何密钥；退出码 `0=全部 PASS / 1=存在 FAIL / 2=无 FAIL 但有 BLOCK`。
