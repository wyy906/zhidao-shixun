# 下一步

## 现状一句话

后端 113 项 pytest、沙箱管理器 129 项单元测试、前端 `npm test` 全部通过；
学生代码已改为「独立 Linux 执行节点 + 一次性 Docker 容器」执行，业务后端不再持有本机执行路径。
已完成三轮安全审查修复（镜像 digest、HTTPS/mTLS、容器配置回查、启动清理阻断、清理范围、
输出限额、数据库初始化、队列上限、错误脱敏、异步轮询与异常收口）。
**真实容器隔离与 TLS 握手尚未在 Linux 节点验证**，下一步是在执行节点运行 `verify_isolation.py` 并记录实机结果。

---

## 已完成

### 阶段 1：代码基线（`3032872`）

- `backend/`、`frontend/`、`desktop/`、`scripts/`、`experiment_packs/`、`demo_shots/` 已入库。
- 密钥、数据库、日志、依赖、构建产物、`ai_review/` 全部排除。

### 阶段 2：最小自动化测试（已完成）

- 新增 `backend/tests/`：`conftest.py` + 5 个用例文件，共 **53 项**，全部通过。
- 测试数据库三层隔离：临时 `DATABASE_URL` + `tmp_path` 独立 SQLite + `dependency_overrides`。
- **配置隔离**：新增 `ZD_ENV_FILE` 环境变量，pytest 在导入 app 前将其指向不存在的临时文件，
  测试完全不读取真实 `backend/.env`；`tests/test_config_isolation.py` 提供 4 项验证。
- 前端 `frontend/package.json` 新增 `npm test`（vue-tsc 类型检查），实测退出码 0。
- 新增 `backend/requirements-dev.txt`（`-r requirements.txt` + `pytest`）。
- 修复 3 个真实缺陷（D-01 步骤序号越界、D-02 不存在实验写孤儿进度、D-09 测试可能读取真实 .env），
  详见 `TEST_REPORT.md` 7.1。

### 阶段 3-A：代码执行沙箱（已实现，待实机验证）

- `POST /code/run` 不再在业务后端或本机 subprocess 执行代码，改为：
  校验 → 创建 `CodeTask` → 转发独立沙箱管理器 → 轮询结果。
- 新增 `GET /code/tasks/{task_id}`：学生只能看自己的任务，教师可查看；task_id 为 uuid4，不可猜测。
- 沙箱管理器（`sandbox_manager/`，Linux）：Docker 一次性容器、`network=none`、只读根文件系统、
  非 root、drop ALL caps、no-new-privileges、内存/CPU/进程/磁盘/输出限制、任务结束强制回收。
- 安全失败：管理器未配置 / 不可用 / Docker 异常 / 镜像 digest 不匹配 / 清理失败 → 一律拒绝执行，
  不存在回退本机执行的代码路径。
- 服务重启会把 `queued/running` 任务标记为失败，不会当成成功。
- 新增测试：后端 14 项（`tests/test_code_sandbox.py`）+ 管理器 35 项；安全审查修复后
  后端增至 **70**、管理器增至 **71**（第二轮后为 **75 / 80**）。
- 部署与验证：见 `SANDBOX_DEPLOYMENT.md`、`sandbox_manager/scripts/verify_isolation.py`。

#### 安全审查修复（已完成）

- 修正镜像 digest 校验：Registry Manifest Digest 与 Image ID 分开处理（`image_verify.py`）。
- 生产强制 HTTPS，支持双向 TLS；证书缺失/不可读/不成对时拒绝启动；
  明文 HTTP 仅限显式开发开关 + 回环地址，无自动降级。
- 容器创建后完整回查运行用户、tmpfs 容量与选项、日志驱动/上限、端口映射、设备挂载、
  资源限制、运行时与镜像，不符即删除容器并拒绝执行。
- 管理器启动时清理 `zd.sandbox=1` 残留容器；取消/超时/启动失败清理均有测试。
- 新增 `code_tasks` 正式 Alembic 迁移；请求模型禁止额外字段；错误响应不回显令牌/路径。
- 测试增加：后端 67 → **75**，管理器 35 → **80**。

#### 第二轮审查补充修复（已完成）

- 启动清理失败（Docker 不可用 / 删除失败）→ 进程启动失败，不进入可服务状态。
- 容器打 `zd.sandbox.instance` / `zd.sandbox.job` 标签；启动清理只删本实例遗留容器；
  单节点推荐单实例，多实例必须配置不同 `ZD_SANDBOX_INSTANCE_ID`。
- 日志流式读取，stdout/stderr 各 32KB，日志存储总量 64KB，不再整块读完再截断。
- 数据库初始化：开发默认 `create_all`；生产缺表拒绝启动，必须先 `alembic upgrade head`。

#### 第三轮 P1 修复（已完成）

- 管理器队列上限：固定线程池 + `max_pending`，超限 `queue_full`，不创建任务/容器。
- 后端强制 HTTPS / 完整 mTLS；明文 HTTP 仅限显式本地开发回环。
- 学生端错误脱敏（管理器固定文案 + 学生接口固定文案，教师可查看内部诊断）。
- `/dev/shm` 固定 8MB；seccomp/AppArmor/CapAdd/Init/ShmSize 实际配置回查。
- `/code/run` 改异步 + 连接池 + 全局/每用户并发上限（429）。
- 畸形响应、轮询异常、保存失败统一收口为安全终态，并尽力取消沙箱任务。
- 测试：后端 75 → **99**，管理器 80 → **93**。

#### 第四轮 F-20 ~ F-24 修复（已完成）

- 管理器内部队列改为有界 deque + 固定 daemon 工作线程；取消即移出队列。
- 沙箱提交成功后任何异常都会尽力取消远端任务，本地任务落安全终态。
- `no-new-privileges` 严格校验为 `no-new-privileges:true`。
- 异步连接池随 FastAPI lifespan 关闭。
- 教师 / 管理员权限判断统一；学生越权仍 404。
- 管理器结果字段校验；队列满 429 正确映射为业务后端 429（任务 `queue_full`）。
- 测试：后端 99 → **104**，管理器 93 → **102**。

#### 第五轮结果字段完整校验（已完成）

- 后端完整校验 7 个结果字段，bool 不再冒充 int，保存前强制终态校验。
- 管理器补齐 `error_code` / `error_message` 与严格整数校验，畸形结果 `failed/internal_error`。
- 测试：后端 104 → **113**，管理器 102 → **107**。
- 仍不代表 Linux / Docker 实机安全验收完成。

> ⚠️ 开发机为 Windows 且无 Docker，**容器隔离能力未实机验证**。在负责人完成 Linux 节点验收前，
> 不得对外宣称沙箱已通过安全验收。

#### 实机部署准备（本轮已完成；环境尚未具备）

- `SANDBOX_DEPLOYMENT.md` 补齐节点就绪检查、Docker 版本校验、专用账号、镜像构建与 digest、
  管理器安装/启停、证书生成与 mTLS 验证、故障排查、证据保存。
- 新增 §17 `S-01 ~ S-15` 实机验收清单（目标 / 命令 / 预期 / 实际 / 证据 / 状态）。
- `verify_isolation.py` 新增非 root、根文件系统只读、仅回环网卡、cgroup CPU/内存/PID 实际限额检查。
- 环境检查结论：Windows、无 Docker CLI、无 WSL 发行版、无已配置 Linux 节点，
  **S-01 ~ S-15 全部未执行**。
- 下一步（需要负责人提供）：专用 Ubuntu 22.04/24.04 节点、Docker、内网证书，
  然后按 §17 逐项执行并保存证据。

#### 验收工具可靠性（第七轮已完成）

- `verify_isolation.py` 支持 PASS / FAIL / INCOMPLETE 三态，退出码 0 / 1 / 2；
  必检项 SKIP 不再返回 0。
- 错误令牌仅 HTTP 401 通过；宿主机标记与容器残留检查要求在执行节点运行；
  CPU 按 quota/period 校验；网络与资源测试要求明确证据。
- 新增 mTLS 客户端证书参数与四项 TLS 验证。
- 管理器测试 112 → **129**（新增 17 项工具可靠性测试）；仍无 Linux 实机验证。

---

## 需要负责人决策的问题

| 编号 | 问题 | 建议 |
|---|---|---|
| D-03 | `overwrite=False` 时同标题实验可重复导入 | 建议改为按标题去重或返回 409 |
| D-04 | 无教师查看/批阅学生报告接口 | 新增教师只读视图或批阅接口（属新功能） |
| D-05 | 六个字段全空的报告也能提交 | 明确「空报告」判定规则后加校验 |
| D-06 | `GET /experiments/{id}` 与 `/steps` 无鉴权 | 确认是否应要求登录 |
| D-07 | 覆盖导入会连带删除学生进度与报告 | 确认是否改为保留/归档历史进度 |
| R-01 | 后端 `admin_password` 默认 `demo123`；桌面端内置 `auto_login("admin","demo123")` | 首次启动强制改密；桌面端移除默认凭据 |
| R-02 | `sqlalchemy>=2.0.35` 实测会装到 2.1.8，其 C 扩展在启用应用控制的机器上被拦截 | 收敛版本上限或改纯 Python 安装 |
| S-04 | 执行超时由最大 30s 收紧为 10s（学生不可提高），`/code/run` 输入上限改为 64KB | 确认教学实验是否够用；如不足请调整 `CODE_RUN_TIMEOUT_SECONDS`（管理员配置） |
| S-05 | 移除了 AST 危险模块黑名单（改由容器真隔离） | 确认是否接受 `import os` 等代码在沙箱内运行 |
| S-06 | 未部署执行节点时 `/code/run` 返回 503（此前可直接运行） | 部署顺序需先上线执行节点，再开启 `CODE_EXECUTION_ENABLED` |
| S-07 | 执行节点需要内网 TLS 证书（生产强制，本机开发才可明文） | 由负责人签发/部署证书，并配置业务端 CA / 客户端证书 |
| R-06 | 桌面端 GUI/UIA/悬浮层仍未实跑验证 | 需人工点验 |

---

## 阶段 3：风险治理与工程化（进行中）

1. **P0 `/code/run` 沙箱化**：架构、代码与安全审查修复已完成；**待 Linux 执行节点实机验证**
   （`SANDBOX_DEPLOYMENT.md` 第 9、10 节 + `verify_isolation.py`）。
2. **P0 凭据治理**：修复 R-01；确认 `AI_API_KEY` 只存在于本地 `.env`。
3. **P1 数据库迁移**：`alembic` 目前只有 `env.py`，补首个 revision，结束 `create_all` 与迁移双轨
   （阶段 3-A 新增了 `code_tasks` 表）。
4. **P1 导入校验**：`POST /experiments/import` 的 `adapter` 结构弱校验，错误会延迟到桌面端才暴露。
5. **P1 桌面端拆分**：`desktop/src/ui/main_window.py` 偏大，按「窗口选择 / 实验驱动 / 教程 / 悬浮层」拆分。
6. **P2 体验**：Monaco 懒加载（当前约 3.3 MB）；桌面端补断线重连提示。

## 阶段 4：MVP 演示闭环（需产品确认范围）

- 一个网页内 Python 实验 + 一个外部软件实验（MySQL Workbench 需先确认环境可用）。
- 能识别当前步骤与完成状态，给出逐步指导、错误提示与结果验证，并留存过程记录。

## 测试维护约定

- 新增接口或修改业务规则时，必须同步补 `backend/tests/` 用例。
- 沙箱相关改动必须同时运行 `python -m pytest -q sandbox_manager/tests`。
- 用例不得依赖网络、真实 AI Key、真实数据库。
- 不得把模拟测试（FakeRunner / 参数级单测）写成“真实隔离已验证”。
- `pytest` 出现失败时先判断是代码缺陷还是用例过期，**不得通过删断言或 skip 变绿**。
