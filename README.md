# 智导实训

> AI 视觉感知与实时操作引导平台 —— 面向高校多学科数字化实验教学。
>
> 通过视觉感知、操作状态理解与实验流程建模，识别学生当前所处的实验步骤，并像实验指导老师一样给出
> 分步骤解释、操作提示、错误诊断与结果验证。

---

## 1. 架构总览

```
┌──────────────────────────────────────────────────────────────────┐
│                         智导实训 平台                             │
├───────────────────┬───────────────────────┬──────────────────────┤
│  Vue 3 网页端     │   FastAPI 后端        │   PySide6 桌面助手   │
│  教师端 / 学生端  │   业务 + AI 实训引擎  │   透明悬浮标注层     │
└───────────────────┴───────────────────────┴──────────────────────┘
                           HTTP / JSON + JWT
```

三端互不共享代码，只通过 HTTP 通信：

- **网页端**：教师创建/导入实验、查看进度与统计、批阅报告；学生查看实验、逐步操作、在线写并运行 Python、提交报告。
- **后端**：鉴权、实验与进度、AI 屏幕指导（教程关键词快路径 + 多模态视觉兜底）、代码运行、数据分析。
- **桌面助手**：常驻托盘，用 Windows UI Automation 读取控件坐标，透明悬浮层在真实软件上画绿框标注下一步该点哪里。

## 2. 技术栈

| 端 | 技术 |
|---|---|
| backend | Python 3.10+（开发环境 3.13）、FastAPI、SQLAlchemy 2、SQLite、python-jose(JWT)、bcrypt、httpx |
| frontend | Vue 3.5 + TypeScript + Vite 4、Element Plus、Pinia、Vue Router、Monaco Editor、ECharts |
| desktop | PySide6(Qt6)、comtypes / IUIAutomation、pywin32、mss、Windows Graphics Capture、httpx |

## 3. 目录结构

```
.
├── backend/                # FastAPI 服务
│   ├── app/
│   │   ├── main.py         # 入口（建表 + 首次管理员 + 挂载路由）
│   │   ├── core/           # 配置 / 安全（JWT、bcrypt）
│   │   ├── db/             # 数据库会话
│   │   ├── models/         # ORM 模型
│   │   ├── api/v1/routers/ # auth / experiments / progress / ai / code / analytics
│   │   ├── engines/        # AI 实训引擎（动态指导 / 结果验证 / 视觉理解）
│   │   ├── adapters/       # 软件适配器（Python / MySQL / 注册表）
│   │   └── knowledge/      # 软件教程关键词库
│   ├── alembic/            # 数据库迁移（目前仅 env.py 占位）
│   ├── tests/              # pytest 用例（隔离临时数据库）
│   ├── requirements.txt
│   ├── requirements-dev.txt
│   └── .env.example        # 环境变量模板（不含真实密钥）
├── frontend/               # Vue 3 网页端
│   ├── src/
│   │   ├── views/          # auth / student / teacher
│   │   ├── layouts/  router/  stores/  api/  utils/  assets/
│   ├── package.json
│   └── .env.example
├── desktop/                # PySide6 桌面助手（仅 Windows）
│   ├── src/
│   │   ├── main.py         # 入口
│   │   ├── ui/             # 主窗口 + 托盘
│   │   ├── overlays/       # 全屏透明悬浮标注层
│   │   ├── core/           # 截图 / 窗口识别 / UIA / OCR 接口
│   │   ├── network/        # 后端 HTTP 客户端
│   │   └── config/         # 本地配置（保存在用户目录，不入库）
│   └── requirements.txt
├── scripts/                # 启动与调试脚本（start-*.ps1、init_db.py、test_*.py）
├── experiment_packs/       # 可导入的实验包 JSON
├── demo_shots/             # 产品界面截图（README 用）
├── docs/                   # 文档说明（调试截图不入库）
└── *.md                    # 协作与项目文档
```

## 4. 环境要求

| 项 | 要求 |
|---|---|
| 操作系统 | Windows 10/11（**桌面助手仅支持 Windows**，UIA / DWM / WGC 均为 Windows API） |
| Python | 3.10+（开发环境实测 3.13.14） |
| Node.js | 18+（开发环境实测 v26.13.0，npm 11.20.0） |
| 浏览器 | 支持 ES2020 的现代浏览器 |

## 5. 启动方式

### 5.1 后端（FastAPI，默认 8000）

```powershell
cd backend
python -m venv .venv
.\.venv\Scripts\activate
pip install -r requirements.txt
copy .env.example .env        # 按需修改（至少改 ADMIN_PASSWORD 与 JWT_SECRET_KEY）
python -m app.main
```

启动后访问：

- 健康检查：<http://localhost:8000/health>
- 接口文档：<http://localhost:8000/docs>

也可以直接运行 `scripts\start-backend.ps1`（会自动复制 `.env` 并安装依赖）。

### 5.2 前端（Vite，默认 5173）

```powershell
cd frontend
npm install
npm run dev
```

访问 <http://localhost:5173>。也可运行 `scripts\start-frontend.ps1`。

可用命令：

| 命令 | 说明 |
|---|---|
| `npm run dev` | 开发服务器 |
| `npm run build` | 类型检查 + 生产构建 |
| `npm run preview` | 预览构建产物 |
| `npm run type-check` | 仅类型检查 |

### 5.3 桌面助手（仅 Windows）

```powershell
cd desktop
python -m venv .venv
.\.venv\Scripts\activate
pip install -r requirements.txt
python src\main.py
```

首次启动请在「设置」中确认后端地址（默认 `http://localhost:8000/api`）。悬浮标注层按 **ESC**
或双击可临时隐藏。

> 桌面端配置保存在 `%USERPROFILE%\.zd_shixun\desktop_config.json`，其中可能包含登录 token，
> 该文件位于用户目录，不在本仓库内。

## 6. 环境变量

### 后端 `backend/.env`

| 变量 | 说明 | 默认 |
|---|---|---|
| `APP_NAME` | 应用名 | 智导实训 |
| `APP_ENV` | `development` / 其他 | development |
| `DEBUG` | 调试模式（影响热重载） | true |
| `HOST` / `PORT` | 监听地址与端口 | 0.0.0.0 / 8000 |
| `CORS_ORIGINS` | 允许的前端来源（JSON 数组） | `["http://localhost:5173"]` |
| `DATABASE_URL` | 数据库连接串 | `sqlite:///./zd_shixun.db` |
| `ADMIN_USERNAME` / `ADMIN_PASSWORD` | 首次建库时的唯一管理员 | admin / change-me-please |
| `JWT_SECRET_KEY` | JWT 签名密钥，**生产必须替换** | 占位值 |
| `ACCESS_TOKEN_EXPIRE_MINUTES` | token 有效期（分钟） | 1440 |
| `ALLOW_PUBLIC_REGISTER` | 是否开放公开注册 | false |
| `AI_API_BASE_URL` / `AI_API_KEY` / `AI_VISION_MODEL` | OpenAI 兼容多模态接口；三项留空则只用关键词快路径 | 空 |

### 前端 `frontend/.env`

| 变量 | 说明 |
|---|---|
| `VITE_API_BASE_URL` | 后端基础地址，默认 `http://localhost:8000` |
| `VITE_APP_ENV` | 环境标识 |

## 7. 默认账号

首次启动、`users` 表为空时会创建**一个**管理员账号（不生成任何演示数据）：

- 账号：`admin`（可用 `ADMIN_USERNAME` 覆盖）
- 密码：`.env` 中的 `ADMIN_PASSWORD`
- 角色：teacher（可进入教师端与学生端）

> **部署前必须修改默认密码。** 实验内容由教师通过「实验管理 → 导入实验」导入 JSON 实验包，
> 示例见 `experiment_packs/01-ai-api-lab.json`。

## 8. 主要接口

```
POST   /api/v1/auth/login            GET  /api/v1/auth/me        POST /api/v1/auth/register
GET    /api/v1/experiments           POST /api/v1/experiments
POST   /api/v1/experiments/import    GET/PUT/DELETE /api/v1/experiments/{id}
GET    /api/v1/experiments/{id}/steps
POST   /api/v1/experiments/{id}/start | /step | /submit
GET/PUT /api/v1/experiments/{id}/report    POST /api/v1/experiments/{id}/report/submit
GET    /api/v1/progress/{exp_id}
POST   /api/v1/ai/guide | /screen-guide | /analyze-screen | /diagnose/{id} | /verify/{id}/{step_id}
POST   /api/v1/code/run
GET    /api/v1/analytics/overview | /students | /experiments/{id}
GET    /health
```

## 9. 测试

### 9.1 后端 pytest

```powershell
cd backend
pip install -r requirements-dev.txt   # 含 pytest
python -m pytest -q
```

- 测试位于 `backend/tests/`（`conftest.py`、`test_auth.py`、`test_experiments.py`、
  `test_progress.py`、`test_report.py`）。
- **完全隔离**：每个测试使用 `tmp_path` 下独立的临时 SQLite 库，`get_db` 通过
  `dependency_overrides` 替换；导入 app 之前已把 `DATABASE_URL` 指向一次性临时文件，
  不会连接、修改或删除真实数据库。
- **不读取真实 `.env`**：pytest 启动时把 `ZD_ENV_FILE` 指向一个不存在的临时文件，
  配置加载器因此不会读到 `backend/.env`（该路径可用 `ZD_ENV_FILE` 自定义，正常开发不受影响）。
- 不需要联网、不需要真实 AI Key。

### 9.2 前端

```powershell
cd frontend
npm install      # 首次
npm test         # 执行 vue-tsc 类型检查，返回真实退出码
npm run type-check  # 等价命令
```

> 目前前端测试入口只做类型检查，尚未引入 Vitest 组件测试。

### 9.3 测试现状

- 后端：**53 项用例，全部通过**。
- 前端：`npm test`（vue-tsc）通过。
- 详见 [TEST_REPORT.md](TEST_REPORT.md)。

## 10. 安全说明（重要）

1. **`POST /api/v1/code/run` 无沙箱**：会在服务端以子进程执行任意 Python 代码，仅适合本机/内网教学，
   切勿暴露到公网。
2. **不要提交 `.env`、密钥、数据库**：`.gitignore` 已覆盖 `.env`、`*.db`、`*.log`、`node_modules`、
   `dist` 等；`ai_review/` 本地审核快照已被忽略。
3. **JWT 密钥**：`APP_ENV` 非 `development` 时若仍使用默认密钥，应用会拒绝启动。
4. **采集最小化**：桌面助手只上传当前目标窗口截图与 UIA 控件信息，不采集整屏内容。

## 11. 截图

`demo_shots/` 下为产品界面截图（教师端实验管理、学生端工作台、实验报告等），可用于演示材料。

## 12. License

内部项目。
