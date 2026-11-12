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
| 后端测试 | **113 项，全部通过**（`backend/tests/`） |
| 沙箱管理器测试 | **141 项，全部通过**（`sandbox_manager/tests/`） |
| 前端测试 | **通过**（`npm test` → vue-tsc，退出码 0） |
| 数据库 | 测试使用临时 SQLite，**不接触真实库** |
| 真实 `.env` | 测试**不读取**（`ZD_ENV_FILE` 指向不存在的临时文件） |
| 代码执行 | 已改为「业务后端 + 独立 Linux 执行节点 + 一次性 Docker 容器」架构；**真实隔离尚未在 Linux 节点验证** |
| 操作系统 | Windows 10/11，Python 3.13.14，Node v26.13.0 |

## 2. 结论摘要

1. 后端 113 项自动化测试全部通过，覆盖鉴权、实验 CRUD 与导入、进度、报告、配置隔离、代码沙箱接口、数据库初始化与迁移、管理接口传输安全与连接池生命周期。
2. 沙箱管理器 141 项单元测试全部通过，覆盖容器安全参数（含创建后完整回查）、固定镜像 digest 校验、
   生产 HTTPS / 双向 TLS 启动约束、启动清理阻断、清理范围隔离、输出流式限额、队列上限与内部队列、
   结果字段校验、生命周期，以及验收工具 `verify_isolation.py` 的 PASS/FAIL/SKIP 判定可靠性
   （网络 errno 分类、stdout/stderr 分别与合计截断、`memory.swap.max`、本地临时 mTLS 握手、执行节点身份声明）。
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

## 4. 后端自动化测试（113 项 + 141 项）

### 4.1 用例分布

| 文件 | 用例数 | 通过 | 失败 |
|---|---|---|---|
| `tests/test_auth.py` | 12 | 12 | 0 |
| `tests/test_experiments.py` | 16 | 16 | 0 |
| `tests/test_progress.py` | 11 | 11 | 0 |
| `tests/test_report.py` | 10 | 10 | 0 |
| `tests/test_config_isolation.py` | 4 | 4 | 0 |
| `tests/test_code_sandbox.py` | 36 | 36 | 0 |
| `tests/test_sandbox_client.py` | 18 | 18 | 0 |
| `tests/test_migration_code_tasks.py` | 1 | 1 | 0 |
| `tests/test_db_init.py` | 5 | 5 | 0 |
| **backend 合计** | **113** | **113** | **0** |
| `sandbox_manager/tests/test_container_spec.py` | 41 | 41 | 0 |
| `sandbox_manager/tests/test_server.py` | 19 | 19 | 0 |
| `sandbox_manager/tests/test_jobs.py` | 21 | 21 | 0 |
| `sandbox_manager/tests/test_verify_isolation.py` | 29 | 29 | 0 |
| `sandbox_manager/tests/test_config.py` | 7 | 7 | 0 |
| `sandbox_manager/tests/test_image_verify.py` | 7 | 7 | 0 |
| `sandbox_manager/tests/test_runner.py` | 17 | 17 | 0 |
| **管理器合计** | **141** | **141** | **0** |

### 4.2 实际执行结果

```
# backend
python -m pytest -q
113 passed, 400 warnings in 61.10s

# sandbox_manager（无 Docker 依赖，纯单元测试）
python -m pytest -q sandbox_manager/tests
141 passed, 1 warning in 2.64s
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
- **启动清理阻断**：清理时 Docker 不可用或容器删除失败 → 启动直接失败（抛 `RuntimeError`），
  不会进入可服务状态；清理成功才允许 `/health` 与任务接口可用。
- **清理范围隔离**：容器打 `zd.sandbox.instance=<实例>` 与 `zd.sandbox.job=<job>` 标签；
  启动清理只删除本实例遗留容器，其他实例 / 无实例标签 / 其他服务的容器不会被删除。
- **输出限制**：Docker json-file 日志总存储上限 64KB（`max-size=64k`、`max-file=1`）；
  返回时按流读取，stdout / stderr 各自上限 32KB，达到上限立即停止读取并关闭流，
  不做“先读完无限日志再截断”。
- **数据库初始化**：开发环境默认 `create_all`；生产环境（或 `DB_AUTO_CREATE=false`）
  缺少表时拒绝启动并提示 `alembic upgrade head`；迁移补齐 `code_tasks` 后可通过检查。
- **队列上限**：管理器使用固定线程池，排队任务上限 `4 × 最大并发`（可配置），
  超限返回稳定 `queue_full`；被拒绝的请求不创建任务、不启动容器；取消/开始执行会释放容量。
- **传输安全**：非回环地址强制 HTTPS；明文 HTTP 仅限显式开发开关 + 回环地址；
  客户端证书与私钥必须成对，缺失时启动失败；保留证书校验。
- **错误脱敏**：管理器只返回固定安全文案，内部细节仅写服务端日志；学生任务查询
  不返回 Docker 错误、镜像地址、宿主机路径；教师可查看内部诊断。
- **/dev/shm**：固定 8MB，并在 Docker 实际配置中回查，防止默认 64MB 绕过磁盘预算。
- **安全配置回查**：seccomp / AppArmor 选项、`CapAdd` 为空、`Init`、`ShmSize`
  等逐项与实际 `HostConfig` 比对，不匹配即删除容器拒绝执行。
- **异步轮询与异常收口**：路由改为 `async` + `httpx.AsyncClient`，不阻塞事件循环；
  畸形响应 / 异常 / 保存失败都会把任务落到安全终态，并尽力取消沙箱任务。
- **内部队列有界**：管理器使用固定 daemon 工作线程 + 有界 deque；取消排队任务会从内部队列
  移除，不会留下占位项；重复提交/取消不会累积内部任务。
- **异常收口扩大**：沙箱提交成功后任何异常（含状态更新、轮询、保存）都会尽力取消远端任务，
  本地任务不会永久停留在 `queued/running`。
- **`no-new-privileges` 严格校验**：必须精确包含 `no-new-privileges:true`；
  `no-new-privileges:false` 或裸选项一律拒绝。
- **连接池生命周期**：异步 `SandboxClient` 由 FastAPI lifespan 在应用关闭时 `aclose()`；
  可幂等重复关闭。
- **权限统一**：教师与管理员共用同一套“可查看其他用户任务 / 内部错误”的判断入口；
  学生仍只能查看自己的任务，越权统一 404。
- **管理器结果校验**：执行器返回的状态、输出类型、退出码、耗时先做结构校验，
  畸形结果落为 `failed/internal_error`，不把异常对象或内部内容返回给调用方。
- **队列满映射**：管理器 429 被识别为 `SandboxBusy`，业务后端返回 429 而不是 503，
  并记录任务 `error_code=queue_full`。
- **结果字段完整校验**：后端在保存前校验 `status` / `stdout` / `stderr` / `exit_code` /
  `duration_ms` / `error_code` / `error_message`，使用 `type(x) is int` 拒绝 bool；
  管理器对 Runner 返回值执行同等校验；畸形结果统一 `failed/internal_error`，
  且校验发生在数据库提交之前，不会出现“已保存 succeeded 后接口 500”。

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
| S-01 | 容器网络隔离（公网 / 局域网 / 业务端口） | **未执行**：开发机为 Windows、无 Docker、无 Linux 节点 |
| S-02 | 文件系统隔离（宿主机 / 业务文件不可读） | **未执行** |
| S-03 | 根文件系统只读 | **未执行** |
| S-04 | 非 root 身份运行 | **未执行** |
| S-05 | 无额外挂载与设备 | **未执行** |
| S-06 | 无端口映射 | **未执行** |
| S-07 | CPU 限制 0.5 核 | **未执行** |
| S-08 | 内存与交换限制 128MB | **未执行** |
| S-09 | PID 数量限制 32 | **未执行** |
| S-10 | 临时磁盘限制（tmpfs 24MB / 业务 16MB） | **未执行** |
| S-11 | 执行超时与进程终止 | **未执行** |
| S-12 | stdout/stderr 输出截断 64KB | **未执行** |
| S-13 | 任务完成后容器清理 | **未执行** |
| S-14 | 并发与队列限制（2 并发 / 8 排队） | **未执行** |
| S-15 | HTTPS / mTLS 身份认证与证书错误处理 | **未执行** |

> S-01 ~ S-15 的命令、预期结果与证据要求见 `SANDBOX_DEPLOYMENT.md` §17；
> 当前全部为“未执行”，不得用单元测试或配置检查替代实机结论。

补充未验证项（技术细节，与上表互补）：

| 编号 | 项 | 说明 |
|---|---|---|
| V-01 | Docker / 镜像 / 运行时故障注入 | 仅用 FakeRunner 模拟，未在真实节点停止 Docker 或替换镜像验证 |
| V-02 | gVisor / AppArmor / seccomp 实际启用 | 已做启动前校验，未在启用这些能力的节点上实测内核强制 |
| V-03 | 管理器异常退出后残留容器的真实清理 | FakeDocker 已覆盖逻辑；S-13 只覆盖正常结束路径 |
| V-04 | 创建后回查 HostConfig 的真实字段取值 | 单元测试覆盖判定逻辑，未在真实 Docker 上确认 |
| V-05 | 启动清理失败在真实 Docker 下的阻断效果 | FakeDocker 验证抛错，未在真实节点验证 |
| V-06 | 多实例清理隔离 | 标签过滤逻辑已测，未在真实多实例节点验证 |
| V-07 | 日志轮转与流式读取的真实字节上限 | 单元测试使用假日志流，未在真实 json-file 驱动下验证 |
| V-08 | 队列上限在真实高并发下的表现 | 线程级单元测试通过；S-14 覆盖端到端 |
| V-09 | `/dev/shm` 8MB 在真实容器中的实际挂载 | 仅验证 inspect 字段与创建参数；S-10 覆盖 |
| V-10 | 异步接口 / 连接池在真实并发下的行为 | 仅接口级测试，未做真实压测 |

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
| 启动清理失败阻断服务 | 是 | 是（FakeDocker） | **未验证** |
| 清理只作用于本实例 | 是 | 是（标签过滤） | **未验证** |
| 输出流式限额 | 是 | 是（假日志流） | **未验证** |
| 生产库必须迁移而非 create_all | 是 | 是（临时 SQLite + Alembic） | **未验证**（真实库升级） |
| 队列上限 / queue_full | 是 | 是（线程模拟） | **未验证**（真实压测） |
| `/dev/shm` 8MB | 是 | 是（inspect 字段） | **未验证**（真实挂载） |
| seccomp / AppArmor 记录回查 | 是 | 是（模拟 attrs） | **未验证**（内核实际加载） |
| 异步轮询不阻塞事件循环 | 是 | 接口测试 + 静态检查 | **未验证**（真实压测） |
| 取消后内部队列有界 | 是 | 线程模拟测试 | **未验证**（真实压力） |
| 管理器 429 → 后端 429 | 是 | MockTransport + FakeSandbox | **未验证**（端到端联调） |
| 连接池随 lifespan 释放 | 是 | lifespan 单元测试 | **未验证**（真实进程退出） |
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

#### 第二轮审查补充修复

| 编号 | 问题 | 修复 | 回归测试 |
|---|---|---|---|
| F-09 | 启动清理失败仅告警，仍继续服务 | 清理失败直接抛 `RuntimeError`，进程启动失败，绝不进入可服务状态 | `test_server.py` 3 项 |
| F-10 | 清理仅按 `zd.sandbox=1`，可能误删其他实例容器 | 增加 `zd.sandbox.instance`（及 `zd.sandbox.job`）标签，清理只匹配本实例；明确单实例/多实例策略 | `test_runner.py` 2 项 + `test_container_spec.py` 1 项 |
| F-11 | 日志整块读取后再截断，双通道未分别限额 | 日志按流读取，达到上限停止；stdout/stderr 各 32KB，日志存储总量 64KB | `test_runner.py` 2 项 + `test_container_spec.py` 1 项 |
| F-12 | 生产环境仍依赖 `create_all` 自动建表 | `DB_AUTO_CREATE` 策略：开发默认建表，生产缺表拒绝启动并提示 Alembic；迁移测试补齐 | `test_db_init.py` 5 项 |

#### 第三轮审查（P1）修复

| 编号 | 问题 | 修复 | 回归测试 |
|---|---|---|---|
| F-13 | 管理器任务队列无上限，可被大量阻塞线程打满 | 固定线程池 + `max_pending`（默认 4×并发），超限 `queue_full`；拒绝请求不建任务/容器 | `test_jobs.py` 4 项、`test_server.py` 1 项 |
| F-14 | 后端允许明文 HTTP 访问管理器，mTLS 配置可缺失 | 非回环强制 HTTPS；回环 HTTP 需显式开发开关；证书/私钥必须成对；启动校验 | `test_sandbox_client.py` 15 项 |
| F-15 | 内部错误信息会返回给学生 | 管理器固定安全文案 + 内部日志；学生接口固定文案，教师经权限检查看详情 | `test_server.py` 1 项、`test_code_sandbox.py` 1 项 |
| F-16 | `/dev/shm` 默认 64MB 绕过磁盘预算 | 显式 8MB 并在 `HostConfig.ShmSize` 回查 | `test_container_spec.py` 3 项 |
| F-17 | seccomp/AppArmor/CapAdd/Init 未回查实际配置 | 逐项比对 `SecurityOpt`、`CapAdd`、`Init`、`ShmSize`，不匹配删容器 | `test_container_spec.py` 4 项 |
| F-18 | 同步轮询占用线程池 | `async def` + `httpx.AsyncClient` + 连接/读取超时与连接池上限；后端并发保护 429 | `test_code_sandbox.py` 4 项 |
| F-19 | 异常路径可能留下永久 running 任务 | 畸形响应 / 异常 / 保存失败统一收口为安全终态并尽力取消 | `test_code_sandbox.py` 4 项 |

#### 第四轮审查（F-20 ~ F-24）修复

| 编号 | 问题 | 修复 | 回归测试 |
|---|---|---|---|
| F-20 | 取消后执行器内部队列仍可能积累 | 固定 daemon 工作线程 + 有界 deque；取消排队任务直接移出队列 | `test_jobs.py` 2 项 |
| F-21 | 提交成功后部分异常未取消远端任务 | 任务创建后全流程统一 try/except；任何异常取消远端并落终态 | `test_code_sandbox.py` 2 项（取消断言、队列满） |
| F-22 | `no-new-privileges` 校验过宽 | 必须精确包含 `no-new-privileges:true` | `test_container_spec.py` 2 项 |
| F-23 | 异步连接池未随应用关闭释放 | `aclose()` + FastAPI lifespan 关闭；幂等 | `test_sandbox_client.py` 2 项 |
| F-24 | 教师/管理员权限判断分散 | 统一 `STAFF_ROLES` / `_is_staff` / `_can_view_task` | `test_code_sandbox.py` 1 项 |
| — | 管理器结果字段未校验 | 状态、输出类型、退出码、耗时结构校验，畸形落 `internal_error` | `test_jobs.py` 6 项 |
| — | 管理器 429 被误映射为 503 | `SandboxBusy` → 业务后端 429；任务 `queue_full` | `test_sandbox_client.py` 1 项、`test_code_sandbox.py` 1 项 |

#### 第五轮结果字段完整校验

| 编号 | 问题 | 修复 | 回归测试 |
|---|---|---|---|
| F-25 | 结果字段校验不完整（bool 可冒充 int、error_* 未校验） | 后端与管理器均使用 `type(x) is int` 严格判断；补齐 `error_code` / `error_message`；后端在 `_save_result` 之前调用 `_validate_terminal_result` | `test_code_sandbox.py` 9 项、`test_jobs.py` 5 项 |

#### 第七轮验收工具可靠性

| 编号 | 问题 | 修复 | 回归测试 |
|---|---|---|---|
| F-26 | SKIP 也可能退出码 0、错误令牌任意异常算 PASS、标记文件可能不在 Docker 宿主机、Docker 残留可能查错机器、CPU 只做字符串匹配 | 新增 PASS/FAIL/INCOMPLETE 三态与退出码 0/1/2；错误令牌仅 401 通过；标记文件与宿主检查要求 `--on-execution-node`；Docker 残留要求 `--docker-check local`；CPU 解析 quota/period；网络与资源测试要求明确证据 | `test_verify_isolation.py` 17 项 |

#### 第八轮验收证据补强

| 编号 | 问题 | 修复 | 回归测试 |
|---|---|---|---|
| F-27 | 网络探测把所有 `OSError` 当 `NET_BLOCKED`，DNS 失败 / ConnectionRefused / 超时可能被误判为隔离 | 容器内输出结构化 `NET_RESULT`（type + errno）；只有 `ENETUNREACH(101)` / `EHOSTUNREACH(113)` / `EACCES(13)` / `EPERM(1)` 算阻断证据；Refused、DNS、timeout、未知异常均 FAIL；记录类型与 errno | `test_verify_isolation.py` 网络 6 项 |
| F-28 | 只检查 stdout 截断，未验证 stderr 与合计上限 | 分别提交大量 stdout / stderr 任务，校验字节数、终态、非空，并新增 stdout+stderr 合计上限检查 | `test_verify_isolation.py` 3 项 |
| F-29 | 未检查 `memory.swap.max`，`max` 可能被当作有限制 | 新增 `parse_swap_max`：`max`/空/格式错误均非 PASS；本项目 memswap==mem 期望 `0`；文件不可读时 SKIP | `test_verify_isolation.py` 1 项 |
| F-30 | mTLS 只覆盖证书加载，未验证真实握手 | 本地临时 TLS 服务覆盖合法握手、无证书、不受信客户端证书、不受信服务端证书、错误令牌 401、证书与私钥不匹配；证书临时生成自动清理，不输出私钥 | `test_verify_isolation.py` 6 项 |
| F-31 | `--on-execution-node` 布尔开关被当作身份证明 | 明确为人工声明；仅在本机 Docker 可用时记“非密码学证明”，未声明/不可用则 SKIP；文档要求先 SSH 登录执行节点并核对管理器/Docker/Socket 同节点 | `test_verify_isolation.py` 1 项 |

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
- 新增 16 项后端沙箱接口测试 + 80 项管理器单元测试，总数由 53 增至 **75（后端）**。
- **本机没有 Linux 执行节点与 Docker，因此没有任何“真实隔离已验证”的结论。**

### 8.6 阶段 3-A 安全审查修复

- 修正镜像 digest 校验（Registry Digest ≠ Image ID），新增 `image_verify.py` 与测试。
- 生产强制 HTTPS / 可选双向 TLS，配置不完整或证书不可读时拒绝启动；明文 HTTP 仅限
  显式开发开关 + 回环地址。
- 容器创建后完整回查 `Config + HostConfig`（用户、tmpfs、日志、端口、设备、资源、运行时、镜像）。
- 增加启动时残留容器清理；取消/超时/启动失败清理均有测试。
- 新增 `code_tasks` Alembic 迁移；请求模型禁止额外字段；错误响应不回显令牌或路径。
- 后端测试 67 → **70**，管理器测试 35 → **71**。

### 8.7 阶段 3-A 第二轮审查补充

- 启动清理失败 → 服务拒绝启动（不再降级继续服务）。
- 清理范围收紧到本实例标签（instance + job），避免误删其他实例容器。
- 输出改为流式读取并分通道限额（stdout/stderr 各 32KB，日志存储 64KB）。
- 数据库初始化区分开发 / 生产：生产缺表拒绝启动，必须先 `alembic upgrade head`。
- 后端测试 70 → **75**，管理器测试 71 → **80**。

### 8.8 阶段 3-A 第三轮 P1 修复

- 管理器队列上限（固定线程池 + `max_pending` + `queue_full`）。
- 后端强制 HTTPS / 完整 mTLS；明文 HTTP 仅限显式本地开发回环。
- 学生端错误信息在后端接口层脱敏；教师可查看内部诊断。
- `/dev/shm` 固定 8MB；seccomp/AppArmor/CapAdd/Init 实际配置回查。
- 代码执行接口改异步，增加连接池与并发保护，避免阻塞事件循环 / 请求堆积。
- 异常路径统一收口，任务不会静默永久停在 `running`。
- 后端测试 75 → **99**，管理器测试 80 → **93**；真实 Linux 实机验证仍未完成。

### 8.9 阶段 3-A 第四轮 F-20 ~ F-24 修复

- 管理器内部队列改为有界 deque + 固定 daemon 工作线程；取消排队任务立即移出队列。
- 沙箱提交成功后任何异常都会尽力取消远端任务，本地任务落到安全终态。
- `no-new-privileges` 必须精确为 `no-new-privileges:true`。
- 异步连接池随 FastAPI lifespan 关闭，可幂等释放。
- 教师 / 管理员共用统一权限入口；学生越权仍返回 404。
- 管理器执行器结果增加结构校验，畸形结果统一 `failed/internal_error`。
- 管理器 429 正确映射为业务后端 429（任务 `queue_full`），不再误报 503。
- 后端测试 99 → **104**，管理器测试 93 → **102**；真实 Linux 实机验证仍未完成。

### 8.10 阶段 3-A 第五轮结果字段完整校验

- 后端 `_validate_job_result` 完整校验 7 个字段，bool 不再被当作 int；
  新增 `_validate_terminal_result`，在 `_save_result` 之前强制终态与字段校验。
- 管理器 `_validate_result` 同步补齐 `error_code` / `error_message` 与严格整数判断。
- 畸形结果统一落 `failed/internal_error`，不保存 succeeded，不泄露原始内容。
- 后端测试 104 → **113**，管理器测试 102 → **107**。
- 真实 Linux / Docker 实机验证仍未完成，本轮不代表阶段 3-A 安全验收通过。

### 8.11 阶段 3-A 第七轮验收工具可靠性

- `verify_isolation.py` 改为三态判定：PASS 退出 0、FAIL 退出 1、INCOMPLETE 退出 2；
  必检项 SKIP 不再可能得到 0。
- 错误令牌仅在 HTTP 401 时通过；连接拒绝、TLS、DNS 异常均记 FAIL。
- 宿主机标记文件只在 `--on-execution-node` 时创建/测试，否则 SKIP；
  容器残留只在 `--docker-check local` 时检查，否则 SKIP 并给出节点侧命令。
- 新增 `--client-cert` / `--client-key` / `--expect-mtls`，验证无证书、错误证书、
  合法证书、不受信服务端证书四种情况；私钥不输出。
- CPU 解析 `quota/period` 比例，内存与 PID 精确比较；网络/超时/内存/fork/磁盘/输出
  均要求任务终态与明确标记，不再把任意失败当作限制生效。
- 管理器测试 112 → **129**（新增 `test_verify_isolation.py` 17 项），后端仍为 113。
- 自动化测试通过，但**验收工具本身未在真实 Linux / Docker 节点运行**，
  S-01 ~ S-15 仍全部未执行。

### 8.12 阶段 3-A 第八轮验收证据补强

- 网络判定改为解析容器内结构化 `NET_RESULT`，按 Linux errno 分类：
  `ENETUNREACH/EHOSTUNREACH/EACCES/EPERM` 算阻断；`ConnectionRefused`、DNS 失败、
  超时、未知异常均 FAIL；输出记录异常类型与 errno。
- 新增 stdout / stderr 分别提交任务验证截断字节数、任务终态与非空输出，并新增
  stdout+stderr 合计上限检查；不能用配置值替代实跑。
- 新增 `memory.swap.max` 检查与 `--expected-swap-mb`（本项目 memswap==mem，期望 0）；
  `max` 不算有限制，文件不可读 SKIP。
- 新增本地临时 TLS 的 mTLS 握手测试：合法成功、无证书失败、不受信客户端证书失败、
  不受信服务端证书失败、合法证书+错误令牌 401、证书与私钥不匹配初始化失败；
  证书临时生成并自动清理，不输出私钥。
- `--on-execution-node` 明确为操作人员声明而非密码学证明；文档要求先 SSH 登录执行节点，
  核对管理器、Docker Engine、Docker Socket 同节点，无法确认时相关项 SKIP。
- 管理器测试 129 → **141**（`test_verify_isolation.py` 17 → 29 项），后端仍为 113。
- 全部为自动化/本地临时环境测试，**不代表真实 Linux / Docker 实机验收**；
  S-01 ~ S-15 仍全部未执行。

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
