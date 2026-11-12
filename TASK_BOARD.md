# 任务看板

## 当前阶段：阶段 0 — 项目接入与现状盘点（已基本完成，有 1 项待确认）

### P0：必须先完成

- [x] 检查 Trae 当前打开的项目目录与 Git 状态。
  - 证据：工作区 `c:\Users\wyy\Desktop\GitHub-chatgpt-tare` 已成功 clone 远程仓库，`git status -sb` 输出 `## trae-dev...origin/trae-dev`，工作区干净。
- [x] 判断本地是否已有项目代码；若有，列出目录结构、主要模块和入口文件。
  - 证据：工作区内（远程仓库内容）**只有 9 份协作文档 + README，无任何业务代码**。
    真实代码位于 `C:\Users\wyy\Desktop\sxzd`，但该目录**不是 Git 仓库**。详见 TEST_REPORT.md T-02 / T-03。
- [x] 对比本地目录与 GitHub 远程仓库，确认是否存在未提交/未推送内容。
  - 证据：`git ls-tree -r --name-only origin/main` 仅 `README.md`；`origin/trae-dev` 为 9 份文档。
    本地 `sxzd` 的 backend/frontend/desktop/scripts/experiment_packs 全部**未进入远程仓库**。
- [x] 检查是否包含密钥、Token、Cookie、个人数据、数据库文件或大体积产物。
  - 证据：`C:\Users\wyy\Desktop\sxzd\backend\.env` 含真实 `AI_API_KEY`、`JWT_SECRET_KEY`；
    `ai_review\backend\.env` 是**第二份带密钥的副本**；另有 `zd_shixun.db`（真实用户数据）、
    `node_modules` 310.6 MB、`ai_review` 329.3 MB、`docs` 10.9 MB 图片、`dist` 6.8 MB。
    当前仓库内**无**任何密钥（已核对 trae-dev 文件清单）。
- [x] 识别项目使用的语言、框架、依赖和启动方式。
  - 详见 TASK_BOARD 下方「技术栈摘要」与 TEST_REPORT.md T-04 / T-05。
- [x] 在不修改业务代码的前提下，尝试运行现有项目并记录结果。
  - 证据：后端实启成功、`/health` 返回 ok、OpenAPI 23 条路由；前端 `vue-tsc` 退出码 0；
    桌面端离屏导入成功（GUI 未实际弹出）。详见 TEST_REPORT.md T-06 ~ T-08。
- [x] 输出项目盘点报告与建议的下一阶段任务。
  - 证据：见 NEXT_STEPS.md 与 CHANGELOG.md 2026-11-12 条目。

### 阻塞项（需项目负责人确认，Trae 不擅自处理）

- [ ] **B-01 本地代码是否迁入仓库、以什么顺序迁入。**
  远程仓库当前为空壳；本地 `sxzd` 是唯一真实代码来源。迁入涉及 300 MB+ 依赖与二进制产物、
  两份带密钥的 `.env`、真实用户数据库，必须先剔除再提交。**需明确授权后再执行。**
- [ ] **B-02 敏感文件清理策略。** `ai_review/` 目录整体是待清理的审核快照（内含 `.env`、`*.db`、
      `uvicorn.log`、`child_log.txt`），不建议入库；是删除、还是纳入 `.gitignore` 后保留在本地？
- [ ] **B-03 main 与 trae-dev 的合并节奏。** main 仍停在 `11698fa`（只有 README），
      trae-dev 已领先 8 个文档提交。是否把协作文档同步回 main，需负责人决定（本轮不动 main）。

### P1：盘点通过后再做

- [ ] 确定首版 MVP 范围和可验收演示流程。
- [ ] 确定前后端/桌面助手的模块边界。
- [ ] 建立最小可运行开发环境和基础测试（当前**零自动化测试**）。
- [ ] 按确认后的方案分阶段实现，不进行无必要的大规模重构。

## 技术栈摘要（来自本地实盘，非文档推测）

| 端 | 技术 |
|---|---|
| backend | Python 3.13、FastAPI、SQLAlchemy 2、SQLite、python-jose(JWT)、bcrypt、httpx |
| frontend | Vue 3.5 + TypeScript + Vite 4、Element Plus、Pinia、Vue Router、Monaco、ECharts |
| desktop | PySide6(Qt6)、comtypes/IUIAutomation、pywin32、mss、WGC 截图、httpx（**仅 Windows**） |

## 任务状态说明
- 待办：尚未开始
- 进行中：正在开发
- 阻塞：缺少信息/环境/权限
- 完成：有代码、测试或可复现证据支持

每项任务完成时，补充负责人、改动文件、验证方式和结果。
