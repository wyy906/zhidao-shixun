# 测试报告

> 本文件记录「智导实训」的测试基线与历次实测结果。**第 1~7 章为当前状态**，
> 第 8 章为历史演进记录（仅用于追溯，不代表当前状态）。

---

## 1. 当前基线

| 项 | 值 |
|---|---|
| 日期 | 2026-11-12 |
| 分支 | `trae-dev` |
| 仓库内容 | **已包含业务代码**：`backend/`、`frontend/`、`desktop/`、`scripts/`、`experiment_packs/`、`demo_shots/`、`docs/`、`sandbox_manager/` |
| 后端测试 | **70 项，全部通过**（`backend/tests/`） |
| 沙箱管理器测试 | **71 项，全部通过**（`sandbox_manager/tests/`） |
| 前端测试 | **通过**（`npm test` → vue-tsc，退出码 0） |
| 数据库 | 测试使用临时 SQLite，**不接触真实库** |
| 真实 `.env` | 测试**不读取**（`ZD_ENV_FILE` 指向不存在的临时文件） |
| 代码执行 | 已改为「业务后端 + 独立 Linux 执行节点 + 一次性 Docker 容器」架构；**真实隔离尚未在 Linux 节点验证** |
| 操作系统 | Windows 10/11，Python 3.13.14，Node v26.13.0 |

## 2. 结论摘要

1. 后端 70 项自动化测试全部通过，覆盖鉴权、实验 CRUD 与导入、进度、报告、配置隔离、代码沙箱接口、`code_tasks` 迁移。
2. 沙箱管理器 71 项单元测试全部通过，覆盖容器安全参数（含创建后完整回查）、固定镜像 digest 校验、
   生产 HTTPS / 双向 TLS 启动约束、管理接口认证、输入校验、超时上限、取消与重启语义。
3. 学生代码**已不在业务后端进程内执行**，也不再作为本机 subprocess 运行；沙箱不可用时一律 503，不存在降级路径。
4. 测试在**无网络、无真实 AI Key、无真实数据库、无真实 `.env`、无 Docker** 的条件下可重复运行。
5. 测试过程中发现 8 个问题：**2 个已修复**，**6 个待负责人决策**；1 项（桌面端 GUI）**尚未验证**。
6. **代码执行的真实隔离能力（网络/文件/资源/容器清理）本机无法验证**，必须由负责人在 Linux 执行节点运行
   `sandbox_manager/scripts/verify_isolation.py` 后才能称为“已验证”。

## 3. 测试环境

| 组件 | 版本 |
|---|---|
| Python | 3.13.14 |
| pytest | 8.3.4 |
| FastAPI | 0.115.6 |
| SQLAlchemy | 2.0.36 |
| httpx | 0.28.1 |
| TypeScript | 5.9.3 |
| vue-tsc | 2.2.12 |
| Docker | **本机未安装**（Windows 开发机，无 Linux 执行节点） |

测试依赖声明：`backend/requirements-dev.txt`（`-r requirements.txt` + `pytest>=8.0`）；
沙箱管理器依赖见 `sandbox_manager/requirements.txt`。

## 4. 后端自动化测试（70 项 + 71 项）

### 4.1 用例分布

| 文件 | 用例数 | 通过 | 失败 |
|---|---|---|---|
| `tests/test_auth.py` | 12 | 12 | 0 |
| `tests/test_experiments.py` | 16 | 16 | 0 |
| `tests/test_progress.py` | 11 | 11 | 0 |
| `tests/test_report.py` | 10 | 10 | 0 |
| `tests/test_config_isolation.py` | 4 | 4 | 0 |
| `tests/test_code_sandbox.py` | 16 | 16 | 0 |
| `tests/test_migration_code_tasks.py` | 1 | 1 | 0 |
| **backend 合计** | **70** | **70** | **0** |
| `sandbox_manager/tests/test_container_spec.py` | 30 | 30 | 0 |
| `sandbox_manager/tests/test_server.py` | 14 | 14 | 0 |
| `sandbox_manager/tests/test_config.py` | 7 | 7 | 0 |
| `sandbox_manager/tests/test_image_verify.py` | 7 | 7 | 0 |
| `sandbox_manager/tests/test_runner.py` | 13 | 13 | 0 |
| **管理器合计** | **71** | **71** | **0** |

### 4.2 实际执行结果

```
# backend
python -m pytest -q
70 passed, 297 warnings in 47.53s

# sandbox_manager（无 Docker 依赖，纯单元测试）
python -m pytest -q sandbox_manager/tests
71 passed, 1 warning in 0.99s
```

> warning 主要为 `datetime.utcnow()` 的 DeprecationWarning（见 D-08）及 starlette TestClient 内部弃用提示，
> 不影响结果。

### 4.3 覆盖内容

- **鉴权**：登录成功 / 密码错误 401 / 账号不存在 401 / 无 token 401 / 学生越权 403 / 教师成功；
  响应体不得出现 `hashed_password` 或 bcrypt 哈希。
- **实验**：创建、查询、修改、删除；学生越权全部 403；JSON 导入、步骤顺序与内容、
  `adapter` 提示落库、覆盖导入、覆盖后孤儿数据清理、未知 ID 404、非法载荷 422。
- **进度**：开始、查询、逐步推进、完成最后一步、提交后状态与完成时间、跨学生隔离、
  序号越界 400、未知实验 404。
- **报告**：保存、更新（不新建记录）、查询、提交、无报告提交 400、跨学生隔离、
  删除实验后报告清理、未知实验 404。
- **配置隔离**：env 文件路径指向临时不存在文件、机制生效性、缺失文件不回退真实 `.env`。
- **代码沙箱接口**（`FakeSandbox`，不触达真实管理器）：
  - 未登录 401；空代码 / 超长代码 400 且不提交任务；成功结果字段与旧格式兼容；
  - 学生传 `timeout=30` 被压紧到管理员上限 10s；资源超限 / 巨量输出映射与截断；
  - 沙箱不可用 → 503 且**代码未在业务后端执行**（标记文件不存在）；
  - 轮询期间管理器掉线 → 503 + 任务标记失败；
  - 任务查询：本人 200、其他学生 404、教师 200、未知 ID 404；
  - 服务重启清理：`queued/running` 标记失败，已完成不受影响；
  - 额外字段（`image` / `network_mode` / `memory_mb`）返回 422，学生无法覆盖资源与镜像；
  - `CodeTask` 不含代码列，学生代码不落业务库；
  - 静态检查：路由中不存在 `subprocess.run` / `sys.executable`。
- **容器安全参数**：禁网（`network_mode=none` + `network_disabled`）、非 root、`cap_drop=ALL`、
  `no-new-privileges`、只读根文件系统、独立 tmpfs（合计 ≤16MB）、内存/交换、CPU、pids、
  日志轮转上限、无挂载/无设备/无端口映射、代码仅经环境变量传入；
  容器创建后还会回查 Docker 实际生效的完整 `Config + HostConfig`
  （运行用户、tmpfs 容量与挂载选项、日志驱动与上限、端口/设备映射、资源、运行时、镜像），
  任何一项未生效都会删除容器并拒绝执行。
- **固定镜像 digest**：区分 Registry Manifest Digest 与本地 Image ID；Registry 引用校验
  `RepoDigests` 是否包含该 digest，本地 Image ID 校验完全相等；覆盖镜像被替换、缺失、
  错误摘要、tag 引用等情况。
- **管理接口**：令牌认证、错误令牌 401、配置缺失/镜像未固定 digest 拒绝启动、
  `/health` 就绪与不可用、提交/轮询/取消、超时上限压紧、空/超长代码 400、额外字段 422、
  未知任务 404、错误响应不回显令牌或宿主机路径、管理器重启后旧任务不存在。
- **启动传输安全**：生产默认必须 TLS（缺证书/证书不可读拒绝启动）；证书与私钥必须成对；
  双向 TLS 缺少 CA 或证书拒绝启动；明文 HTTP 仅允许显式 `ALLOW_INSECURE_HTTP` +
  回环地址，不存在失败后自动降级。
- **容器生命周期**（FakeDocker）：成功 / 超时 / 取消 / 启动失败 / 安全参数不符 / 清理失败，
  都会删除容器；管理器启动时清理带 `zd.sandbox=1` 标签的残留容器。

## 5. 数据库与配置隔离验证（实测输出）

三层数据库隔离：

1. `conftest.py` 在**导入 app 之前**把 `DATABASE_URL` 指向一次性临时文件；
2. 每个用例用 `tmp_path` 新建独立 SQLite 文件；
3. `app.dependency_overrides[get_db]` 替换为测试会话。

另外，`conftest.py` 在导入 app 前设置 `ZD_ENV_FILE`，使配置加载器指向**不存在**的临时 env 文件。

实测输出：

```
[env 隔离检查] 实际 env 文件: C:\Users\...\Temp\zd_shixun_test_guard_lq7vwcdy\no-such-test.env
[隔离检查] 全局 engine 实际连接: sqlite:///C:/Users/.../Temp/zd_shixun_test_guard_lq7vwcdy/guard.db
[隔离检查] 本次测试库连接: sqlite:///C:/Users/.../pytest-of-wyy/pytest-6/test_each_test_uses_isolated_s0/test.db
```

- 仓库内 `Get-ChildItem -Recurse -Filter *.db` 结果为空：**未生成、未修改任何真实数据库**。
- `TestClient` 未使用 `with`，不触发 lifespan 的建表 / 建管理员逻辑。
- 用户本地 `backend/.env` 不会被读取、不会被修改（测试只做存在性检查）。

## 6. 前端测试

| 项 | 结果 |
|---|---|
| 命令 | `npm test`（等价 `vue-tsc --noEmit`） |
| 退出码 | **0** |
| 覆盖范围 | 仅类型检查；尚未引入 Vitest 组件测试 |

> 注意：需先执行 `npm install`。否则 `npx` 会拉取最新版 TypeScript（6.x），
> 因 `baseUrl` 弃用而误报失败——这不是代码缺陷。

## 7. 问题清单

### 7.1 已修复（含回归用例）

| 编号 | 问题 | 位置 | 修复内容 |
|---|---|---|---|
| D-01 | `POST /experiments/{id}/step` 不校验步骤序号，`step_index=999` 或 `-1` 被接受并写入 `completed_steps` | `backend/app/api/v1/routers/experiments.py` `update_step_progress` | 越界返回 400；`test_step_index_out_of_range_returns_400` |
| D-02 | 对**不存在**的实验调用 `/step`、`PUT /report`、`POST /report/submit` 会创建指向不存在实验的孤儿进度行 | 同上（`_get_or_create_progress` 调用点） | 先查实验，不存在返回 404；2 项回归用例 |
| D-09 | 测试环境可能加载真实 `backend/.env`，从而读到真实 `AI_API_KEY` / `DATABASE_URL` | `backend/app/core/config.py`、`backend/tests/conftest.py` | 新增 `ZD_ENV_FILE` 环境变量；测试指向不存在的临时文件；4 项隔离用例 |

### 7.2 待负责人决策（已记录，未改代码）

| 编号 | 问题 | 影响 | 建议 |
|---|---|---|---|
| D-03 | `overwrite=False` 时同标题实验可重复导入 | 产生多个同名实验 | 按标题去重或返回 409 |
| D-04 | 没有教师查看 / 批阅学生报告的接口，`GET /{id}/report` 只返回当前登录者自己的报告 | 教师无法批阅 | 新增教师只读 / 批阅接口（新功能） |
| D-05 | 报告六个字段全为空时仍可提交成功 | 可提交空报告 | 明确「空报告」判定规则后加校验 |
| D-06 | `GET /experiments/{id}` 与 `GET /experiments/{id}/steps` 无鉴权，未登录可读 | 信息暴露 | 确认是否要求登录 |
| D-07 | 覆盖导入会删除同标题旧实验，连带删除学生进度、报告与操作记录 | 数据不可恢复 | 改为归档 / 保留历史进度 |
| D-08 | 全量使用 `datetime.utcnow()`，触发 DeprecationWarning，未来版本将移除 | 未来兼容性 | 迁移到 `datetime.now(UTC)` |

### 7.3 尚未验证

| 编号 | 项 | 说明 |
|---|---|---|
| R-06 | 桌面端 GUI / UIA / 悬浮层实际运行 | 目前仅完成离屏导入检查；需人工在 Windows 桌面点验 |
| S-01 | 沙箱容器在真实 Linux 节点的隔离效果 | 开发机为 Windows 且未安装 Docker；网络/文件/资源/清理均**未实机验证** |
| S-02 | Docker / 镜像 / 运行时故障注入 | 仅用 FakeRunner 模拟，未在真实节点停止 Docker 或替换镜像验证 |
| S-03 | gVisor / AppArmor / seccomp 实际启用 | 代码已做启动前校验，但未在启用这些能力的节点上实测 |
| S-04 | 生产 TLS / 双向 TLS 真实握手 | 仅验证配置校验与 uvicorn 参数，未在真实证书链下握手 |
| S-05 | 管理器重启后残留容器的真实清理 | FakeDocker 已覆盖逻辑，未在真实 Docker 节点验证 |
| S-06 | 创建后回查 HostConfig 在真实运行时的结果 | 单元测试覆盖判定逻辑，未在真实 Docker 上确认字段取值 |

### 7.4 阶段 3-A 的用户可见行为变化（已记录，非缺陷）

| 变化 | 之前 | 现在 | 原因 |
|---|---|---|---|
| 代码执行位置 | 业务后端本机 subprocess | 独立 Linux 节点的一次性容器 | 真隔离 |
| 危险模块黑名单 | AST 黑名单拦截 `os` / `asyncio` 等 | **移除**（由容器隔离替代） | 黑名单不可靠且误伤正常代码 |
| 执行超时 | 最大 30s（前端传 20） | 管理员上限 10s，学生不可提高 | 资源保护 |
| 代码输入上限 | 20000 字符 | 65536 字节 | 与新规范对齐 |
| 未部署执行节点时 | 仍可执行（不安全） | `POST /code/run` 返回 503 | 安全失败，禁止降级 |
| 响应字段 | `stdout/stderr/exit_code/duration_ms/timed_out` | 原字段全部保留，新增 `task_id` / `status` | 向前兼容 |

### 7.5 沙箱能力验证矩阵（避免把模拟测试当成真实隔离）

| 能力 | 已实现（代码） | 模拟/单元测试 | 真实 Linux 节点验证 |
|---|---|---|---|
| 学生代码不进业务进程 | 是 | 是（静态检查 + 标记文件） | — |
| 每任务独立容器 | 是 | 参数级 | **未验证** |
| 容器禁网 | 是 | 参数级 | **未验证** |
| 宿主机文件隔离 | 是 | 参数级 | **未验证** |
| CPU/内存/进程/磁盘/输出限制 | 是 | 参数级 | **未验证** |
| 超时终止整个容器 | 是 | 状态映射 | **未验证** |
| 任务结束清理容器 | 是 | 是（FakeDocker） | **未验证** |
| 启动清理残留容器 | 是 | 是（FakeDocker） | **未验证** |
| 镜像 digest 校验 | 是 | 是 | **未验证**（真实 daemon 字段） |
| 生产强制 HTTPS / mTLS | 是 | 是（配置与启动参数） | **未验证**（真实握手） |
| 管理接口认证 | 是 | 是 | **未验证**（TLS/mTLS） |
| 沙箱不可用即拒绝 | 是 | 是 | — |

### 7.6 阶段 3-A 安全审查修复记录（本次）

| 编号 | 问题 | 修复 | 回归测试 |
|---|---|---|---|
| F-01 | Registry Manifest Digest 被直接和 Image ID 比较，校验逻辑错误 | 新增 `image_verify.py`：Registry 引用校验 `RepoDigests`，本地 ID 校验完全相等 | `test_image_verify.py` 7 项 + `test_runner.py` 4 项 |
| F-02 | 管理器可能以明文 HTTP 启动；mTLS 配置不完整不报错 | 生产默认强制 TLS；证书/私钥成对校验、文件可读校验；mTLS 缺 CA/证书拒绝启动；HTTP 仅限显式开发开关 + 回环地址 | `test_config.py` 7 项 |
| F-03 | 创建后只回查部分 HostConfig | 回查运行用户、tmpfs 容量与 `noexec/nosuid/nodev`、日志驱动与上限、端口映射、设备/挂载、资源、运行时、镜像；不符即删容器并拒绝 | `test_container_spec.py` 30 项 + `test_runner.py` |
| F-04 | systemd/部署文档未强调独立节点、Socket 边界、管理接口暴露面 | systemd 增加加固项与网络暴露要求；部署文档补充独立节点、Socket 禁止入容器、防火墙只放行业务后端 | 文档核查（无自动化测试） |
| F-05 | `CodeTask` 无正式 Alembic 迁移 | 新增 `alembic.ini`、`alembic/env.py`、`20261112_0001_add_code_tasks.py` | `test_migration_code_tasks.py` |
| F-06 | 学生可传额外字段（被静默忽略） | 业务端与管理器请求模型 `extra="forbid"`，返回 422 | 后端 + 管理器各 1 项 |
| F-07 | 取消/超时/启动失败清理未被测试覆盖 | FakeDocker 覆盖全部路径与启动清理 | `test_runner.py` 13 项 |
| F-08 | 错误响应可能泄露内部信息 | 管理器错误仅返回错误码；断言响应不含令牌/路径 | `test_server.py` |

## 8. 历史记录（仅追溯，不代表当前状态）

### 8.1 阶段 0：项目接入与现状盘点

当时的事实（**已被后续阶段改变**）：

- Trae 工作区是空目录；真实代码在本地 `C:\Users\wyy\Desktop\sxzd`，且该目录不是 Git 仓库。
- 远程仓库只有 9 份协作文档，**没有任何业务代码**。
- 当时结论为「后端可运行（23 条路由 / `/health` ok）、前端类型检查通过、桌面端仅导入级验证、
  无任何自动化测试」。该结论只对当时快照有效。

阶段 0 的主要产出是把项目接入 GitHub、确认技术栈与风险、建立协作文档体系。

### 8.2 阶段 1：代码基线导入与验证

提交 `3032872`（111 files, +11389）。关键实测结果：

| 项 | 结果 |
|---|---|
| 敏感信息扫描 | 首次命中 5 个脚本硬编码真实 NVIDIA API Key + 4 处个人绝对路径，**脱敏后复扫 0 命中** |
| 后端（干净 venv + 全新目录 + 无 .env / DB） | 启动成功，`/health` ok，23 条路由，自动建表建管理员，`admin` 登录 200，无 token 401 |
| 前端（全新目录 `npm ci`） | 115 packages，`vue-tsc --noEmit` 退出码 0 |
| 桌面端（独立 venv，PySide6 6.12.0） | 6 个模块离屏导入通过（GUI 未实跑） |
| 仓库整洁性 | 无 `.env` / `*.db` / `*.log` / `node_modules` / `dist` |
| 启动脚本 | `start-backend.ps1` / `start-frontend.ps1` 路径少一级，已修正为 `..\backend` / `..\frontend` |

阶段 1 同时确定了 `.gitignore` 规则、安全的 `.env.example` 与 README。

### 8.3 阶段 2：最小自动化测试体系

提交 `09264c5`（12 files, +905/−42）：

- 建立 `backend/tests/`，49 项用例。
- 三层数据库隔离。
- 首轮 `3 failed, 46 passed` → 修复 D-01、D-02 后 `49 passed`。
- 新增 `npm test` 与 `requirements-dev.txt`。

### 8.4 阶段 2 收尾

- 新增 `ZD_ENV_FILE` 配置项，测试彻底不读真实 `.env`。
- 新增 `tests/test_config_isolation.py`（4 项），用例总数由 49 增至 **53**。
- 重写本文件，消除阶段间结论矛盾。

### 8.5 阶段 3-A：代码执行沙箱改造

- 新增 `backend/app/services/sandbox_client.py`、`CodeTask` 模型、`GET /code/tasks/{id}`。
- `POST /code/run` 保留原请求/响应字段，内部改为转发独立沙箱管理器。
- 新增 `sandbox_manager/`（Linux 执行节点）：Docker 一次性容器、全量安全参数、
  管理令牌认证、并发上限、任务状态与取消、`verify_isolation.py` 实机验证脚本。
- 新增 16 项后端沙箱接口测试 + 71 项管理器单元测试，总数由 53 增至 **70（后端）**。
- **本机没有 Linux 执行节点与 Docker，因此没有任何“真实隔离已验证”的结论。**

### 8.6 阶段 3-A 安全审查修复

- 修正镜像 digest 校验（Registry Digest ≠ Image ID），新增 `image_verify.py` 与测试。
- 生产强制 HTTPS / 可选双向 TLS，配置不完整或证书不可读时拒绝启动；明文 HTTP 仅限
  显式开发开关 + 回环地址。
- 容器创建后完整回查 `Config + HostConfig`（用户、tmpfs、日志、端口、设备、资源、运行时、镜像）。
- 增加启动时残留容器清理；取消/超时/启动失败清理均有测试。
- 新增 `code_tasks` Alembic 迁移；请求模型禁止额外字段；错误响应不回显令牌或路径。
- 后端测试 67 → **70**，管理器测试 35 → **71**。

## 9. 本机环境限制（影响复现）

- 全局 Git 配置存在 `url.https://ghfast.top/https://github.com/.insteadOf=https://github.com/`，
  所有 GitHub 请求被改写到镜像代理；代理不稳定时 clone/push 会失败。
- 本机无 `gh` CLI、无 credential helper、无 `GH_TOKEN`/`GITHUB_TOKEN`，推送依赖 Git Credential Manager 登录。
- 本机启用应用控制策略：新建虚拟环境中带 C 扩展的 `.pyd`（如 SQLAlchemy 2.1.8 的 `_collections_cy.pyd`）
  会被拦截，需使用 2.0.x 才能导入；该限制不影响已安装的全局环境。
- 后端与桌面端依赖安装在系统 Python 中，未使用虚拟环境，存在版本漂移风险。

## 10. 复现命令

```powershell
# 后端
cd backend
pip install -r requirements-dev.txt
python -m pytest -q

# 沙箱管理器（无需 Docker，纯单元测试）
cd ..
python -m pytest -q sandbox_manager/tests

# 前端
cd frontend
npm install
npm test
```

真实隔离验证（只能在专用 Linux 执行节点运行）：

```bash
python3 sandbox_manager/scripts/verify_isolation.py \
  --url https://<节点>:8443 --token "$ZD_SANDBOX_TOKEN"
```

## 11. 本机环境补充

- 开发机为 Windows 且未安装 Docker，无法启动 Linux 容器，
  因此阶段 3-A 的容器隔离、网络隔离、资源限制、容器清理**均未在本机实机验证**。
- 上述能力的测试结果只能以 Linux 执行节点上的 `verify_isolation.py` 输出为准。
