# 测试报告

## 当前基线

- 日期：2026-11-12
- 分支：trae-dev（commit `adfa581`，跟踪 `origin/trae-dev`）
- 工作区：`c:\Users\wyy\Desktop\GitHub-chatgpt-tare`（clone 自 `https://github.com/wyy906/zhidao-shixun.git`）
- 被测代码：`C:\Users\wyy\Desktop\sxzd`（本地目录，**非 Git 仓库**；远程仓库内无业务代码）
- 操作系统：Windows / Python 3.13.14 / Node v26.13.0 / npm 11.20.0 / Git 2.56.0
- 总体结论：**代码基线已入库并完成三端验证**；后端/前端/桌面端均能在干净环境建立并通过启动或导入检查，
  项目仍**没有自动化测试套件**。

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

## 阶段 1 复验（代码基线迁入后，2026-11-12）

基线提交：`3032872`（111 files changed, 11389 insertions）

### T-09 敏感信息扫描与脱敏

- 环境：仓库工作区，扫描 `git diff --cached` 全量新增内容
- 命令/操作：正则匹配 `nvapi-` / `sk-` / `ghp_` / `AKIA` / `C:\\Users\\` / `c:/Users/`
- 预期结果：0 命中
- 实际结果：**首次扫描命中严重问题**——5 个脚本硬编码了真实 NVIDIA API Key
  （`check_nv_models.py`、`test_model_access.py`、`test_model_compare.py`、`test_visual_api.py`、`test_nv_vl.py`），
  另有 4 个脚本硬编码个人绝对路径 `c:/Users/wyy/Desktop/sxzd/backend`。
  已全部改为读取 `NV_API_KEY` 环境变量与相对路径（`Path(__file__).resolve().parent.parent`）。
  复扫结果：`NO MATCH`。
- 结论：**通过（问题已修复后再提交）**
- 证据：修复后暂存内容扫描 0 命中；敏感文件名匹配（`.env` / `*.db` / `*.log` / `node_modules` / `dist`）为 `NONE`

### T-10 后端（干净环境）

- 环境：仓库副本 `C:\Users\wyy\.zd_baseline_be`，**全新 venv**，无 `.env`、无数据库
- 命令/操作：`pip install -r requirements.txt` → `uvicorn app.main:app --port 8012` →
  请求 `/health`、`/openapi.json`、`POST /api/v1/auth/login`、无 token 访问 `/api/v1/experiments`
- 预期结果：可启动、可登录、鉴权生效
- 实际结果：
  - `pip install` 成功；但 SQLAlchemy 解析到 **2.1.8**，其 C 扩展 `_collections_cy.pyd` 被本机
    应用控制策略拦截（`ImportError: DLL load failed while importing _collections_cy`）。
    回退 `sqlalchemy==2.0.36` 后正常。**属主机策略限制，非代码问题**。
  - 启动成功，`/health` = `{"status":"ok","app":"智导实训"}`，OpenAPI **23 条路由**
  - 首次启动自动建表 + 创建管理员；`admin/demo123` 登录返回 **200**
  - 无 token 访问 `/api/v1/experiments` 返回 **401**
  - 启动时正确输出警告：「JWT_SECRET_KEY 仍为默认值，仅可用于本地开发」
- 结论：通过
- 证据：uvicorn 日志、health 响应、登录响应体、401 状态码

### T-11 前端（干净环境）

- 环境：全新目录（无 `node_modules`），从 `package-lock.json` 安装
- 命令/操作：`npm ci` → `npx vue-tsc --noEmit`
- 预期结果：依赖安装成功且类型检查无错误
- 实际结果：`added 115 packages in 9s`；`vue-tsc` 退出码 **0**
- 结论：通过
- 证据：命令输出

### T-12 桌面端（干净环境）

- 环境：仓库副本独立 venv，安装 `desktop/requirements.txt`（PySide6 6.12.0、pywinauto 0.6.9、comtypes 1.5.0、mss 10.2.0、pywin32 312）
- 命令/操作：`QT_QPA_PLATFORM=offscreen` 下导入 `src.ui.main_window`、`src.core.uia`、
  `src.core.screen`、`src.overlays.annotation`、`src.network.api_client`、`src.config.settings`
- 预期结果：无导入错误
- 实际结果：`desktop clean import ok`
- 结论：通过（**导入级**）
- 未覆盖：GUI 实际弹出、UIA 取控件、窗口枚举、截图链路、悬浮层绘制。原因：会接管用户桌面并弹全屏悬浮层，需人工在场验证。

### T-13 仓库整洁性

- 环境：仓库工作区
- 命令/操作：`git status --porcelain -uall` 全量统计 + 敏感文件名匹配
- 预期结果：仅包含源码与文档
- 实际结果：111 个文件；`backend 42 / frontend 24 / desktop 18 / scripts 16 / demo_shots 6 / docs 2 / experiment_packs 1`
  （另 `.gitignore`、`README.md` 为修改）。无 `.env`、`*.db`、`*.log`、`node_modules`、`dist`、`*.tsbuildinfo`
- 结论：通过

### T-14 启动脚本缺陷（已修复）

- 环境：`scripts/start-backend.ps1`、`scripts/start-frontend.ps1`
- 命令/操作：静态审阅路径拼接
- 预期结果：脚本能从任意工作目录定位到 backend/frontend
- 实际结果：原代码 `Set-Location "$PSScriptRoot\backend"` 指向 `scripts\backend`（不存在），
  两处均已改为 `$PSScriptRoot\..\backend` / `..\frontend`
- 结论：**通过（缺陷已修复）**
- 未覆盖：脚本会安装依赖并长驻前台，未实际执行

## 阶段 2：最小自动化测试体系（2026-11-12）

### 测试环境

| 项 | 值 |
|---|---|
| Python | 3.13.14 |
| pytest | 8.3.4 |
| FastAPI | 0.115.6 |
| SQLAlchemy | 2.0.36 |
| httpx | 0.28.1 |
| 前端 | TypeScript 5.9.3 + vue-tsc 2.2.12 |
| 网络 | **不需要**（无外部调用） |
| AI Key | **不需要**（不触发任何 AI 接口） |

### 数据库隔离验证（实测）

三层隔离同时生效：

1. `conftest.py` 在**导入 app 之前**设置 `DATABASE_URL` 指向一次性临时文件；
2. 每个测试用 `tmp_path` 新建独立 SQLite；
3. `app.dependency_overrides[get_db]` 替换为测试会话。

实测连接路径：

```
[隔离检查] 全局 engine 实际连接: sqlite:///C:/Users/wyy/AppData/Local/Temp/zd_shixun_test_guard_audmw42g/guard.db
[隔离检查] 本次测试库连接: sqlite:///C:/Users/wyy/AppData/Local/Temp/pytest-of-wyy/pytest-2/.../test.db
```

- 仓库内 `Get-ChildItem -Recurse -Filter *.db` 结果为空，**未生成/修改任何真实数据库**。
- `TestClient` 未使用 `with`，不触发 lifespan 的建表与建管理员逻辑。

### 用例统计与结果

| 文件 | 用例数 | 通过 | 失败 |
|---|---|---|---|
| `tests/test_auth.py` | 12 | 12 | 0 |
| `tests/test_experiments.py` | 16 | 16 | 0 |
| `tests/test_progress.py` | 11 | 11 | 0 |
| `tests/test_report.py` | 10 | 10 | 0 |
| **合计** | **49** | **49** | **0** |

```
python -m pytest -q   →   49 passed, 232 warnings in 36.96s
npm test              →   exit 0
```

> 232 条 warning 全部是 `datetime.utcnow()` 的 DeprecationWarning（见 D-08），不影响结果。

### 测试发现的缺陷

| 编号 | 缺陷 | 位置 | 处理 |
|---|---|---|---|
| D-01 | `POST /experiments/{id}/step` 不校验步骤序号范围，`step_index=999` 或 `-1` 都会被接受并写入 `completed_steps` | `experiments.py` `update_step_progress` | **已修复**：超出 `0..len(steps)-1` 返回 400，并补回归用例 |
| D-02 | 对**不存在**的实验调用 `/step`、`PUT /report`、`POST /report/submit` 会创建指向不存在实验的孤儿进度行 | `experiments.py` `_get_or_create_progress` 调用点 | **已修复**：先查实验，不存在返回 404，并补回归用例 |
| D-03 | `overwrite=False` 时同标题实验可重复导入，产生多个同名实验 | `experiments.py` `import_experiment` | **已记录**（业务规则，需负责人确认是否应拒绝） |
| D-04 | 没有教师查看/批阅学生报告的接口，`GET /{id}/report` 只返回当前登录者自己的报告 | `experiments.py` 报告接口 | **已记录**（需新增功能，本轮不实现） |
| D-05 | 报告存在但六个字段全为空时，`POST /report/submit` 仍可提交成功 | `experiments.py` `submit_report` | **已记录**（业务规则，需确认「空报告」定义） |
| D-06 | `GET /experiments/{id}` 与 `GET /experiments/{id}/steps` **无鉴权**，未登录即可读取实验内容 | `experiments.py` | **已记录**（涉及权限策略，需负责人确认） |
| D-07 | 覆盖导入会删除同标题旧实验，连带删除学生已有进度、报告与操作记录（数据不可恢复） | `experiments.py` `import_experiment` | **已记录**（产品行为，需确认是否应改为「保留进度」） |
| D-08 | 全量使用 `datetime.utcnow()`，触发 DeprecationWarning，未来版本将移除 | 多个 router | **已记录**，不影响当前功能 |

> 未通过删除断言、放宽预期或跳过用例来制造全绿：首轮运行是 `3 failed, 46 passed`，
> 修复 D-01、D-02 后复跑才达到 `49 passed`。

## 本机环境限制（影响复现）

- 全局 Git 配置存在 `url.https://ghfast.top/https://github.com/.insteadOf=https://github.com/`，
  所有 GitHub 请求被改写到镜像代理；若代理不可用会导致 clone/push 失败，需注意。
- 本机无 `gh` CLI、无 credential helper、无 `GH_TOKEN`/`GITHUB_TOKEN`，**推送需要凭据**。
- 本机启用应用控制策略：新建虚拟环境中带 C 扩展的 `.pyd`（实测 SQLAlchemy 2.1.8 的 `_collections_cy.pyd`）
  会被拦截，需回退到纯 Python 可用的版本才能导入；该限制不影响已安装的全局环境。
- 后端与桌面端依赖安装在系统 Python 中，未使用虚拟环境，版本漂移风险较高。

## 后续测试记录模板
### 测试项
- 环境：
- 命令/操作：
- 预期结果：
- 实际结果：
- 结论：通过 / 失败 / 阻塞
- 证据（日志、截图或测试输出）：
