# 测试报告

> 本文件记录「智导实训」的测试基线与历次实测结果。**第 1~7 章为当前状态**，
> 第 8 章为历史演进记录（仅用于追溯，不代表当前状态）。

---

## 1. 当前基线

| 项 | 值 |
|---|---|
| 日期 | 2026-11-12 |
| 分支 | `trae-dev` |
| 仓库内容 | **已包含业务代码**：`backend/`、`frontend/`、`desktop/`、`scripts/`、`experiment_packs/`、`demo_shots/`、`docs/` |
| 后端测试 | **53 项，全部通过**（`backend/tests/`） |
| 前端测试 | **通过**（`npm test` → vue-tsc，退出码 0） |
| 数据库 | 测试使用临时 SQLite，**不接触真实库** |
| 真实 `.env` | 测试**不读取**（`ZD_ENV_FILE` 指向不存在的临时文件） |
| 操作系统 | Windows 10/11，Python 3.13.14，Node v26.13.0 |

## 2. 结论摘要

1. 后端 53 项自动化测试全部通过，覆盖鉴权、实验 CRUD 与导入、进度、报告、配置隔离。
2. 测试在**无网络、无真实 AI Key、无真实数据库、无真实 `.env`** 的条件下可重复运行。
3. 测试过程中发现 8 个问题：**2 个已修复**，**6 个待负责人决策**；1 项（桌面端 GUI）**尚未验证**。
4. 首轮运行结果为 `3 failed, 46 passed`，修复 D-01 / D-02 后复跑才达到全绿——未通过删断言或跳过用例制造绿色。

## 3. 测试环境

| 组件 | 版本 |
|---|---|
| Python | 3.13.14 |
| pytest | 8.3.4 |
| FastAPI | 0.115.6 |
| SQLAlchemy | 2.0.36 |
| httpx | 0.28.1 |
| TypeScript | 5.9.3 |
| vue-tsc | 2.2.12 |

测试依赖声明：`backend/requirements-dev.txt`（`-r requirements.txt` + `pytest>=8.0`）。

## 4. 后端自动化测试（53 项）

### 4.1 用例分布

| 文件 | 用例数 | 通过 | 失败 |
|---|---|---|---|
| `tests/test_auth.py` | 12 | 12 | 0 |
| `tests/test_experiments.py` | 16 | 16 | 0 |
| `tests/test_progress.py` | 11 | 11 | 0 |
| `tests/test_report.py` | 10 | 10 | 0 |
| `tests/test_config_isolation.py` | 4 | 4 | 0 |
| **合计** | **53** | **53** | **0** |

### 4.2 实际执行结果

```
python -m pytest -q
53 passed, 234 warnings in 36.94s
```

> 234 条 warning 全部为 `datetime.utcnow()` 的 DeprecationWarning（见 D-08），不影响结果。

### 4.3 覆盖内容

- **鉴权**：登录成功 / 密码错误 401 / 账号不存在 401 / 无 token 401 / 学生越权 403 / 教师成功；
  响应体不得出现 `hashed_password` 或 bcrypt 哈希。
- **实验**：创建、查询、修改、删除；学生越权全部 403；JSON 导入、步骤顺序与内容、
  `adapter` 提示落库、覆盖导入、覆盖后孤儿数据清理、未知 ID 404、非法载荷 422。
- **进度**：开始、查询、逐步推进、完成最后一步、提交后状态与完成时间、跨学生隔离、
  序号越界 400、未知实验 404。
- **报告**：保存、更新（不新建记录）、查询、提交、无报告提交 400、跨学生隔离、
  删除实验后报告清理、未知实验 404。
- **配置隔离**：env 文件路径指向临时不存在文件、机制生效性、缺失文件不回退真实 `.env`。

## 5. 数据库与配置隔离验证（实测输出）

三层数据库隔离：

1. `conftest.py` 在**导入 app 之前**把 `DATABASE_URL` 指向一次性临时文件；
2. 每个用例用 `tmp_path` 新建独立 SQLite 文件；
3. `app.dependency_overrides[get_db]` 替换为测试会话。

另外，`conftest.py` 在导入 app 前设置 `ZD_ENV_FILE`，使配置加载器指向**不存在**的临时 env 文件。

实测输出：

```
[env 隔离检查] 实际 env 文件: C:\Users\...\Temp\zd_shixun_test_guard_lq7vwcdy\no-such-test.env
[隔离检查] 全局 engine 实际连接: sqlite:///C:/Users/.../Temp/zd_shixun_test_guard_lq7vwcdy/guard.db
[隔离检查] 本次测试库连接: sqlite:///C:/Users/.../pytest-of-wyy/pytest-6/test_each_test_uses_isolated_s0/test.db
```

- 仓库内 `Get-ChildItem -Recurse -Filter *.db` 结果为空：**未生成、未修改任何真实数据库**。
- `TestClient` 未使用 `with`，不触发 lifespan 的建表 / 建管理员逻辑。
- 用户本地 `backend/.env` 不会被读取、不会被修改（测试只做存在性检查）。

## 6. 前端测试

| 项 | 结果 |
|---|---|
| 命令 | `npm test`（等价 `vue-tsc --noEmit`） |
| 退出码 | **0** |
| 覆盖范围 | 仅类型检查；尚未引入 Vitest 组件测试 |

> 注意：需先执行 `npm install`。否则 `npx` 会拉取最新版 TypeScript（6.x），
> 因 `baseUrl` 弃用而误报失败——这不是代码缺陷。

## 7. 问题清单

### 7.1 已修复（含回归用例）

| 编号 | 问题 | 位置 | 修复内容 |
|---|---|---|---|
| D-01 | `POST /experiments/{id}/step` 不校验步骤序号，`step_index=999` 或 `-1` 被接受并写入 `completed_steps` | `backend/app/api/v1/routers/experiments.py` `update_step_progress` | 越界返回 400；`test_step_index_out_of_range_returns_400` |
| D-02 | 对**不存在**的实验调用 `/step`、`PUT /report`、`POST /report/submit` 会创建指向不存在实验的孤儿进度行 | 同上（`_get_or_create_progress` 调用点） | 先查实验，不存在返回 404；2 项回归用例 |
| D-09 | 测试环境可能加载真实 `backend/.env`，从而读到真实 `AI_API_KEY` / `DATABASE_URL` | `backend/app/core/config.py`、`backend/tests/conftest.py` | 新增 `ZD_ENV_FILE` 环境变量；测试指向不存在的临时文件；4 项隔离用例 |

### 7.2 待负责人决策（已记录，未改代码）

| 编号 | 问题 | 影响 | 建议 |
|---|---|---|---|
| D-03 | `overwrite=False` 时同标题实验可重复导入 | 产生多个同名实验 | 按标题去重或返回 409 |
| D-04 | 没有教师查看 / 批阅学生报告的接口，`GET /{id}/report` 只返回当前登录者自己的报告 | 教师无法批阅 | 新增教师只读 / 批阅接口（新功能） |
| D-05 | 报告六个字段全为空时仍可提交成功 | 可提交空报告 | 明确「空报告」判定规则后加校验 |
| D-06 | `GET /experiments/{id}` 与 `GET /experiments/{id}/steps` 无鉴权，未登录可读 | 信息暴露 | 确认是否要求登录 |
| D-07 | 覆盖导入会删除同标题旧实验，连带删除学生进度、报告与操作记录 | 数据不可恢复 | 改为归档 / 保留历史进度 |
| D-08 | 全量使用 `datetime.utcnow()`，触发 DeprecationWarning，未来版本将移除 | 未来兼容性 | 迁移到 `datetime.now(UTC)` |

### 7.3 尚未验证

| 编号 | 项 | 说明 |
|---|---|---|
| R-06 | 桌面端 GUI / UIA / 悬浮层实际运行 | 目前仅完成离屏导入检查；需人工在 Windows 桌面点验 |

## 8. 历史记录（仅追溯，不代表当前状态）

### 8.1 阶段 0：项目接入与现状盘点

当时的事实（**已被后续阶段改变**）：

- Trae 工作区是空目录；真实代码在本地 `C:\Users\wyy\Desktop\sxzd`，且该目录不是 Git 仓库。
- 远程仓库只有 9 份协作文档，**没有任何业务代码**。
- 当时结论为「后端可运行（23 条路由 / `/health` ok）、前端类型检查通过、桌面端仅导入级验证、
  无任何自动化测试」。该结论只对当时快照有效。

阶段 0 的主要产出是把项目接入 GitHub、确认技术栈与风险、建立协作文档体系。

### 8.2 阶段 1：代码基线导入与验证

提交 `3032872`（111 files, +11389）。关键实测结果：

| 项 | 结果 |
|---|---|
| 敏感信息扫描 | 首次命中 5 个脚本硬编码真实 NVIDIA API Key + 4 处个人绝对路径，**脱敏后复扫 0 命中** |
| 后端（干净 venv + 全新目录 + 无 .env / DB） | 启动成功，`/health` ok，23 条路由，自动建表建管理员，`admin` 登录 200，无 token 401 |
| 前端（全新目录 `npm ci`） | 115 packages，`vue-tsc --noEmit` 退出码 0 |
| 桌面端（独立 venv，PySide6 6.12.0） | 6 个模块离屏导入通过（GUI 未实跑） |
| 仓库整洁性 | 无 `.env` / `*.db` / `*.log` / `node_modules` / `dist` |
| 启动脚本 | `start-backend.ps1` / `start-frontend.ps1` 路径少一级，已修正为 `..\backend` / `..\frontend` |

阶段 1 同时确定了 `.gitignore` 规则、安全的 `.env.example` 与 README。

### 8.3 阶段 2：最小自动化测试体系

提交 `09264c5`（12 files, +905/−42）：

- 建立 `backend/tests/`，49 项用例。
- 三层数据库隔离。
- 首轮 `3 failed, 46 passed` → 修复 D-01、D-02 后 `49 passed`。
- 新增 `npm test` 与 `requirements-dev.txt`。

### 8.4 阶段 2 收尾

- 新增 `ZD_ENV_FILE` 配置项，测试彻底不读真实 `.env`。
- 新增 `tests/test_config_isolation.py`（4 项），用例总数由 49 增至 **53**。
- 重写本文件，消除阶段间结论矛盾。

## 9. 本机环境限制（影响复现）

- 全局 Git 配置存在 `url.https://ghfast.top/https://github.com/.insteadOf=https://github.com/`，
  所有 GitHub 请求被改写到镜像代理；代理不稳定时 clone/push 会失败。
- 本机无 `gh` CLI、无 credential helper、无 `GH_TOKEN`/`GITHUB_TOKEN`，推送依赖 Git Credential Manager 登录。
- 本机启用应用控制策略：新建虚拟环境中带 C 扩展的 `.pyd`（如 SQLAlchemy 2.1.8 的 `_collections_cy.pyd`）
  会被拦截，需使用 2.0.x 才能导入；该限制不影响已安装的全局环境。
- 后端与桌面端依赖安装在系统 Python 中，未使用虚拟环境，存在版本漂移风险。

## 10. 复现命令

```powershell
# 后端
cd backend
pip install -r requirements-dev.txt
python -m pytest -q

# 前端
cd frontend
npm install
npm test
```
