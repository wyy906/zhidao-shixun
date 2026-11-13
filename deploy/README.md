# 生产上线交付包（M5）

> 状态：**交付物已完成并通过本地验证，尚未在真实生产服务器部署**。
> 本目录所有模板（systemd / nginx / 环境变量）在真实 Linux 服务器上的安装步骤
> 尚未执行过，上线时按本清单逐项执行并记录实际结果。

## 1. 交付物清单

| 文件 | 用途 | 本地验证 |
|---|---|---|
| `backend/backend.env.production.example` | 生产环境变量模板 | 内容评审；真实填写需在生产机完成 |
| `deploy/backend/zd-backend.service` | 业务后端 systemd 加固单元 | 未在真实服务器安装（模板） |
| `deploy/nginx/zd-backend.conf.example` | nginx TLS 反向代理模板 | 未在真实服务器安装（模板） |
| `scripts/backend_preflight.py` | 生产配置预检（只读、不回显密钥） | 已实测 + 11 项单测 |
| `backend/alembic/versions/20261113_0000_baseline.py` | 基线迁移（核心表） | 干净库 / 历史库两场景实测通过 |
| `SANDBOX_DEPLOYMENT.md` + `PRODUCTION_READINESS.md` | 执行节点部署与生产就绪 | M4 已记录 |

## 2. 本轮已修复的上线阻塞项

1. **迁移链缺基线**（原为阻塞）：`alembic upgrade head` 在干净库只建 `code_tasks`，
   生产模式（`DB_AUTO_CREATE` 为空/false）下应用会因缺 `users` 等表拒绝启动。
   已新增基线迁移 `20261113_0000`，迁移链变为
   `20261113_0000（核心表）→ 20261112_0001（code_tasks）`。
   验证：干净库建出全部 7 张表且 `alembic_version=20261112_0001`；
   `create_all` 历史库幂等通过。
2. **alembic.ini 非 ASCII**（原为阻塞）：Alembic 用 locale 编码读取 alembic.ini，
   中文注释在 GBK locale（Windows zh-CN）下直接 `UnicodeDecodeError`。
   已改为纯 ASCII 并加注释说明。

## 3. 上线流程（业务服务器，需负责人执行）

1. 安装 Python 3.13 + venv，部署代码到 `/opt/zd-backend`，
   `pip install -r backend/requirements.txt` 到 `/opt/zd-backend/.venv`。
2. `cp deploy/backend/backend.env.production.example /etc/zd-backend/backend.env`，
   填写真实值，`chmod 600`，属主 `zd-backend`。
3. **配置预检**（只读，不回显密钥）：
   ```bash
   python scripts/backend_preflight.py --env-file /etc/zd-backend/backend.env
   ```
   退出码 `0=可上线；1=存在 FAIL 必须修复；2=仅 WARN，需负责人确认接受`。
4. **数据库迁移**：
   ```bash
   cd /opt/zd-backend/backend && .venv/bin/python -m alembic upgrade head
   ```
   （PostgreSQL 需先建库建账号；alembic.ini 保持 ASCII，勿加中文注释。）
5. 安装 `deploy/backend/zd-backend.service` → `systemctl daemon-reload`。
6. 安装 `deploy/nginx/zd-backend.conf.example` → `nginx -t` → reload。
7. **执行节点**：按 `SANDBOX_DEPLOYMENT.md` + `PRODUCTION_READINESS.md` 第 5 节部署，
   通过后回填 `backend.env` 的 `CODE_EXECUTION_ENABLED=true` 与沙箱配置。
8. 健康验证：`curl -s https://<域名>/health`（nginx 模板中 /health 默认限内网）。

## 4. 运维（备份 / 回滚 / 监控）

- **备份**：PostgreSQL `pg_dump` 每日定时；SQLite 场景先停服务再拷贝库文件。
  保留策略与异地存储由负责人确定（未演练）。
- **回滚**：代码回滚 = 部署上一个版本 + `alembic downgrade` 到对应 revision
  （当前链仅 2 个迁移，downgrade 需先在测试库演练）。
- **监控**：`/health`（业务后端）、执行节点 `/health`、`journalctl -u zd-backend`、
  `docker ps -a --filter label=zd.sandbox=1` 残留检查。告警通道未配置。

## 5. 上线门槛（全部满足才能宣布上线）

- [ ] 业务服务器配置预检 FAIL=0（WARN 项经负责人确认）
- [ ] 干净库执行 `alembic upgrade head` 成功且应用可登录
- [ ] systemd + nginx 安装完成，HTTPS 访问正常，`/health` 返回 ok
- [ ] 执行节点上线并通过 `PRODUCTION_READINESS.md` 全部门槛（AppArmor、Registry digest 等）
- [ ] `CODE_EXECUTION_ENABLED=true` 后学生代码端到端可运行
- [ ] 备份与回滚演练各执行一次并留证据
- [ ] 监控告警接通

## 6. 诚实边界

- `backend_preflight.py` 对当前开发机 `backend/.env` 实测 `PASS=4 FAIL=7 WARN=2` ——
  开发配置**应当**不通过生产预检，这是脚本的正确行为，不是缺陷。
- systemd / nginx 模板**未在真实 Linux 服务器安装验证**，首次上线时按 §3 逐项执行。
- 备份、回滚、监控均为文档描述，**未演练**。
