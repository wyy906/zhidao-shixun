# 智导实训 V2｜AI 协作与开发总控文档

本文件是 ChatGPT、Trae 和项目负责人共同使用的项目协作记录。**所有重要指令、决策、进度、问题、验收结果和交接内容都必须写在这里。**

- 当前分支：feat/zhidao-shixun-v2-rebuild
- 原有项目分支：main（保持独立，不得擅自修改）

---

## 0. 协作规则

### 每次开始工作前
1. 拉取当前分支最新代码。
2. 完整阅读本文件和根目录 README.md，尤其是当前任务、进度看板、最近交接和未解决问题。
3. 检查实际代码，不把计划误认为已经实现。
4. 文档和代码不一致时，先核实代码，再记录差异。

### 每次工作结束后
必须更新本文件，记录实际完成内容、修改文件、运行命令、测试结果、未完成事项、风险和下一步建议。**禁止只在聊天窗口汇报而不更新本文件。**

### 角色分工
- **项目负责人（用户）：** 决定方向、优先级和重要取舍，通过 ChatGPT 传达需求。
- **ChatGPT：** 产品与技术协作负责人，负责需求拆解、架构审查、技术方案、开发指令和代码审查；把明确指令写入本文件；核实代码和进度。未实际提交不得声称已修改代码。
- **Trae：** 代码实施负责人，负责编码、运行、测试和修复；执行前阅读本文件；完成后提交代码并更新本文件。阻塞时说明原因、证据、尝试过的方案和待决策问题。

### Git 分支纪律
- V2 所有新开发只提交到 feat/zhidao-shixun-v2-rebuild。
- main 是旧项目线，禁止向其提交 V2 内容；不直接合并，不自动创建 PR。
- 不要把旧项目业务实现直接复制进 V2。旧代码只作历史参考；V2 必须重新设计目录、模块边界和业务实现。
- 不得未经盘点就删除整个仓库。先列出旧文件，区分可复用通用工具与必须重建模块，再实施清理。
- 每个阶段独立 commit；推送前先 pull/rebase。
- 不得提交 API Key、密码、Cookie、个人数据或真实实验截图。

### 协作文档防覆盖
修改前先拉取最新版本；只改必要章节并保留对方记录。发生冲突时以最新远端版本为基础合并。禁止在旧副本上强制推送或整篇覆盖。

---

## 1. 项目定位（最高优先级）

### 正式名称
**「智导实训」——AI视觉感知与实时操作引导平台**  
参赛方向：AI+教育。

### 项目简介（策划书基础表述）
本项目构建了一个面向多学科数字化实验的 AI 实训平台，通过视觉感知、操作状态理解和实验流程建模，实现对学生电脑操作过程的实时感知与智能引导。平台采用通用 AI 实训引擎与专业软件适配器相结合的架构，支持网页内部实验及外部专业软件实训，能够根据学生的实际操作状态提供精确的步骤指导、错误诊断和结果验证。

### 核心定位
这不是普通聊天机器人，也不是 AI 实训考官。它是一个能够观察学生真实操作环境、理解实验目标和当前状态、给出具体操作指引、验证结果并在出错时帮助恢复的 AI 实验指导老师。

### 核心架构
**一个平台 + 两种终端 + 一个通用 AI 实训引擎 + 多种专业软件适配器。**
- Web 平台：课程、任务、实验步骤、在线实验、记录、报告和教师管理。
- Windows 助手：感知外部软件窗口与界面，展示悬浮提示、箭头、边框和编号。
- AI 实训引擎：任务理解、步骤规划、状态判断、指导生成、错误诊断、结果验证、指导颗粒度调整。
- 软件适配器：为不同软件提供状态读取、控件定位、操作能力和结果验证接口。

### 不同软件接入原则
不同软件可访问性不同，不强求一种技术通吃：
1. 有可访问控件接口：优先 UI Automation / pywinauto。
2. 浏览器网页：优先使用 Playwright 读取授权页面 DOM 和状态。
3. 只能视觉识别：使用截图、OCR、多模态视觉模型；置信度不足时不做精确标注。
4. 特殊软件：开发独立专业适配器，向 AI 引擎输出统一状态结构。

统一的是 AI 实训流程和状态接口，不是所有软件的底层实现。

### 首期范围
只验证两个环境：
- **Python 网页实验：** 网页编辑、运行、结果展示与验证。
- **MySQL Workbench 外部软件实验：** Windows 助手识别真实软件界面并指导操作。

后续再评估 Excel、Java IDE、MATLAB、Multisim、CAD 等适配器。不得在首期为“支持所有软件”过度设计。

---

## 2. 必须实现的核心闭环

1. 学生选择实验任务。
2. AI 读取实验目标、标准步骤、前置条件和预期结果。
3. 系统识别当前环境（网页实验或外部软件）。
4. 识别学生当前步骤和实际界面状态。
5. 给出具体操作指导（软件、窗口、菜单、按钮、输入内容、预期结果）。
6. 学生亲自操作。
7. 系统重新感知并验证操作结果。
8. 成功则进入下一步；失败则诊断错误并指导恢复。
9. 根据实际困难动态调整指导颗粒度。
10. 记录真实实验过程并生成报告草稿。

**每一步必须有可验证的完成条件，不能只凭大模型说“完成了”就标记成功。**

---

## 3. 指导颗粒度动态调整（核心创新）

根据学生实际状态，而不是机械按尝试次数调整：
- **一级：简洁提示**——直接告诉学生下一步做什么、在哪里操作。
- **二级：屏幕标注**——箭头、边框、编号定位控件，并解释按钮作用。
- **三级：详细解释**——说明菜单路径、输入内容、参数含义和注意事项。
- **四级：局部示范**——针对当前困难步骤给出操作演示、代码片段或示例，不直接替学生完成整个实验。

触发依据包括操作错误、停留时间、界面状态、连续失败、学生主动求助等。学生恢复顺利后应降低指导强度。不要频繁反问“你觉得下一步该做什么”；优先给出明确、可执行的动作指引。

---

## 4. 技术与安全原则

1. 优先用可访问控件接口，视觉识别作为补充或回退。
2. 不要每秒截图并上传大模型；采用事件触发、关键步骤观察和本地 OCR 优先。
3. 能用程序、数据库、文件或运行结果验证时，不要只凭截图猜测。
4. 实验步骤结构化定义：前置条件、操作目标、预期状态、验证器、常见错误、恢复方法。
5. AI 只能在已审核流程和适配器能力范围内给建议，不得自由编造高风险操作。
6. 默认只提供指导，不自动执行。演示/代操作必须得到明确授权。
7. 删除、提交、覆盖、系统设置等重要动作必须再次确认。
8. 必须提供暂停观察、停止助手和关闭标注入口。
9. 只采集实验所需状态和关键事件；明确告知采集范围，敏感信息遮挡，避免无关全屏监控。
10. Python 代码执行必须隔离运行，不能直接在服务主进程执行不可信代码。
11. 密钥只从环境变量或本地配置读取；提供 .env.example，真实 .env 加入忽略规则。
12. 所有“已完成”“识别成功”“验证通过”都必须有测试或运行证据。

---

## 5. 建议技术方向（可论证调整，但记录理由）

- Web：Vue 3 + Element Plus。
- 后端：Python FastAPI。
- 编辑器：Monaco Editor。
- Windows 助手：Python + PySide6。
- 控件访问：Windows UI Automation / pywinauto。
- 浏览器接入：Playwright。
- 视觉：截图 + OCR + 多模态视觉模型。
- AI：多模态模型、结构化输出、RAG、受约束实验流程。
- 数据：初期 SQLite，确有需要再引入 PostgreSQL。
- 图表：ECharts。

不要为了追求技术名词引入不必要的复杂组件，优先保证可运行、可验证、可演示。

---

## 6. 首期功能清单

### P0：必须优先完成
- 项目基础结构、配置和启动说明。
- 学生端基础页面。
- 实验任务与标准步骤管理。
- Python 网页实验的编辑、运行和结果验证。
- Windows 桌面助手基础窗口。
- 屏幕截图、窗口识别、OCR/控件识别。
- MySQL Workbench 基础适配器。
- 悬浮提示和屏幕目标标注。
- 实验步骤状态机。
- AI 指导生成。
- 结果验证和失败恢复。
- 四级动态指导机制最小可用实现。
- 暂停/停止、授权和敏感动作确认。

### P1：闭环稳定后完成
- 实验过程记录、AI 实验报告草稿。
- 教师管理页面、班级统计和错误分布。
- 适配器诊断页面、更多实验任务样例。
- 演示和部署体验优化。

### 暂不做
- 一次性支持所有专业软件。
- 手机 App、VR/AR 或专用硬件。
- 无限制自动操作学生电脑。
- 复杂多智能体架构。
- 未经验证的大规模并发平台。

---

## 7. 当前任务（ChatGPT 更新，Trae 执行）

### 当前总任务：V2-02 基础工程骨架

V2-01 已经由 ChatGPT 审查通过，进入工程实现。后续按“先跑通最小闭环，再扩展功能”的顺序开发，不要一次性生成庞大系统。

#### 已审查通过的 V2-01 结论
1. 旧项目业务代码全部参考重写，不复制旧业务实现；旧分支 `trae-dev` 只读参考。
2. 采用单仓结构：`server/`、`web/`、`desktop/`、`experiments/`、`scripts/`、`docs/`。
3. Web、API、Windows 助手、AI 引擎和软件适配器职责分离。
4. AI 密钥只保存在服务端；桌面助手只负责本地感知和标注。
5. 统一跨端状态契约需要版本化。不要让 desktop 直接依赖 server 内部模块；优先通过独立共享契约包或 JSON Schema/OpenAPI 生成的客户端保持兼容。
6. 旧项目的个人桌面截图、弱默认凭据、自动登录、调试脚本和硬编码教程数据均不得迁移。

#### 已确定的三个关键决策
- **D-1 代码执行隔离：选择 Docker 沙箱方案。** Python 实验代码属于不可信输入，不能把普通 subprocess + timeout 当作安全沙箱。首期采用独立容器执行，默认禁网、非 root、只读根文件系统、临时工作目录、CPU/内存/PID/时间/输出限制，不挂载宿主机敏感目录，不把 Docker socket 暴露给 Web 业务进程。Windows 本地演示通过 Docker Desktop（Linux containers）运行；Docker 不可用时必须明确提示，不得静默退化为宿主机执行。
- **D-2 实验定义格式：选择全新规范化 JSON Schema。** 可参考旧 experiment_packs 的步骤组织思想，但不直接沿用旧格式。至少包含 schema_version、experiment 元信息、环境/适配器、步骤 ID、前置条件、操作目标、预期状态、验证器、常见错误、恢复建议和指导等级提示；验证器类型必须白名单化。
- **D-3 sandbox_manager：不迁移旧代码，也不保留旧独立服务。** 在 V2 内重新实现最小 Docker 执行服务/接口，安全设计可参考旧报告；先做最小必要能力和自动化测试，避免引入旧项目部署复杂度。

#### V2-02 Trae 执行清单
1. 拉取并确认当前分支最新提交，工作区干净；不得修改 main 或 trae-dev。
2. 按审查通过的目录结构建立 server、web、desktop、experiments、scripts、tests。
3. 建立 Python/Node 版本与依赖锁定策略、根级 .gitignore、.env.example；不得提交真实密钥、个人数据或演示账号。
4. 建立 FastAPI 最小入口和 /health；建立 Vue 3 + Vite + TypeScript 最小页面；建立 PySide6 桌面助手最小启动入口（没有 Windows 环境时说明未实测，不得声称通过）。
5. 建立版本化跨端契约，至少定义 ScreenState、StepState、VerifyRequest、VerifyResult、GuideMessage；提供契约校验测试。
6. 建立配置读取、日志、统一错误响应和基础 pytest；前端至少通过构建检查。
7. 建立 Docker 执行器接口与安全配置设计/测试占位；本阶段不得先实现不安全的宿主机任意代码执行。
8. 补齐 README 中经过实际验证的安装、启动、健康检查命令；未验证的命令标注待验证。
9. 每个子模块分别给出运行命令和测试结果，提交阶段性 commit，并更新本文件。

**V2-02 验收标准：** 新环境按 README 可安装；后端 /health 返回成功；前端可启动并访问；桌面助手入口在 Windows 环境实际启动（若当前环境无法验证，单独标记）；契约测试、后端测试、前端构建均通过；无真实密钥/弱默认凭据；工作区和提交记录清晰。达到标准后才进入 V2-03。

#### 后续阶段顺序
- V2-03：实验任务与步骤数据模型、规范化 JSON Schema、验证器注册机制。
- V2-04：Python 网页实验闭环 + Docker 隔离执行 + 可验证结果。
- V2-05：Windows 助手基础能力（窗口、截图、OCR/UIA、暂停/停止）。
- V2-06：MySQL Workbench 适配器与安全标注。
- V2-07：AI 指导与四级动态颗粒度。
- V2-08：错误诊断、成功/失败/不确定三态验证与恢复。
- V2-09：过程记录与报告草稿。
- V2-10：集成测试、干净环境部署和比赛演示。

## 8. 进度看板

状态：未开始 / 进行中 / 待审查 / 已完成 / 阻塞。

| 编号 | 工作项 | 状态 | 验收标准 | 负责人 |
|---|---|---|---|---|
| V2-00 | 新分支与协作机制建立 | 已完成 | 分支存在；协作文档和 README 已提交 | ChatGPT |
| V2-01 | 旧项目盘点与重建方案 | 已完成 | 文件清单、复用/重建边界、V2目录结构；ChatGPT审查通过并确定D-1/D-2/D-3 | Trae + ChatGPT |
| V2-02 | V2基础工程骨架 | 待审查 | 后端健康检查、前端构建/启动、桌面入口、跨端契约、基础测试和真实启动文档 | Trae |
| V2-03 | 实验任务与步骤数据模型 | 未开始 | 规范化 JSON Schema、Python/MySQL任务可结构化表达、验证器白名单 | Trae |
| V2-04 | Python网页实验闭环 | 未开始 | 编辑、Docker隔离运行、验证、步骤推进；禁止宿主机直接执行不可信代码 | Trae |
| V2-05 | Windows助手基础能力 | 未开始 | 截图、窗口信息、暂停/停止 | Trae |
| V2-06 | MySQL适配器与标注 | 未开始 | 识别目标界面并安全显示标注 | Trae |
| V2-07 | AI指导与动态颗粒度 | 未开始 | 四级指导按实际状态切换 | Trae |
| V2-08 | 错误诊断与结果验证 | 未开始 | 覆盖成功、失败、不确定三态 | Trae |
| V2-09 | 过程记录与报告 | 未开始 | 记录真实事件并生成可编辑报告草稿 | Trae |
| V2-10 | 集成测试与比赛演示 | 未开始 | 两种环境闭环可稳定演示 | 双方协作 |

只有达到验收标准并提供测试证据才能标记“已完成”。只写完代码但没有运行验证，最多标记“待审查”。

---

## 9. 最近交接记录（倒序追加，不删除旧记录）

### 2026-11-12｜Trae：V2-02 基础工程骨架完成，全部本机实测

**本次目标：**
- 按 §7 执行 V2-02：建立 server/web/desktop/experiments/scripts/tests 骨架、版本化跨端契约、基础测试与安全配置；实际运行验证并如实记录。

**实际完成：**
- 目录与依赖策略：新增顶层 `contracts/`（独立可安装 Python 包 `zhidao-contracts`，含 JSON Schema 导出与漂移检测）；根级 .gitignore / .env.example（全 ZD_ 前缀，无任何密钥/默认凭据）；Node 用 package-lock.json 锁定，Python 用上限版本区间（Python 3.13.14 / Node 26.13.0 验证）。
- 跨端契约：`CONTRACT_VERSION="0.1.0"` + 五个核心模型 ScreenState / StepState / VerifyRequest / VerifyResult / GuideMessage（含 UiTarget、四级 GuideLevel、验证三态 VerifyOutcome）；Schema 基线导出至 contracts/schemas/*.json；契约变更通过契约测试强制同步。
- server：FastAPI 最小入口（/health、/api/v1/contract/version）、pydantic-settings 配置（ZD_ 前缀）、统一错误响应 {"error":{code,message,details}}、日志初始化、Docker 执行器接口与安全基线占位（D-1：禁网/只读/非 root/资源限制不可关闭，Docker 不可用时显式拒绝，无宿主机回退路径）。
- web：Vue 3 + Vite 6 + TS 最小页面（显示后端连接状态与契约版本），dev 代理目标可经 ZD_API_PROXY_TARGET 配置。
- desktop：PySide6 包 zhidao_desktop 最小窗口（后端连接状态 / 暂停感知 / 停止助手），入口支持 --smoke / --check；仅 HTTP + 共享契约，不依赖 server 内部模块。
- scripts：setup-dev / start-server / start-web / start-desktop（PowerShell，ASCII 英文注释避免 GBK 解析问题；后端/桌面支持 -ApiTarget）。
- 实验目录 experiments/ 为空属预期（用户后期导入，符合「无内置演示数据」要求）。

**修改文件：**
- 新增约 50 个文件：contracts/（6 源文件 + 5 Schema）、server/app/**（main/core/api/services/executor/engine 占位）+ 3 个测试、web/（Vite+TS 工程 + 最小页面）、desktop/zhidao_desktop/**、tests/contracts/ 2 个测试、scripts/ 4 个、根级 .gitignore / .env.example / pytest.ini / README.md 更新、experiments/README.md。

**验证命令与结果（本机 Windows 实测，全部通过）：**
- `.venv\Scripts\python.exe -m pytest` → **20 passed**（契约模型 7、Schema 漂移 3、配置 2、执行器 4、健康检查 4）。
- `scripts/start-server.ps1 -Port 8100` + `curl /health` → HTTP 200 `{"status":"ok",...,"contract_version":"0.1.0"}`；`/api/v1/contract/version` 返回 5 模型清单；未知路径返回统一 404 错误结构。
- `scripts/start-desktop.ps1 -Check` → 后端已连接；`-Smoke` → **窗口真实启动**，1.5 秒自动退出，退出码 0。
- `npm run build`（web/）→ vue-tsc 类型检查 + vite 构建通过（13 modules）；`npm run dev` → 页面 HTTP 200，经代理访问 /health 返回 V2 响应。

**本机环境问题与解决（供后续阶段参考）：**
- 本机 8000 端口被一个遗留 python 进程占用（非 V2 服务，未处理），V2 验证改用 8100；脚本已支持 -Port / -ApiTarget。
- **Windows Smart App Control（已开启）拦截未签名原生模块**：rollup 原生 .node 无法加载导致 vite build 失败；通过 package.json 依赖别名 `rollup → npm:@rollup/wasm-node@^4.68.2`（WASM 构建）解决。与旧项目 TASK_BOARD R-02 记录的 SQLAlchemy C 扩展被拦截属同一机器策略。
- npm 11 install-scripts 特性提示 esbuild postinstall 未批准：不影响构建（esbuild.exe 随平台包安装），已记录。
- .ps1 中文注释在 PowerShell 5.1 GBK 代码页下破坏解析（UTF-8 无 BOM）：所有脚本已改为 ASCII 英文注释。

**未完成 / 已知问题：**
- V2-02 为骨架：无业务功能、无数据库模型、无 Docker 容器执行（V2-03/V2-04 交付）；执行器 run() 现阶段显式抛 DockerUnavailableError（有测试覆盖该行为）。
- 依赖策略为版本区间（README 已记录验证版本）；未做 pip 精确锁定（避免跨平台差异，如 ChatGPT 认为需要可再加）。

**下一步建议：**
- V2-03：实验任务与步骤数据模型、规范化 JSON Schema（D-2）、验证器白名单注册机制；contracts 契约随之扩展。

**关联提交：**
- commit `10fc9de`：feat(v2-02): build V2 skeleton with versioned cross-end contract and tests（64 文件 +3132 行；已 rebase 合并 ChatGPT 并行提交 9beacc4 / fbcc7bc 后推送）。

**给 ChatGPT 的汇报留档（对应聊天窗口汇报内容）：**

本次汇报四项内容，与上方交接记录互为摘要：

1. **提交 SHA**：`10fc9de`（V2-02 骨架 + 文档，64 文件 +3132 行，feat/zhidao-shixun-v2-rebuild）。
2. **修改文件**（按模块）：contracts/（独立契约包 0.1.0：5 核心模型 + JSON Schema 基线 + 漂移测试）；server/（FastAPI 入口 /health、契约版本端点、统一错误结构、ZD_ 配置、日志、Docker 执行器接口与不可关闭安全基线）；web/（Vue3+Vite6+TS 最小页面、dev 代理可配置）；desktop/（PySide6 最小窗口：状态/暂停/停止，--smoke/--check）；scripts/ 4 个；根级 .gitignore / .env.example / pytest.ini；README 与本文档更新。
3. **测试命令与结果（本机实测全部通过）**：`pytest` → 20 passed；`start-server.ps1 -Port 8100` + curl /health → HTTP 200 含 contract_version；404 → 统一错误结构；`start-desktop.ps1 -Check/-Smoke` → 连接成功 + 窗口真实启动自动退出；`npm run build` → vue-tsc+vite 通过；`npm run dev` → 页面 200、代理 /health 正常。
4. **未完成事项**：业务功能（实验模型、AI 指导、标注、Docker 容器执行）未实现——执行器 run() 现阶段显式抛 DockerUnavailableError（测试覆盖该行为），V2-04 交付容器实现；Python 依赖为版本区间 + README 记录验证版本，未做 pip 精确锁定（是否升级为精确锁定请 ChatGPT 定夺）。

**本次开发遇到的问题与解决（均已实测复现并解决，供后续阶段参考）：**

| 问题 | 根因 | 解决方式 | 状态 |
|---|---|---|---|
| vite build 失败：rollup 原生 .node ERR_DLOPEN_FAILED | 本机 Windows Smart App Control（已开启）拦截未签名原生模块，与旧项目 TASK_BOARD R-02 记录的 SQLAlchemy C 扩展被拦截同因 | web/package.json 依赖别名 `rollup → npm:@rollup/wasm-node@^4.68.2`（纯 WASM，无原生模块）；npm overrides 方式对该场景不生效，顶层 devDependency 别名生效 | 已解决（决策已记录 §10） |
| 推送被拒（fetch first） | ChatGPT 并行推送了 9beacc4 / fbcc7bc | fetch + rebase，无冲突，双方文档内容均保留；rebase 后复跑 pytest 仍 20 passed | 已解决 |
| start-server.ps1 解析报错（Unexpected token） | PowerShell 5.1 在 GBK 代码页按 ANSI 读取 UTF-8 无 BOM 脚本，中文注释尾字节吞掉换行破坏语法 | 4 个 .ps1 全部改为 ASCII 英文注释；新增脚本同样遵守 | 已解决（决策已记录 §10） |
| 8000 端口被占用（bind 10048） | 遗留 python 进程（路径 .workbuddy，非 V2 服务）监听 8000 并响应旧版 /health | 未动该进程；V2 支持 -Port / -ApiTarget，验证用 8100 | 待负责人决定是否清理 |
| npm 11 提示 esbuild postinstall 未批准（allowScripts） | npm 11 新安全特性 | 可忽略：esbuild.exe 随平台包安装，构建不受影响 | 已知悉 |
| contracts 首次安装失败（readme 指向包外文件） | setuptools 不允许读取包目录外文件 | 移除 pyproject 的 readme 字段 | 已解决 |

**需要对方处理或确认：**
- ChatGPT：审查 V2-02（看板已标"待审查"）；确认依赖锁定策略（版本区间 vs pip 精确锁定）。
- 负责人：是否清理占用 8000 端口的遗留进程；仓库 public/private 决策仍未定。

### 2026-11-12｜ChatGPT：V2-01 审查通过，确定关键技术决策并启动 V2-02

**审查依据：**
- 已读取本分支最新 `AI_COLLABORATION.md`、`README.md` 和 `docs/V2-01_inventory_and_rebuild_plan.md`。
- GitHub 比较结果：V2 分支相对 main ahead 5 commits、behind 0；本分支新增/修改文件为 AI_COLLABORATION.md、README.md、docs/V2-01_inventory_and_rebuild_plan.md。
- V2-01 对旧项目分支、文件规模、风险和重建边界的盘点逻辑清楚，符合独立重建目标，审查通过。

**额外安全提醒：**
- 当前 GitHub 仓库元数据显示为 public。Trae 的盘点报告指出旧分支 trae-dev 含 6 张个人桌面截图及弱默认凭据。即使 V2 分支不迁移，这些旧分支内容仍可能被任何人读取；文件删除也不能自动清除 Git 历史。未处理前不要向仓库提交任何个人数据、密钥或真实截图。是否改为 private 或清理旧分支历史，需要项目负责人决定；ChatGPT 未擅自更改仓库可见性。

**审查补充意见：**
- 统一状态契约必须版本化，desktop 不应直接依赖 server 内部 Python 模块；采用共享契约包或 JSON Schema/OpenAPI 生成客户端。
- 普通 subprocess + timeout 不构成可靠安全沙箱；不可信 Python 代码必须进入受限容器。
- 新实验格式应有 schema_version 和白名单验证器，不能让实验 JSON 任意指定 Python 模块/函数。
- 桌面端的截图、OCR、标注必须有明确启停、最小采集和敏感信息保护；不能默认持续上传全屏。

**决策确认：**
- D-1：选择 Docker 沙箱；默认禁网、非 root、只读根文件系统、临时工作目录、资源/时间/输出限制；Docker 不可用不得退化到宿主机执行。
- D-2：选择全新规范化 JSON Schema，参考旧实验包思想但不直接复制旧格式。
- D-3：不迁移旧 sandbox_manager 服务代码；在 V2 内重新实现最小执行接口，旧代码仅作安全设计参考。

**本次实际修改：**
- 更新本文件 §7 当前任务，明确 V2-02 任务和验收标准。
- 更新 §8 看板：V2-01 已完成，V2-02 标记为“未开始（指令已下达）”，并将 Docker 安全要求纳入 V2-04。
- 更新 §10 决策记录和 §11 风险跟踪。

**下一步：**
- Trae 按 §7 执行 V2-02；完成后提交代码、测试证据和 README 运行步骤，再由 ChatGPT 审查。
- 本次只更新协作指令，没有修改业务代码，也没有声称项目已运行或测试通过。

---


### 2026-11-12｜Trae：撤回误建的交流区文档
- 负责人指出 AI_COLLABORATION.md 本身就是唯一交流文档；已 revert 掉误建的 docs/AI_DISCUSSION.md 及相关引用（commit cff80c3 已撤销）。
- 待决策项 D-1/D-2/D-3 回到本文件 §11 风险表跟踪（详见 docs/V2-01_inventory_and_rebuild_plan.md §6）。
- 规则已记入 §10 决策记录：不再另建任何交流/流程文档。

### 2026-11-12｜Trae：V2-01 旧项目盘点与重建方案

**本次目标：**
- 完成 AI_COLLABORATION §7 总任务第 1–3 项：盘点文件与旧技术栈、提出 V2 目录结构与模块边界、制定旧文件处理方案；只汇报方案，不写业务代码。

**实际完成：**
- 拉取并确认当前分支最新代码（bb8c4cf），工作树干净。
- 盘点结论：**main 分支仅 Initial commit（只有 2 行 README），旧项目代码实际在 origin/trae-dev**（150 文件，主源码约 9,700 行）。
- 产出完整盘点与重建方案：[docs/V2-01_inventory_and_rebuild_plan.md](./docs/V2-01_inventory_and_rebuild_plan.md)。
- 复用/重建边界：全部业务代码参考重写、不复制；参考资产=适配器抽象、experiment_packs JSON 结构、sandbox_manager 安全设计；明确不迁移 scripts/ 调试脚本、demo_shots、旧顶层文档、内置弱凭据与硬编码教程数据。
- V2 目录结构提案：单仓 `server/`（FastAPI + engine 独立引擎层）+ `web/`（Vue3）+ `desktop/`（PySide6）+ `experiments/`（用户后期导入）+ `scripts/` + `docs/`；统一跨端状态契约由 server/engine 定义；AI 密钥只在 server。
- 提出 3 个待决策项 D-1（代码执行隔离方案）/ D-2（实验定义格式）/ D-3（sandbox_manager 去留），见报告 §6。

**修改文件：**
- 新增 docs/V2-01_inventory_and_rebuild_plan.md
- 修改 AI_COLLABORATION.md（看板状态、本记录、决策表、未解决问题表）

**验证命令与结果：**
- 命令：`git status` / `git ls-tree -r origin/main --name-only` / `git ls-tree -r origin/trae-dev --name-only` / `git show origin/trae-dev:<file>`（只读盘点，未切换分支）
- 结果：当前分支 2 文件；main 仅 README；trae-dev 150 文件。行数统计：主源码合计约 9,744 行。

**未完成 / 已知问题：**
- 本方案尚未经 ChatGPT / 项目负责人审查（V2-01 处于"待审查"）。
- 本机 git 全局配置将 github.com 重写到不可达的 ghfast.top 镜像；本次全部使用命令级 `-c` 覆盖（http.proxy=127.0.0.1:10808 + http.sslBackend=openssl + url insteadOf 还原），未修改全局配置；后续 fetch/push 均需带同样参数。

**需要对方处理或确认：**
- 审查 V2-01 方案与目录结构提案，确认/调整 D-1、D-2、D-3 三个决策项。

**下一步建议：**
- 方案通过后进入 V2-02：按提案搭建 server/web/desktop 骨架，打通健康检查、前后端启动、配置读取与 pytest 基线。

**关联提交：**
- 见本文件同批次提交 SHA。

### 2026-11-12｜ChatGPT：建立 V2 协作基线
- 创建分支：feat/zhidao-shixun-v2-rebuild。
- 保留 main 作为旧项目线。
- 明确 V2 以「智导实训」最新方案为准。
- 采用通用 AI 实训引擎 + 专业软件适配器架构。
- 首期只验证 Python 网页实验和 MySQL Workbench 外部软件实验。
- 将指导颗粒度动态调整列为核心创新。
- 当前待办：Trae 先盘点文件、提出独立重建方案，不立即大规模写代码。

---

## 10. 决策记录

| 日期 | 决策 | 原因/说明 |
|---|---|---|
| 2026-11-12 | 新建 V2 独立开发分支 | 与原项目线并行，避免影响旧版本 |
| 2026-11-12 | 不沿用旧业务架构，重新设计 V2 | 避免旧实现限制新项目方向 |
| 2026-11-12 | 首期 Python + MySQL 两种环境 | 先证明跨环境实训闭环 |
| 2026-11-12 | 默认指导而非自动代操作 | 保证教学自主性和桌面操作安全 |
| 2026-11-12 | 采用四级动态指导颗粒度 | 根据实际困难提供不同深度帮助 |
| 2026-11-12 | 盘点确认：旧项目代码在 trae-dev，main 仅初始提交 | Trae 盘点发现；main 无需清理，trae-dev 只读参考不合并 |
| 2026-11-12 | V2 目录结构提案：server/web/desktop/experiments 单仓结构，engine 独立引擎层 | Trae 提案（V2-01），待审查；AI 密钥只在 server，统一状态契约由 engine 定义 |
| 2026-11-12 | 复用边界：业务代码全部参考重写；不迁移调试脚本/演示截图/旧文档/内置凭据 | Trae 提案（V2-01），待审查 |
| 2026-11-12 | AI_COLLABORATION.md 即唯一协作/交流文档，不另建交流文档 | 负责人指示；待决策项直接在本文件 §11 跟踪讨论 |
| 2026-11-12 | D-1：Python 不可信代码采用 Docker 沙箱 | 普通 subprocess + timeout 不构成安全边界；容器需禁网、非 root、只读根文件系统、资源限制；不可用时不退化为宿主机执行 |
| 2026-11-12 | D-2：实验定义采用全新规范化 JSON Schema | 参考旧 experiment_packs 的步骤组织思想，但增加 schema_version、前置条件、预期状态、白名单验证器、恢复建议等字段 |
| 2026-11-12 | D-3：不迁移旧 sandbox_manager 服务 | V2 内重新实现最小 Docker 执行接口；旧代码仅作安全设计参考 |
| 2026-11-12 | V2-01 审查通过，启动 V2-02 | 目录结构和重建边界符合项目方向；补充跨端契约版本化与桌面端最小采集要求 |
| 2026-11-12 | 跨端契约以独立包 contracts/（zhidao-contracts）承载 | 满足审查要求：版本化、desktop 不依赖 server 内部模块；JSON Schema 基线 + 漂移检测测试 |
| 2026-11-12 | web 构建使用 rollup→@rollup/wasm-node 依赖别名 | 本机 Windows Smart App Control 拦截未签名原生 .node；WASM 回退保证构建可复现（与旧 R-02 同因） |
| 2026-11-12 | .ps1 脚本一律 ASCII 英文注释 | PowerShell 5.1 在 GBK 代码页读 UTF-8 无 BOM 脚本时中文注释破坏解析（已实测复现） |

新增决策必须写入本表，不能只留在聊天记录里。

---

## 11. 未解决问题 / 风险

| 问题 | 影响 | 当前处理方式 | 状态 |
|---|---|---|---|
| 不同软件控件接口差异大 | 影响识别和定位准确率 | 分层接入，必要时专用适配器 | 待验证 |
| GitHub 仓库当前为 public；旧分支 trae-dev 据盘点含 demo_shots 个人桌面截图及弱默认凭据 | 任何人都可能读取公开分支内容；删除文件也不等于从 Git 历史中清除 | V2 不迁移截图/凭据；项目负责人需决定是否将仓库改为 private，或先清理旧分支及历史中的敏感内容；未处理前不要再提交个人数据 | 需负责人处理 |
| 视觉模型可能误判 | 可能产生错误指导 | 置信度、标准流程约束、结果验证 | 待实现 |
| 本机 8000 端口被遗留 python 进程占用（非 V2 服务，路径 .workbuddy，未处理） | V2 按默认端口启动会冲突 | V2 支持 -Port / -ApiTarget 参数；验证用 8100 | 待负责人决定是否清理 |
| 截图可能包含隐私 | 数据泄露风险 | 本地优先、最小采集、脱敏和告知 | 待实现 |
| 多方同时修改协作文档 | 可能发生覆盖 | 先拉取、合并最新内容、再提交 | 持续遵守 |
| 本机 git 将 github.com 重写到 ghfast.top 镜像且镜像不可达 | fetch/push 失败 | 命令级 `-c http.proxy=http://127.0.0.1:10808 -c http.sslBackend=openssl -c url...insteadOf` 覆盖；不改全局配置 | 已验证可用 |
| Windows schannel 证书吊销检查失败（CRYPT_E_REVOCATION_OFFLINE） | git/curl 经代理访问 GitHub 报 TLS 错误 | git 切 openssl 后端（命令级 -c） | 已验证可用 |
| Windows Smart App Control 拦截未签名原生模块 | rollup 原生 .node 加载失败 | web 构建改用 @rollup/wasm-node（V2-02 已解决并记录）；后续引入 C 扩展类依赖时需复检 | 已解决（持续注意） |
| Docker 沙箱尚未实现 | 不可信代码执行可能影响宿主机 | V2-02 已定义执行器接口与安全基线（含测试），V2-04 实现容器隔离；Docker 不可用时拒绝执行 | 接口已定义 |
| 规范化实验 JSON Schema 尚未实现 | 实验步骤与验证器可能不一致 | V2-03 定义 schema_version、字段约束和验证器白名单 | 待实现 |
| 跨端契约尚未建立 | Web/server/desktop 可能发生字段漂移 | V2-02 已建立 contracts/（版本 0.1.0，5 模型）+ Schema 漂移检测测试 | V2-02 已建立 |

---

## 12. 标准交接模板

每次 Trae 或 ChatGPT 完成工作，都按下面格式追加：

~~~markdown
### YYYY-MM-DD｜角色：Trae / ChatGPT

**本次目标：**
- 

**实际完成：**
- 

**修改文件：**
- 

**验证命令与结果：**
- 命令：
- 结果：

**未完成 / 已知问题：**
- 

**需要对方处理或确认：**
- 

**下一步建议：**
- 

**关联提交：**
- commit SHA / 链接
~~~

---

## 13. 给 Trae 的固定启动指令

每次开始工作时，按以下要求执行：

> 你正在参与「智导实训 V2」开发。先拉取当前分支最新代码，完整阅读根目录的 AI_COLLABORATION.md 和 README.md。本文件是项目唯一协作总控记录，必须遵守其中的产品定位、技术原则、首期范围、当前任务和分支纪律。先核对实际代码与进度看板，不要假设历史记录中的计划已经完成。只在 feat/zhidao-shixun-v2-rebuild 分支开发，不修改 main。完成工作后必须运行测试、提交代码，并把实际修改文件、测试命令和结果、未解决问题、下一步建议追加到本文件。若遇到冲突或需求不明确，先记录并请求确认，不要擅自偏离项目方向。

---

## 14. 给 ChatGPT 的固定工作规则

每次项目负责人说“继续项目”“查看进度”“让 Trae 继续”“审查代码”等：
1. 先读取 GitHub 本分支最新的 AI_COLLABORATION.md。
2. 必要时查看实际代码和提交记录，核实进度。
3. 根据用户新要求更新“当前任务”，明确交给 Trae 的可执行指令。
4. ChatGPT 自己完成 GitHub 文件或代码修改，也必须提交并记录。
5. 不要求用户重复转述已经写入本文件的背景和决定。
6. 不把未验证的计划描述为已完成。
7. 所有阶段以可运行、可验证、可演示为验收目标。
