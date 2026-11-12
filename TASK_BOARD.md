# 任务看板

## 当前阶段：阶段 1 — 建立现有项目代码基线（已完成，待验收）

### 阶段 1 任务

- [x] 备份/确认原项目可恢复，不删除原目录。
  - 证据：迁移全程为**只读复制**，`C:\Users\wyy\Desktop\sxzd` 未被修改、未被删除；
    `ai_review/` 按要求保留在本地且已加入 `.gitignore`。
- [x] 确认工作分支为 `trae-dev`。
  - 证据：`git branch --show-current` = `trae-dev`，`git status -sb` = `## trae-dev...origin/trae-dev`。
- [x] 对比本地与远程差异，不覆盖已有代码。
  - 证据：远程仅有 9 份协作文档 + README；代码目录（backend/frontend/desktop/scripts 等）在远程**不存在**，
    无路径冲突。唯一被覆盖的是 `README.md`（按要求重写）与 `.gitignore`（按要求扩充）。
- [x] 完善 `.gitignore`。
  - 证据：新增 `ai_review/`、`.screenshots/`、`docs/*.png`、`*.tsbuildinfo`、
    `frontend/vite.config.js`、`frontend/vite.config.d.ts` 等规则。
- [x] 迁入 backend、frontend、desktop、scripts、experiment_packs。
  - 证据：共 111 个待提交文件（含 `demo_shots/` 6 张产品截图、`docs/` 2 个文本文件）。
- [x] 生成安全 `.env.example`（仅变量名 + 占位值）。
  - 证据：`backend/.env.example` 补入 `ADMIN_USERNAME` / `ADMIN_PASSWORD` / `ALLOW_PUBLIC_REGISTER`，
    密钥项全部为占位值；`frontend/.env.example` 无敏感项。
- [x] 完善 README（三端安装、启动、环境变量、Windows 限制）。
  - 证据：`README.md` 已重写为 12 节完整说明。
- [x] 检查硬编码密钥、默认弱密码、真实账号、数据库、个人数据。
  - 证据：**发现并修复** 5 个脚本硬编码的真实 NVIDIA API Key（改为读取 `NV_API_KEY` 环境变量）；
    清理 4 个脚本中的个人绝对路径；`*.db`、`.env`、`ai_review/` 均未入库。
    遗留：`backend/app/core/config.py` 的 `admin_password="demo123"` 与
    `desktop/src/network/api_client.py` 的 `auto_login("admin","demo123")` 仍为弱默认值（未改动代码，见风险清单）。
- [x] 后端启动、前端类型检查、桌面端导入检查。
  - 证据：见 `TEST_REPORT.md` T-09 ~ T-12。
- [x] 干净环境验证。
  - 证据：后端在独立 venv + 全新目录启动成功并可登录；前端在全新目录 `npm ci` 后类型检查通过。
- [x] 推送前执行文件清单与敏感信息扫描。
  - 证据：`git status --porcelain -uall` 111 项，敏感文件正则匹配 0 命中。
- [x] 提交并推送到 `origin/trae-dev`。
  - 证据：提交 SHA 见下方「提交记录」。

## 提交记录

| 提交 | 内容 |
|---|---|
| `0293b69` | 阶段 0 盘点文档 |
| `3032872` | `feat: import existing project code baseline`（111 files, +11389） |
| 本条文档提交 | `docs: record stage-1 baseline import` |

## 遗留问题（需负责人决策）

- [ ] **R-01 弱默认密码**：后端 `admin_password` 默认 `demo123`；桌面端 `auto_login` 内置 `admin/demo123`。
      建议改为首次启动强制改密 + 桌面端不再内置默认凭据。涉及业务代码，本轮未改。
- [ ] **R-02 SQLAlchemy 版本上限**：`requirements.txt` 仅写 `>=2.0.35`，实测会装到 2.1.8；
      在开启应用控制策略的机器上其 C 扩展会被拦截。建议评估是否收敛到 `>=2.0.35,<2.1`。
- [ ] **R-03 `docs/*.png`**：11 张调试截图（10.87 MB）含个人桌面内容，已排除入库；如需文档配图需重新截图。
- [ ] **R-04 自动化测试**：仍为 0，`scripts/test_*.py` 是调试脚本，不可作为回归。
- [ ] **R-05 `POST /code/run` 无沙箱**：可执行任意 Python，属高危。

## 任务状态说明
- 待办：尚未开始
- 进行中：正在开发
- 阻塞：缺少信息/环境/权限
- 完成：有代码、测试或可复现证据支持
