# 测试报告

## 当前基线

- 日期：2026-11-12
- 分支：trae-dev（commit `adfa581`，跟踪 `origin/trae-dev`）
- 工作区：`c:\Users\wyy\Desktop\GitHub-chatgpt-tare`（clone 自 `https://github.com/wyy906/zhidao-shixun.git`）
- 被测代码：`C:\Users\wyy\Desktop\sxzd`（本地目录，**非 Git 仓库**；远程仓库内无业务代码）
- 操作系统：Windows / Python 3.13.14 / Node v26.13.0 / npm 11.20.0 / Git 2.56.0
- 总体结论：**后端与前端可运行，桌面端仅通过导入级验证，项目无任何自动化测试。**

> 说明：以下每条结果均为本轮实际执行所得。未执行的项明确标注「未执行」，不做推测性「通过」结论。

---

## T-01 仓库克隆与分支

- 环境：Windows PowerShell，Git 2.56.0
- 命令/操作：`git clone https://github.com/wyy906/zhidao-shixun.git .` → `git checkout trae-dev`
- 预期结果：克隆成功并检出 trae-dev
- 实际结果：成功。`git status -sb` = `## trae-dev...origin/trae-dev`，无未提交改动。
- 结论：通过
- 证据：
  - `origin/main` = `11698fa`，仅含 `README.md`
  - `origin/trae-dev` = `adfa581`，含 `.gitignore`、`CHANGELOG.md`、`DECISIONS.md`、
    `NEXT_STEPS.md`、`PROJECT_CONTEXT.md`、`README.md`、`TASK_BOARD.md`、`TEST_REPORT.md`、`TRAE_START_HERE.md`
  - 远程**不含** `backend/`、`frontend/`、`desktop/` 等任何业务代码

## T-02 本地项目身份确认

- 环境：本机文件系统（只读检查）
- 命令/操作：检查工作区目录、桌面候选目录的 `.git` 与 README
- 预期结果：找到智导实训的真实代码
- 实际结果：当前工作区为空壳仓库；`C:\Users\wyy\Desktop\sxzd` 为项目本体
  （README 标题「智导实训 —— AI 视觉感知与实时操作引导平台」，
  含 `backend/ frontend/ desktop/ scripts/ experiment_packs/ docs/ ai_review/ zd_shixun.db`）。
  该目录 `Test-Path .git` = **False**，`git status` 报 `not a git repository`。
- 结论：通过（身份确认），但**代码未接入 Git**
- 证据：`sxzd` 目录列表、`backend` 下仅 `alembic/ app/`（无 `.venv`）

## T-03 敏感信息与大体积产物扫描

- 环境：本机文件系统（只读取键名与体积，未读取密钥内容）
- 命令/操作：解析 `backend/.env` 的键名；统计目录体积
- 预期结果：识别不得入库的内容
- 实际结果：发现以下**必须排除**项
  - `sxzd\backend\.env`：含 `AI_API_BASE_URL` / `AI_API_KEY`(70 字符) / `JWT_SECRET_KEY`(55 字符)
  - `sxzd\ai_review\backend\.env`：**同一套密钥的第二份副本**
  - `sxzd\zd_shixun.db`、`sxzd\backend\zd_shixun.db`、`sxzd\ai_review\backend\zd_shixun.db`：真实数据库（含用户数据）
  - `sxzd\ai_review\` 内 `uvicorn.log`、`child_log.txt`、`frontend\build.log`、`npm-install.log`、`vite.log`
  - 体积：`node_modules` 310.6 MB、`ai_review` 329.3 MB、`docs` 10.9 MB（PNG 截图）、`frontend\dist` 6.8 MB
- 结论：**风险（未修复，等待授权）**
- 证据：`.env` 键名与长度统计；目录体积统计。当前远程仓库内无密钥，无泄露。

## T-04 依赖可用性

- 环境：系统全局 Python（无虚拟环境）
- 命令/操作：`python -c "import fastapi, sqlalchemy, pydantic_settings, jose, bcrypt, httpx"`
  及 `PySide6, mss, PIL, comtypes, pywinauto, win32gui`
- 预期结果：全部可导入
- 实际结果：全部可导入（backend 与 desktop 依赖均已安装）
- 结论：通过
- 证据：两条命令均返回 ok

## T-05 前端依赖与类型检查

- 环境：`C:\Users\wyy\Desktop\sxzd\frontend`，node_modules 已存在
- 命令/操作：`npx vue-tsc --noEmit`
- 预期结果：无类型错误
- 实际结果：退出码 0，无输出
- 结论：通过
- 证据：`EXIT=0`

## T-06 后端启动冒烟测试

- 环境：`C:\Users\wyy\Desktop\sxzd\backend`，通过环境变量
  `DATABASE_URL=sqlite:///./_smoke_test.db` 指向临时库，**未触碰原 `zd_shixun.db`**；
  监听 `127.0.0.1:8011` 避开默认 8000 端口占用
- 命令/操作：`python -m uvicorn app.main:app --host 127.0.0.1 --port 8011`，
  随后请求 `/health` 与 `/openapi.json`
- 预期结果：启动成功并可响应
- 实际结果：启动成功（`Application startup complete`）；
  `/health` 返回 `{"status":"ok","app":"智导实训"}`；
  OpenAPI 暴露 **23 条路由**（auth 3 / experiments 9 / progress 1 / ai 5 / code 1 / analytics 3 / health 1）
- 结论：通过
- 证据：uvicorn 日志 + health 响应 + 路由清单；测试结束后已删除临时 db 与日志，进程已停止。

## T-07 桌面端模块导入

- 环境：`C:\Users\wyy\Desktop\sxzd\desktop`，`QT_QPA_PLATFORM=offscreen`
- 命令/操作：导入 `src.ui.main_window`、`src.core.uia`、`src.core.screen`、
  `src.overlays.annotation`、`src.network.api_client`
- 预期结果：无导入错误
- 实际结果：`desktop modules import ok`
- 结论：通过（**仅导入级**）
- 证据：命令输出
- 未覆盖：GUI 实际弹出、悬浮层绘制、UIA 取控件、窗口枚举、截图链路均**未执行**。
  原因：会在用户桌面弹出全屏透明悬浮层并接管窗口枚举，需用户在场并授权后手工验证。

## T-08 自动化测试

- 环境：全项目
- 命令/操作：检索 `test_*.py` / `*_test.py`，检查是否存在 pytest / vitest 配置
- 预期结果：存在可重复执行的测试套件
- 实际结果：**不存在**。命中项均为一次性调试脚本
  （`scripts/test_model_access.py`、`test_screen_guide.py`、`test_full_chain.py` 等 10 个），
  以及 `ai_review/backend/test_flow.py` 等 3 个游离脚本；无 `pytest.ini`/`conftest.py`/`vitest.config`，
  `frontend/package.json` 中无 test script
- 结论：**失败（无测试基线）**
- 证据：文件检索结果 + `frontend/package.json` scripts 仅 dev/build/preview/type-check

---

## 本机环境限制（影响复现）

- 全局 Git 配置存在 `url.https://ghfast.top/https://github.com/.insteadOf=https://github.com/`，
  所有 GitHub 请求被改写到镜像代理；若代理不可用会导致 clone/push 失败，需注意。
- 本机无 `gh` CLI、无 credential helper、无 `GH_TOKEN`/`GITHUB_TOKEN`，**推送需要凭据**。
- 后端与桌面端依赖安装在系统 Python 中，未使用虚拟环境，版本漂移风险较高。

## 后续测试记录模板
### 测试项
- 环境：
- 命令/操作：
- 预期结果：
- 实际结果：
- 结论：通过 / 失败 / 阻塞
- 证据（日志、截图或测试输出）：
