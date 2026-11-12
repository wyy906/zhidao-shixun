# 更新记录

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
