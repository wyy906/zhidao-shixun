# 下一步

## 现状一句话

后端 70 项 pytest、沙箱管理器 71 项单元测试、前端 `npm test` 全部通过；
学生代码已改为「独立 Linux 执行节点 + 一次性 Docker 容器」执行，业务后端不再持有本机执行路径。
已完成安全审查问题修复（镜像 digest、HTTPS、容器配置回查、清理与迁移）。
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
  后端增至 **70**、管理器增至 **71**。
- 部署与验证：见 `SANDBOX_DEPLOYMENT.md`、`sandbox_manager/scripts/verify_isolation.py`。

#### 安全审查修复（已完成）

- 修正镜像 digest 校验：Registry Manifest Digest 与 Image ID 分开处理（`image_verify.py`）。
- 生产强制 HTTPS，支持双向 TLS；证书缺失/不可读/不成对时拒绝启动；
  明文 HTTP 仅限显式开发开关 + 回环地址，无自动降级。
- 容器创建后完整回查运行用户、tmpfs 容量与选项、日志驱动/上限、端口映射、设备挂载、
  资源限制、运行时与镜像，不符即删除容器并拒绝执行。
- 管理器启动时清理 `zd.sandbox=1` 残留容器；取消/超时/启动失败清理均有测试。
- 新增 `code_tasks` 正式 Alembic 迁移；请求模型禁止额外字段；错误响应不回显令牌/路径。
- 测试增加：后端 67 → **70**，管理器 35 → **71**。

> ⚠️ 开发机为 Windows 且无 Docker，**容器隔离能力未实机验证**。在负责人完成 Linux 节点验收前，
> 不得对外宣称沙箱已通过安全验收。

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
