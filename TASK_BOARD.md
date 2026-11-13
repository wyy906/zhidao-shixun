# 任务看板

## 当前阶段：阶段 4 — MVP 全项目盘点与演示闭环（进行中）

### 阶段 4 任务

- [x] **MVP 全项目盘点**（2026-11-13）：模块清单、完成度、Stub 与风险分级已输出，未改代码。
- [x] **M1 演示闭环：PASS**（2026-11-13 本机 Windows 11 + WSL2 Docker）
  - 教师导入实验 → 学生登录/开始/7 步完成 → 真实沙箱运行代码（exit 0，297ms）→ 报告提交
    → 教师统计 1 学生 / 100% 完成率；前端学生端与教师端界面均 PASS，控制台无报错。
  - 证据：`TEST_REPORT.md` §16；`%TEMP%\m1\m1_result.json`。
  - 边界：本机演示拓扑（WSL 中继），**不等同生产验收**。
- [x] **M2 可信度：PASS**（2026-11-13）
  - `ResultVerifier` 已接入 python / mysql 适配器的 `validate_result`，适配器异常与未知结果
    不再被当成失败；两个适配器支持显式 `passed/failed` 优先。
  - 错误诊断接入真实 OpenAI 兼容模型，真实调用 7.3s 返回结构化建议；含 30s 超时、
    失败回退、密钥脱敏与日志脱敏。
  - 后端 **139 项测试通过**（新增 23 项）。后端能力已验证，前端尚未接入按钮。
- [ ] **M3 分发：桌面端打包（构建完成，运行验证被环境策略阻塞）**
  - 已产出 `desktop/dist/ZhidaoShixun/`（onedir，268.4 MB）与
    `ZhidaoShixun-win64.zip`（105.6 MB）；构建脚本 `desktop/build_windows.ps1`。
  - 本机启用 Smart App Control，未签名 exe 被拦截（CodeIntegrity 3077/3033），
    **不得写成打包产物已实机运行通过**；待代码签名或受控测试机验证。
- [ ] **M4 生产化**：独立 Linux 节点、正式 digest、AppArmor/gVisor、多实例与故障注入（未开始）。

## 阶段 3-A — 代码执行沙箱与桌面端验收（已完成）

### 阶段 3-A 验收任务

- [x] 沙箱管理器与本机 WSL2 节点 S-01~S-15 实机验收通过（详见 `TEST_REPORT.md` §7.3）。
- [x] **R-06 桌面端 GUI / UIA / 悬浮层实机点验：主路径 PASS**
      （2026-11-13，Windows 11，测试进程 PID 7556；后端 8000 未启动）。
  - 证据：`TEST_REPORT.md` §15。启动与主窗口、UIA 控件树、悬浮层置顶/工具窗口/鼠标穿透、
    气泡显示/隐藏/位置切换/透明度、开始/暂停观察、托盘图标与右键菜单、`WM_CLOSE` 后进程存活。
- [x] **R-06-I1 绿色目标框端到端：PASS**
      （2026-11-13 第二批验证，桌面端 PID 33580 + 后端 8000 + 记事本目标）。
  - 证据：`TEST_REPORT.md` §15.6.1。`POST /ai/screen-guide` 23 次 200、
    绿框标注记事本「添加新标签页」按钮、开关对照像素 1413→40→1413、截图视觉确认。
- [ ] **R-06-I2 托盘双击恢复主窗口：部分验证，需人工最终确认**。
  - 已验证：`tray.py` 代码路径正确；UIA invoke 溢出区图标成功恢复主窗口 1 次（§15.6.2）。
  - 未完成：真实鼠标双击的自动化复现受 Win11 溢出弹窗 UIA 不稳定影响，**不得写成完整通过**。

## 阶段 2 — 最小自动化测试体系（已完成，待验收）

### 阶段 2 任务

- [x] 解决测试数据库隔离（临时 DATABASE_URL + `tmp_path` 独立库 + `dependency_overrides`）。
  - 证据：实测全局 engine 指向 `%TEMP%/zd_shixun_test_guard_*/guard.db`，每个用例指向 `pytest-of-*/test.db`；
    仓库内未生成任何 `.db` 文件。
- [x] 建立 `backend/tests/`：`conftest.py`、`test_auth.py`、`test_experiments.py`、`test_progress.py`、`test_report.py`。
- [x] 后端 **53** 项用例全部通过（`pytest -q`）。
- [x] 配置隔离：新增 `ZD_ENV_FILE`，测试不读取真实 `backend/.env`（4 项验证）。
- [x] 前端新增 `npm test`（vue-tsc），实测退出码 0。
- [x] 修复测试发现的 3 个真实缺陷（D-01 步骤序号越界、D-02 不存在实验写入孤儿进度、D-09 测试可能读真实 .env）。
- [x] 记录 6 个待决策问题（D-03 ~ D-08，见 `TEST_REPORT.md`）。
- [x] 更新 `TEST_REPORT.md` / `NEXT_STEPS.md` / `README.md`。

## 阶段 1 — 建立现有项目代码基线（已完成）

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
