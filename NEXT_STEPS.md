﻿﻿# 下一步

## 现状一句话

后端 113 项 pytest、沙箱管理器 **168 项**单元测试、前端 `vue-tsc --noEmit` 全部通过（2026-11-13 实测）。
学生代码已改为「独立 Linux 执行节点 + 一次性 Docker 容器」执行，业务后端不再持有本机执行路径。
已完成多轮安全审查修复（镜像 digest、HTTPS/mTLS、容器配置回查、启动清理阻断、清理范围、
输出限额、数据库初始化、队列上限、错误脱敏、异步轮询与异常收口、attach 输出采集完整性）。

当前状态（区分三件事）：

| 维度 | 状态 |
|---|---|
| 单元测试 | **通过**（后端 113 / 管理器 168 / 前端类型检查 0 错误） |
| WSL2 实机验收 | **当前 WSL2 节点 S-01~S-15 通过**（`verify_isolation.py` 27 项 PASS） |
| 独立 Linux 生产节点验收 | **尚未验收** |
| 桌面端 GUI / UIA / 悬浮层（R-06） | **主路径 PASS**（2026-11-13 Windows 11 实机点验）；2 项 INCOMPLETE |

> 下文历史记录中的“151 项”“真实隔离尚未验证”“S-01~S-15 全部未执行”等表述，
> 均为**当时的历史状态**，不代表当前结论。

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
  **S-01 ~ S-15 全部未执行**（**历史状态**；当前已在 WSL2 节点执行并通过，见开篇“当前状态”）。
- 下一步（需要负责人提供）：专用 Ubuntu 22.04/24.04 节点、Docker、内网证书，
  然后按 §17 逐项执行并保存证据。

#### 验收工具可靠性（第七轮已完成）

- `verify_isolation.py` 支持 PASS / FAIL / INCOMPLETE 三态，退出码 0 / 1 / 2；
  必检项 SKIP 不再返回 0。
- 错误令牌仅 HTTP 401 通过；宿主机标记与容器残留检查要求在执行节点运行；
  CPU 按 quota/period 校验；网络与资源测试要求明确证据。
- 新增 mTLS 客户端证书参数与四项 TLS 验证。
- 管理器测试 112 → **129**（新增 17 项工具可靠性测试）；仍无 Linux 实机验证。

#### 验收证据补强（第八轮已完成）

- 网络判定改为解析容器内结构化 `NET_RESULT`，按 Linux errno 分类：仅
  `ENETUNREACH/EHOSTUNREACH/EACCES/EPERM` 算阻断；`ConnectionRefused`、DNS 失败、
  超时、未知异常一律 FAIL，并输出异常类型与 errno。
- 新增 stdout / stderr 分别提交任务的截断验证（字节数、终态、非空）以及
  stdout+stderr 合计上限检查。
- 新增 `memory.swap.max` 检查与 `--expected-swap-mb`（本项目 memswap==mem，期望 0）；
  `max` 不算有限制，文件不可读 SKIP。
- 新增本地临时 TLS 的 mTLS 六场景测试（合法握手、无证书、不受信客户端证书、
  不受信服务端证书、错误令牌 401、证书私钥不匹配）；证书临时生成并自动清理。
- `--on-execution-node` 明确为人工声明而非密码学证明；文档要求先 SSH 登录执行节点、
  核对管理器/Docker/Socket 同节点，无法确认则 SKIP。
- 管理器测试 129 → **141**（`test_verify_isolation.py` 17 → 29 项）；仍无 Linux 实机验证，
  **S-01 ~ S-15 全部未执行**（**历史状态**；当前已在 WSL2 节点执行并通过，见开篇“当前状态”）。

#### 验收工具最后三项（第九轮已完成）

- **合计输出**：改为同一 Python 任务内同时产生 5MB stdout + 5MB stderr，用该单任务
  两通道字节数之和校验 `--output-total-limit`；不再跨任务相加。
- **节点身份**：新增 `--confirm-manager-docker-same-host` 人工确认；`--on-execution-node`
  + 人工确认 + 本机 Docker 可用三者齐备才通过，否则 SKIP；宿主机标记文件与残留容器
  检查绑定该确认；人工核验不等于密码学证明。
- **mTLS/令牌**：不受信客户端证书改为第二套 CA 签发的正常叶子证书；令牌测试服务端
  真实解析 `X-Sandbox-Token`（正确 200 / 错误 401），用真实 Manager 经 TLS 请求。
- 管理器测试 141 → **147**（`test_verify_isolation.py` 29 → 35 项）；仍无 Linux 实机验证，
  **S-01 ~ S-15 全部未执行**（**历史状态**；当前已在 WSL2 节点执行并通过，见开篇“当前状态”）。

#### 验收判定严谨性收尾（第十轮已完成）

- **输出截断**：新增 `MIN_OUTPUT_RATIO=0.9`，要求实际字节数接近单流上限；合计任务要求
  两通道都接近单流上限且合计接近总上限；明显不足/为空/超容差/合计过低均 FAIL。
- **mTLS 异常区分**：`_handshake` 保留两端异常；无证书与不受信客户端证书须服务端
  证书相关 `SSLError`，不受信服务端证书须客户端 `SSLCertVerificationError`；
  服务端注入的 `RuntimeError` 被保留，不再把任意异常当“握手被拒绝”。
- 管理器测试 147 → **151**（`test_verify_isolation.py` 35 → 39 项）；仍无 Linux 实机验证，
  **S-01 ~ S-15 全部未执行**（**历史状态**；当前已在 WSL2 节点执行并通过，见开篇“当前状态”）。

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

## 本机 WSL2 实机验收结果（2026-11-13）

已完成：
1. 本机 WSL2（WSL 3.0.5 + Ubuntu 24.04 + Docker Engine 29.1.3）部署沙箱管理器。
2. 因 Docker Hub 不可达，镜像改为**本地构建 + 本地 Image ID 固定**（`sha256:f6ce001f…`）。
3. `verify_isolation.py` 实跑：**27 项 FAIL 0 / SKIP 0 / PASS**；S-14 另行实测通过。
4. 修复两处：
   - `verify_isolation.py` mTLS 负向判定适配 TLS 1.3（`RemoteDisconnected` 且零 HTTP 响应也算服务端拒绝）。
   - `runner.py` 输出改 attach 实时读取 + 有界缓冲，解决 json-file 轮转导致输出丢失。
5. 管理器用例 151 → 158。

## 第十一轮：attach 部分读取异常修复（2026-11-13）

- 问题：attach 读到部分输出后抛异常时，旧逻辑只在“两通道都为空”才回退，
  其余情况会把**部分输出当作完整结果**返回并标记 `succeeded`。
- 修复：
  - 未读到任何数据 → 才允许回退 `docker logs`，且回退失败抛 `output_capture_failed`；
  - 已读到部分数据后中断 → 直接 `output_capture_failed`，丢弃部分输出；
  - 读取线程有界等待（10s + 关闭流后 5s），仍不退出 → `output_capture_failed` 并回收容器；
  - `_logs()` 改为失败即抛 `_OutputCaptureError`，不再用空字符串掩盖读取失败。
- 新增 6 项回归测试，管理器用例 158 → **164**。

## 第十二轮：读取线程残留边界确认（2026-11-13）

- 实测 Docker SDK 7.2.0：`container.attach(stream=True, demux=True)` 返回
  `CancellableStream`，其 `close()` 会对底层 socket 执行 `shutdown(SHUT_RDWR)` + `close()`，
  可解除另一线程中阻塞的 `next()`（实测线程随即退出）。
- 代码调整：容器结束后读取线程仍未结束 → 关闭流 + 有界等待，**即使随后退出也判
  `output_capture_failed`**，不再可能把不完整输出当成功；容器回收后再 join 一次，
  仍存活则记录 daemon 线程残留警告。
- 未升级 Docker SDK，未使用私有字段或异步异常注入。
- 残留边界：Python 线程无法强制终止；上述 close 行为不构成跨版本保证，
  极端情况下 daemon 线程可能残留至进程退出（不写后续任务结果、不影响容器清理）。
- 新增 4 项测试并强化 1 项，管理器用例 164 → **168**。

## R-06 桌面端 GUI / UIA / 悬浮层实机点验（2026-11-13）

- 环境：Windows 11 开发机，Python 3.13.12，PySide6 6.12.0；测试进程 **PID 7556**。
- 方式：pywinauto（UIA）驱动真实控件 + 全屏截图逐像素取证；**后端 8000 未启动**。
- **主路径 PASS**：启动与主窗口、UIA 控件树、悬浮层置顶/工具窗口/鼠标穿透、
  气泡显示与隐藏、位置切换、透明度 100%/70%/30%、开始/暂停观察、
  托盘图标注册与右键菜单、`WM_CLOSE` 后进程存活。
- **INCOMPLETE（未完成，不得写成通过）**：
  1. 绿色目标框端到端：后端未启动，主程序拿不到 `target`；仅完成 `GuideOverlay`
     独立渲染验证（绿框像素 4942 → `clear_target` 后 1），**不是端到端验收**。
  2. 托盘双击恢复主窗口：自动化点击被同区域其他托盘图标抢占，未稳定复现，需人工点验。
- 非缺陷：Edge（`msedge.exe`）窗口「可识别控件」为 0 属窗口状态 / UIA 可见性结果，
  不是本次改动引入的缺陷。
- 详细记录见 `TEST_REPORT.md` §15。

仍需完成（生产口径）：
1. 在独立 Linux 生产节点（含 AppArmor / 可选 gVisor）复跑 S-01~S-15。
2. 使用正式 registry 镜像 digest（非本地 Image ID）。
3. 多实例清理隔离、Docker 故障注入、真实网络拓扑验证。
4. WSL2 结论**不得**当作生产验收通过。
