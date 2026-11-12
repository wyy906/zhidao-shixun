# 下一步

## 现状一句话

代码基线已入库（`3032872`），后端/前端/桌面端在干净环境均验证通过；仓库里**没有自动化测试**，
下一步应先把回归网建起来，再动业务代码。

---

## 本轮已完成（阶段 1）

- `trae-dev` 上已提交 111 个文件：`backend/`、`frontend/`、`desktop/`、`scripts/`、
  `experiment_packs/`、`demo_shots/`、`docs/`（纯文本）。
- 密钥、数据库、日志、依赖、构建产物、`ai_review/` 全部排除，`.gitignore` 已覆盖。
- 三端干净环境验证通过，详见 `TEST_REPORT.md` T-09 ~ T-14。

## 需要负责人确认的遗留问题

| 编号 | 问题 | 建议 |
|---|---|---|
| R-01 | 后端 `admin_password` 默认 `demo123`；桌面端 `auto_login` 内置 `admin/demo123` | 首次启动强制改密；桌面端不再内置默认凭据 |
| R-02 | `requirements.txt` 只写 `sqlalchemy>=2.0.35`，实测装到 2.1.8 时 C 扩展被主机策略拦截 | 评估收敛为 `>=2.0.35,<2.1`，或改用纯 Python 安装 |
| R-03 | `docs/*.png`（11 张、10.87 MB）含个人桌面内容，未入库 | 如需文档配图，重新截图后入库 |
| R-04 | 无自动化测试 | 阶段 2 解决 |
| R-05 | `POST /api/v1/code/run` 无沙箱，可执行任意 Python | 阶段 3 优先处理 |

---

## 阶段 2：补最小自动化测试（建议下一轮执行）

目标：在**不联网、不依赖真实 AI Key、不碰真实数据库**的前提下可重复运行。

1. **后端 pytest 基线**
   - `tests/conftest.py`：用 `tmp_path` 建临时 SQLite，覆盖 `DATABASE_URL`，提供 `TestClient` 与登录 fixture。
   - `test_auth.py`：登录成功 / 密码错误 401 / 无 token 401 / 学生访问教师接口 403。
   - `test_experiments.py`：CRUD + `import` 导入 + 覆盖导入（检查是否产生孤儿步骤）。
   - `test_progress.py`：开始实验 → 逐步推进 → 最后一步提交。
   - `test_report.py`：学生提交报告、教师批阅。
   - 验收：`pytest -q` 全绿，且断网可跑。
2. **前端**
   - 把 `vue-tsc --noEmit` 固化进 `package.json` 的 `test` 脚本（当前只有 `type-check`）。
   - 验收：`npm test` 退出码 0。
3. **CI（可选）**
   - GitHub Actions：push 到 `trae-dev` 时跑后端 pytest + 前端 type-check。
   - 注意本机 Git 有 `insteadOf` 改写到 `ghfast.top` 的规则，CI 中不要继承该配置。

## 阶段 3：风险与工程化（测试就位后）

1. **P0 `/code/run` 沙箱化**：子进程权限限制、超时与内存上限、危险模块/系统调用拦截。
2. **P0 凭据治理**：R-01 落地；确认 `AI_API_KEY` 只存在于本地 `.env`。
3. **P1 数据库迁移**：`alembic` 目前只有 `env.py`，补首个 revision，结束 `create_all` 与迁移双轨。
4. **P1 导入校验**：`POST /experiments/import` 的 `adapter` 结构弱校验，错误会延迟到桌面端才暴露。
5. **P1 桌面端拆分**：`desktop/src/ui/main_window.py` 已偏大，按「窗口选择 / 实验驱动 / 教程 / 悬浮层」拆分。
6. **P2 体积与体验**：Monaco 懒加载（当前约 3.3 MB）；桌面端补断线重连提示。

## 阶段 4：MVP 演示闭环（需产品确认范围）

- 一个网页内 Python 实验 + 一个外部软件实验（MySQL Workbench 需先确认环境可用）。
- 能识别当前步骤与完成状态，给出逐步指导、错误提示与结果验证，并留存过程记录。
- 验收标准由负责人定义后再拆解为具体任务。
