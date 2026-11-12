# V2-01：旧项目盘点与 V2 重建方案

> 产出人：Trae ｜ 日期：2026-11-12 ｜ 状态：待 ChatGPT / 项目负责人审查
> 本报告对应 AI_COLLABORATION.md §7「当前总任务」第 1–3 项，审查通过后进入 V2-02（工程骨架）。

---

## 1. 分支与文件盘点

### 1.1 当前分支 feat/zhidao-shixun-v2-rebuild

只有 2 个文件，均为 V2-00 产物，工作树干净：

| 文件 | 说明 |
|---|---|
| README.md | V2 运行指南（尚无可运行内容，符合当前阶段） |
| AI_COLLABORATION.md | 协作总控文档 |

### 1.2 main 分支

**仅 1 个 Initial commit（11698fa），内容只有 2 行 README。旧项目代码不在 main 上。** main 保持不动即可，无需任何清理。

### 1.3 旧项目实际位置：origin/trae-dev

共 150 个文件，主源码约 9,700 行。分区盘点：

| 区域 | 规模 | 内容 |
|---|---|---|
| backend/ | 40 文件（app）+ 8（tests） | FastAPI + SQLAlchemy 2 + Alembic + JWT（python-jose/bcrypt）。路由：auth / ai / analytics / code / experiments / progress；adapters 骨架（base+registry+mysql_adapter+python_adapter）；engines 骨架（dynamic_guide 214 行、result_verifier、visual provider 202 行）；knowledge/software_tutorials.py 410 行；**models 仅 user.py** + code_tasks 迁移；services/sandbox_client.py |
| frontend/ | 17 个 src 文件 | Vue 3 + TS + Vite 4 + Element Plus + Pinia + Monaco + ECharts。页面：登录、学生（Dashboard/ExperimentDetail/Workbench 579 行/Report）、教师（Dashboard/ExperimentManage/Analytics） |
| desktop/ | 16 个 src 文件 | PySide6 + mss + Pillow + pywinauto + comtypes。core（screen/ocr/uia 290 行）、overlays/annotation（183 行）、ui/main_window（833 行）、tray、network/api_client（**内置 admin/demo123 自动登录**） |
| sandbox_manager/ | 11 文件 | 独立 FastAPI + Docker 沙箱服务：runner（243 行）/container_spec/image_verify + systemd + 3 个测试文件。与主后端分离部署（Linux 节点） |
| scripts/ | 14 文件 | 调试/诊断脚本（test_visual_api 等），**非回归测试** |
| experiment_packs/ | 1 文件 | 01-ai-api-lab.json：结构化实验包（steps/instruction/expected_result/common_errors/adapter：target_app/window_title/keywords/type_hint） |
| 顶层文档 | 8 文件 | PROJECT_CONTEXT / TASK_BOARD / DECISIONS / TEST_REPORT / CHANGELOG / NEXT_STEPS / SANDBOX_DEPLOYMENT / TRAE_START_HERE |
| 其他 | — | demo_shots 6 张截图（含个人桌面内容）、docs 2 文件 |

### 1.4 旧项目遗留问题（来自 TASK_BOARD / 实测确认）

| 编号 | 问题 | 对 V2 的启示 |
|---|---|---|
| R-01 | 弱默认密码 admin/demo123（backend config + desktop 自动登录） | V2 禁止内置任何默认凭据，与用户记忆要求一致（无默认演示数据） |
| R-02 | SQLAlchemy 依赖未设上限，实测装到 2.1.8 | V2 依赖收敛版本区间 |
| R-04 | 无自动化回归测试，scripts 不可作回归 | V2-02 起每模块配 pytest，验收必须有测试证据 |
| R-05 | /code/run 曾无沙箱可执行任意代码，后补 sandbox_manager | V2 代码执行隔离为 P0 设计项，不是补丁项 |
| 架构 | AI 逻辑耦合在 routers/ai.py（420 行单文件），无独立引擎层 | V2 引擎独立成层（engine/），路由只做协议转换 |
| 完整度 | 数据模型仅 user + code_tasks；实验/步骤/进度/报告未建模 | V2-03 优先补齐实验任务数据模型 |

---

## 2. 复用 / 重建边界

### 2.1 总原则：不复制代码，只参考重写

旧项目全部业务代码（后端业务、前端页面、桌面业务、AI 引擎）在 V2 **全部重写**。需要参考时用 `git show origin/trae-dev:<path>` 只读查看，不合并、不拷贝整文件。

### 2.2 思路级参考资产（结构/设计有价值）

| 旧资产 | V2 用途 |
|---|---|
| adapters/base.py 的 locate_target / validate_result / get_state 抽象 + 注册表模式 | V2 engine/adapters 接口设计起点 |
| experiment_packs JSON 结构（步骤、预期结果、常见错误、适配器提示词） | V2-03 实验数据模型参考 |
| sandbox_manager 安全设计（timeout、输入输出上限、TLS/mTLS、镜像校验、隔离验证脚本） | V2 代码执行隔离设计参考 |
| desktop 技术选型（PySide6/mss/pywinauto/UIA） | 已被 AI_COLLABORATION §5 采纳，V2 沿用 |

### 2.3 唯一保留评估项

**sandbox_manager**（独立 Docker 沙箱服务，含独立测试，不含旧业务架构）：若负责人确认 V2 保留 Docker 执行节点方案，可作为独立子系统原样保留；否则仅在 docs 留设计参考。→ 待决策 D-1/D-3。

### 2.4 明确不迁移

- scripts/ 全部 14 个调试脚本
- demo_shots/（个人隐私内容，R-03）
- 8 个旧顶层文档（信息已被 AI_COLLABORATION.md 取代）
- desktop 内置弱凭据与自动登录逻辑、全部业务页面与路由
- knowledge/software_tutorials.py 的硬编码教程数据（V2 实验内容由用户后期导入，不内置演示数据）

---

## 3. V2 目录结构与模块边界（提案）

```text
zhidao-shixun/
├── README.md                     # V2 运行指南（已有，随实现更新）
├── AI_COLLABORATION.md           # 协作总控（已有）
├── .gitignore                    # 根级统一（.env、*.db、node_modules、__pycache__、dist 等）
├── .env.example                  # 顶层配置示例（无真实密钥）
├── docs/                         # V2 设计文档（本文件所在）
│
├── server/                       # 后端 FastAPI（Python 3.11+）
│   ├── app/
│   │   ├── main.py               # 应用入口 + 健康检查 /health
│   │   ├── core/                 # 配置（pydantic-settings，.env 读取）、安全（JWT）
│   │   ├── api/v1/               # 路由层：auth / experiments / sessions / guide / health
│   │   │                         #   路由只做协议转换，业务在 engine 与 services
│   │   ├── models/               # SQLAlchemy ORM（实验/任务/步骤/会话/事件/报告）
│   │   ├── schemas/              # Pydantic 契约（含跨端统一状态结构）
│   │   ├── engine/               # ★AI 实训引擎（独立层）
│   │   │   ├── planner/          # 步骤规划与实验步骤状态机
│   │   │   ├── guide/            # 四级指导颗粒度生成
│   │   │   ├── verifier/         # 结果验证（程序化验证器优先，视觉验证兜底）
│   │   │   ├── vision/           # 感知编排：本地 OCR 优先、事件触发截图、多模态模型可插拔
│   │   │   └── adapters/         # 适配器接口 + python_web / mysql_workbench 实现
│   │   └── services/             # 代码执行隔离、AI 客户端（OpenAI 兼容）
│   ├── tests/                    # pytest（V2-02 起与模块同步建立）
│   ├── requirements.txt          # 版本区间收敛
│   └── alembic/                  # 数据库迁移
│
├── web/                          # 前端 Vue 3 + Vite + TS
│   └── src/
│       ├── api/                  # 后端 API 封装
│       ├── router/ stores/       # 路由、Pinia
│       ├── views/student/        # 任务列表、实验工作台（Monaco）、指导面板、报告
│       ├── views/teacher/        # 实验管理、进度统计（ECharts）
│       └── components/           # 指导卡片、步骤时间线、验证结果等
│
├── desktop/                      # Windows 助手（PySide6）
│   └── src/
│       ├── core/                 # screen（mss）/ uia（pywinauto）/ ocr（本地优先）
│       ├── perception/           # 感知适配器：把目标软件状态转成统一 ScreenState
│       ├── overlays/             # 悬浮提示、箭头、边框、编号标注
│       ├── ui/                   # 主窗口、托盘、暂停/停止控制
│       └── network/              # 与 server 通信（无 AI 密钥）
│
├── experiments/                  # 结构化实验定义 JSON（含每步验证器），用户后期导入
├── scripts/                      # start-server.ps1 / start-web.ps1 / start-desktop.ps1 / init_db.py
└── tests/                        # 跨端集成测试（V2-10）
```

### 模块边界与跨端契约（关键设计）

1. **统一状态结构**：`ScreenState / StepState / VerifyRequest / VerifyResult / GuideMessage` 由 server/engine 的 Pydantic schema 定义，是三端唯一通信契约。
2. **AI 密钥只在 server**：web、desktop 不持有任何模型密钥；desktop 只做本地感知与标注渲染。
3. **适配器分两层**：
   - desktop 感知适配器（本地运行 UIA/OCR，输出 ScreenState）；
   - server 语义适配器（步骤语义匹配、验证逻辑），接口同源于 engine/adapters。
4. **验证优先级**：程序化验证器（代码运行结果、数据库查询、文件状态）> 控件状态（UIA）> OCR/视觉（兜底，置信度不足不精确标注）。
5. **无内置演示数据**：experiments/ 内容全部由用户后期导入，符合用户明确要求。

---

## 4. 技术选型（严格对应 AI_COLLABORATION §5）

| 层 | 选型 | 说明 |
|---|---|---|
| web | Vue 3 + Vite + Element Plus + Pinia + Monaco Editor + ECharts + TS | 与 §5 一致 |
| server | FastAPI + SQLAlchemy 2（版本区间收敛）+ Alembic + SQLite（初期）+ JWT | 预留 PostgreSQL 切换 |
| desktop | PySide6 + mss + pywinauto/comtypes + 本地 OCR | OCR 库 V2-05 时定（RapidOCR / PaddleOCR 二选一） |
| AI | OpenAI 兼容接口、可替换模型、结构化输出 | 密钥走 .env，禁止入库 |
| 代码执行 | 见 D-1 | V2-04 前决策 |
| 视觉 | 事件触发截图 + 本地 OCR 优先，多模态模型兜底 | 不做每秒全屏上传（§4-2） |

---

## 5. 旧文件处理方案

1. **V2 分支当前无旧文件，无需删除清理。**
2. main 保持不动（仅初始提交）。
3. trae-dev 不合并进 V2，保留为历史参考，只读查看（`git show origin/trae-dev:<path>`）。
4. 本报告存档于 docs/，作为后续复用判断的唯一依据；此后对旧代码的任何参考引用均应指向本报告结论。

---

## 6. 待决策项（需项目负责人 / ChatGPT 审查本方案时确认）

| 编号 | 问题 | 选项 A | 选项 B | Trae 建议 |
|---|---|---|---|---|
| D-1 | Python 实验代码执行隔离方案 | 受限子进程（timeout/输出上限/临时目录/可选禁网），Windows 本地演示友好 | Docker 沙箱（强隔离，需部署 Linux 节点，本机演示受限） | 首期 A，接口预留 B（对应旧 sandbox_manager 思路） |
| D-2 | 实验定义格式 | 以旧 experiment_packs JSON 为基础规范化（补充验证器字段） | 全新设计 | A：旧结构质量可用，规范字段后沿用思路 |
| D-3 | sandbox_manager 去留 | 作为 V2 可选组件保留在仓库 | 仅在 docs 留设计参考 | 依赖 D-1：选 A 则暂留 docs 参考 |

---

## 7. 本机环境注意事项（影响后续所有 git 操作）

- 本机 git 全局配置将 `https://github.com/` 重写为 `https://ghfast.top/https://github.com/`（加速镜像），**当前该镜像不可达**。
- 本次克隆使用单次命令级覆盖完成（未修改全局配置）：
  `-c http.proxy=http://127.0.0.1:10808 -c http.sslBackend=openssl -c url.https://github.com/wyy906/zhidao-shixun.git.insteadOf=https://github.com/wyy906/zhidao-shixun.git`
- 说明：系统代理 127.0.0.1:10808 可达 GitHub；Windows schannel 后端存在吊销检查失败问题（CRYPT_E_REVOCATION_OFFLINE），需切换 openssl 后端。
- **后续每次 fetch/push 均需带同样参数**，否则会尝试连接 ghfast.top 失败。
