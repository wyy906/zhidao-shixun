# 更新记录

## 2026-11-12 — 阶段 3-A 第三轮 P1 修复

### 修复

- **队列上限**：`sandbox_manager/jobs.py` 改用固定线程池，新增 `max_pending`
  （默认 `4 × max_concurrent`，可用 `ZD_SANDBOX_MAX_PENDING` 配置）；
  超限返回稳定 `queue_full`（HTTP 429），被拒绝的请求不创建任务、不启动容器。
- **传输安全**：业务后端强制非回环地址使用 HTTPS；明文 HTTP 仅允许显式开启
  `SANDBOX_ALLOW_INSECURE_HTTP` 且目标为回环地址；`client_cert` / `client_key`
  必须成对，缺失时启动失败；任何情况下不关闭证书校验。
- **错误脱敏**：管理器不再向接口返回 Docker 错误 / 镜像地址 / 宿主机路径，
  仅写服务端日志；学生任务查询返回固定安全文案，教师经权限检查可查看内部诊断。
- **`/dev/shm`**：显式设置为 8MB，并在 Docker 实际 `HostConfig.ShmSize` 中回查。
- **安全配置回查**：新增 seccomp / AppArmor 选项、`CapAdd` 为空、`Init=true`、
  `ShmSize` 校验；任一项不匹配即删除容器并拒绝执行。
- **异步与并发保护**：`/code/run` 改为异步路由 + `httpx.AsyncClient`；
  连接/读取超时与连接池上限；后端全局与每用户并发上限（429），避免请求堆积。
- **异常收口**：畸形响应、轮询异常、保存失败统一落到安全终态并尽力取消沙箱任务，
  不再静默留下永久 `running` 任务。

### 测试

- 后端 pytest：75 → **97 项**。
- 沙箱管理器：80 → **93 项**（新增队列上限、shm、seccomp/AppArmor 回查、脱敏测试）。
- 前端 `npm test`：通过。
- 真实 Linux / Docker 实机验证（队列压测、shm 挂载、seccomp/AppArmor 内核生效、
  异步并发压测）**仍未执行**，不得视为已验收。

## 2026-11-12 — 阶段 3-A 第二轮审查补充修复

### 修复

- **启动清理失败阻断服务**：`sandbox_manager/server.py` 的 lifespan 在
  `cleanup_stale_containers()` 失败时抛 `RuntimeError`，进程拒绝启动，
  不会带着未知残留容器继续接受任务。
- **清理范围收紧**：容器增加 `zd.sandbox.instance` 与 `zd.sandbox.job` 标签；
  启动清理只删除本实例遗留容器，其他实例 / 无实例标签 / 其他服务的容器不会被误删。
  单节点推荐单实例；多实例必须配置不同 `ZD_SANDBOX_INSTANCE_ID`。
- **输出限制完善**：日志改为流式读取，达到上限立即停止并关闭流；
  stdout / stderr 各自上限 32KB，Docker 日志存储总量 64KB（`max-size=64k, max-file=1`），
  不再先读取无限量日志再截断。
- **数据库初始化方案**：新增 `DB_AUTO_CREATE` 策略。开发环境默认 `create_all`；
  生产环境（或 `DB_AUTO_CREATE=false`）缺表时拒绝启动并提示 `alembic upgrade head`，
  不再依赖 `create_all` 替代正式迁移。

### 测试

- 后端 pytest：70 → **75 项**（新增数据库初始化 5 项）。
- 沙箱管理器：71 → **80 项**（新增启动阻断、清理范围、输出限额等）。
- 前端 `npm test`：通过。
- 真实 Linux 节点验证（Docker 清理、日志轮转、TLS、隔离）**仍未执行**，不得视为已验收。

## 2026-11-12 — 阶段 3-A 安全审查问题修复

### 修复

- **镜像 digest 校验**：新增 `sandbox_manager/image_verify.py`，区分 Registry Manifest Digest
  与本地 Image ID。Registry 引用改为校验 `RepoDigests`，本地 ID 校验完全相等；
  镜像被替换、摘要错误、RepoDigests 缺失时返回 `image_digest_mismatch` 并拒绝执行。
- **生产强制 HTTPS**：`ManagerConfig.validate` 要求证书与私钥成对且可读；双向 TLS 缺 CA/证书
  拒绝启动；明文 HTTP 仅允许显式 `ZD_SANDBOX_ALLOW_INSECURE_HTTP=true` + 回环地址。
  `build_uvicorn_kwargs` 不存在证书失败后降级为 HTTP 的路径。
- **容器安全配置回查**：`verify_container_security` 改为检查完整 `Config + HostConfig`，
  新增运行用户、tmpfs 容量与 `noexec/nosuid/nodev`、日志驱动与轮转上限、端口映射、
  设备/挂载、运行时与镜像；任一不符立即删除容器并拒绝执行。
- **部署边界**：systemd 单元增加加固项与网络暴露要求；部署文档明确独立节点、
  Docker Socket 不进入学生容器、管理接口只允许业务后端访问。
- **残留容器清理**：管理器启动时删除所有 `zd.sandbox=1` 标签容器。
- **数据库迁移**：新增 `backend/alembic.ini`、`env.py` 与 `20261112_0001_add_code_tasks.py`。
- **请求字段收紧**：业务端与管理器请求模型 `extra="forbid"`，学生不能传镜像/网络/资源参数。
- **错误信息**：管理接口错误只返回错误码，不回显令牌或宿主机路径。

### 测试

- 后端 pytest：67 → **70 项**（新增额外字段、代码不落库、`code_tasks` 迁移）。
- 沙箱管理器：35 → **71 项**（新增镜像校验、TLS 配置、容器配置回查、FakeDocker 生命周期）。
- 前端 `npm test`：通过。
- 真实 Linux 节点的网络/文件隔离、TLS 握手、残留容器清理**仍未验证**，不得视为已验收。

## 2026-11-12 — 阶段 1：建立现有项目代码基线

提交：`3032872` `feat: import existing project code baseline`（111 files, +11389）

### 新增（代码基线）

- 迁入 `backend/`（FastAPI + SQLAlchemy，42 文件）、`frontend/`（Vue 3 + TS，24 文件）、
  `desktop/`（PySide6 桌面助手，18 文件）、`scripts/`（16 文件）、`experiment_packs/`（1 个实验包）。
- 新增 `demo_shots/`（6 张产品界面截图，已逐张核查无隐私信息）。
- 新增 `docs/README.md` 与 `docs/visual_result.json`（纯文本，不含个人桌面截图）。

### 安全修复

- **删除 5 个脚本中硬编码的真实 NVIDIA API Key**（`check_nv_models.py`、`test_model_access.py`、
  `test_model_compare.py`、`test_visual_api.py`、`test_nv_vl.py`），改为读取环境变量 `NV_API_KEY`；
  未设置时给出明确提示并退出。
- 清理 4 个脚本中的个人绝对路径 `c:/Users/wyy/Desktop/sxzd/backend`，改为基于
  `Path(__file__).resolve().parent.parent` 的相对路径。
- 扩充 `.gitignore`：新增 `ai_review/`、`.screenshots/`、`docs/*.png`、`*.tsbuildinfo`、
  `frontend/vite.config.js`、`frontend/vite.config.d.ts`。
- 未入库：`*.env` 真实配置、`*.db`/`*.sqlite`、`*.log`、`node_modules`、`dist`、`ai_review/`（329 MB，保留本地）。

### 配置与文档

- 重写 `backend/.env.example`：补充 `ADMIN_USERNAME` / `ADMIN_PASSWORD` / `ALLOW_PUBLIC_REGISTER`，
  密钥项全部为占位值，并注明生产环境必须替换 `JWT_SECRET_KEY`。
- 重写 `README.md`：架构、技术栈、目录结构、三端安装启动、环境变量表、默认账号、
  接口清单、测试现状、安全说明、Windows 平台限制。

### 缺陷修复

- `scripts/start-backend.ps1`、`scripts/start-frontend.ps1` 的 `Set-Location` 少一级目录
  （指向不存在的 `scripts\backend`），已改为 `..\backend` / `..\frontend`。

### 验证（全部为实际执行）

- 后端：干净 venv + 全新目录（无 `.env`、无数据库）启动成功，`/health` ok、23 条路由、
  首次建库建管理员、`admin` 登录 200、无 token 访问 401。
- 前端：全新目录 `npm ci`（115 packages）+ `vue-tsc --noEmit` 退出码 0。
- 桌面端：独立 venv 安装 PySide6 6.12.0 等依赖，离屏导入 6 个模块通过（GUI 未实跑）。
- 推送前扫描：暂存内容敏感信息 0 命中；无 `.env`/`*.db`/`*.log`/`node_modules`/`dist`。

### 未做（按约束）

- 未修改 `main` 分支，未合并协作文档。
- 未删除 `C:\Users\wyy\Desktop\sxzd` 与 `ai_review/`。
- 未使用 `git push --force`。
- 未大规模重构业务代码，未删除任何已有功能。

## 2026-11-12 — 阶段 0：项目接入与现状盘点

### 接入

- 成功 clone `https://github.com/wyy906/zhidao-shixun.git` 到工作区
  `c:\Users\wyy\Desktop\GitHub-chatgpt-tare`，检出并跟踪 `trae-dev` 分支。
- 确认远程仓库现状：`main`（`11698fa`）仅含 `README.md`；`trae-dev`（`adfa581`）含 9 份协作文档；
  **两个分支均无任何业务代码**。

### 盘点

- 确认真实项目位于 `C:\Users\wyy\Desktop\sxzd`，该目录**未初始化 Git**、无远程、无提交历史。
- 核实技术栈：后端 FastAPI + SQLAlchemy + SQLite；前端 Vue 3 + TS + Vite 4 + Element Plus；
  桌面端 PySide6 + IUIAutomation + mss/WGC（仅 Windows）。
- 核实功能范围：鉴权、实验 CRUD 与 JSON 导入、分步进度、实验报告、AI 屏幕指导（关键词快路径 +
  多模态视觉兜底）、透明悬浮层标注、在线 Python 运行（无沙箱）、教师数据分析。
- 风险扫描：发现 `backend/.env` 与 `ai_review/backend/.env` 两份含真实 `AI_API_KEY`/`JWT_SECRET_KEY`
  的副本，以及 3 份真实 SQLite 数据库与若干日志、`node_modules`(310.6 MB)、`dist`(6.8 MB)、
  `docs` 图片(10.9 MB)；这些均未进入远程仓库，无泄露。

### 验证

- 后端实启成功：`/health` 返回 ok，OpenAPI 23 条路由（使用临时数据库，未污染原库）。
- 前端类型检查通过：`vue-tsc --noEmit` 退出码 0。
- 桌面端仅做离屏导入验证通过；GUI 与悬浮层未实际运行。
- 确认项目**无任何自动化测试**（无 pytest / vitest 配置与用例）。

### 文档

- 更新 `TASK_BOARD.md`：勾选 P0 检查项并附证据，新增 3 项阻塞（B-01 代码迁入、B-02 敏感文件清理、B-03 main/trae-dev 合并节奏）。
- 重写 `TEST_REPORT.md`：记录 T-01 ~ T-08 共 8 项实测结果（含未执行项说明）。
- 重写 `NEXT_STEPS.md`：给出待确认决策与下一阶段可验收任务。
- 本条记录写入 `CHANGELOG.md`。

### 未做（按约束）

- 未改动任何业务代码，未删除任何文件。
- 未初始化 `sxzd` 为 Git 仓库，未把本地代码推送到远程。
- 未对 `main` 做任何操作。
- 未提交任何 `.env`、密钥、数据库或用户数据。

## 2026-11-12（初始化）

- 初始化 GitHub 与 Trae 协作开发分支。
- 建立项目上下文、任务看板、测试报告、决策记录和后续步骤文档。
- 尚未确认本地业务代码是否已推送到仓库。
