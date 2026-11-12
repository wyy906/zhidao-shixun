# 下一步

## 现状一句话

代码基线已入库，后端 53 项 pytest 与前端 `npm test` 全部通过；回归网已建立，
下一步可以开始处理**已知风险**（第一优先是 `/code/run` 无沙箱与弱默认密码）。

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
| R-05 | `POST /code/run` 无沙箱，可执行任意 Python | 阶段 3 最高优先 |
| R-06 | 桌面端 GUI/UIA/悬浮层仍未实跑验证 | 需人工点验 |

---

## 阶段 3：风险治理与工程化（建议下一轮）

1. **P0 `/code/run` 沙箱化**：子进程权限、超时与内存上限、危险模块黑名单；或明确禁用公网部署。
2. **P0 凭据治理**：修复 R-01；确认 `AI_API_KEY` 只存在于本地 `.env`。
3. **P1 数据库迁移**：`alembic` 目前只有 `env.py`，补首个 revision，结束 `create_all` 与迁移双轨。
4. **P1 导入校验**：`POST /experiments/import` 的 `adapter` 结构弱校验，错误会延迟到桌面端才暴露。
5. **P1 桌面端拆分**：`desktop/src/ui/main_window.py` 偏大，按「窗口选择 / 实验驱动 / 教程 / 悬浮层」拆分。
6. **P2 体验**：Monaco 懒加载（当前约 3.3 MB）；桌面端补断线重连提示。

## 阶段 4：MVP 演示闭环（需产品确认范围）

- 一个网页内 Python 实验 + 一个外部软件实验（MySQL Workbench 需先确认环境可用）。
- 能识别当前步骤与完成状态，给出逐步指导、错误提示与结果验证，并留存过程记录。

## 测试维护约定

- 新增接口或修改业务规则时，必须同步补 `backend/tests/` 用例。
- 用例不得依赖网络、真实 AI Key、真实数据库。
- `pytest` 出现失败时先判断是代码缺陷还是用例过期，**不得通过删断言或 skip 变绿**。
