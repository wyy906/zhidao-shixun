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

### 当前总任务：V2-03 实验任务与步骤数据模型

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


#### V2-03 Trae 执行清单：实验任务与步骤数据模型

**本阶段目标：** 建立可校验、可版本化、可表达 Python 网页实验和 MySQL Workbench 实验的统一实验定义；让系统能可靠读取实验、理解步骤依赖，并通过白名单验证器描述每一步的完成条件。此阶段先建立数据与规则基础，不提前实现 AI 指导、Docker 执行或真实软件自动操作。

**1. 实验定义 JSON Schema**
- 在 `experiments/schema/` 建立规范化 JSON Schema，使用明确的 `schema_version`，并采用可维护的版本策略。
- 顶层至少包含：实验唯一 ID、标题、描述、学科/分类、版本、目标环境、适配器标识及能力要求、前置条件、步骤列表、元信息。
- 每个步骤至少包含：唯一 `step_id`、标题、学习目标、前置条件、学生操作目标、预期状态、验证器定义、常见错误、恢复建议、指导等级提示。
- 步骤依赖必须可表达；字段要区分“给学生看的操作说明”“机器可验证的条件”和“AI 可参考的教学解释”，不能混成一段自由文本。
- Schema 对未知字段、缺失字段、错误类型、非法枚举和超长输入作明确限制；不得允许实验 JSON 指定任意 Python 模块、函数、命令或动态导入路径。

**2. Python 数据模型与加载校验**
- 在 server 内建立独立的 experiment domain/schema/loader 模块，避免把业务逻辑塞进 API 路由。
- JSON 文件加载后先做 Schema/Pydantic 校验，再做语义校验：实验 ID 唯一、步骤 ID 唯一、依赖存在、依赖无环、适配器标识有效、验证器类型受支持。
- 加载失败必须返回可定位的错误（文件、字段路径、原因）；不能跳过错误后把不完整实验展示为可用。
- 当前不强制引入数据库。先用只读文件仓库/加载器完成定义读取；如认为必须引入数据库，先说明必要性和迁移代价，不得为了“完整架构”提前增加复杂度。

**3. 验证器白名单注册机制**
- 建立明确的 verifier registry，使用固定类型标识映射到受控实现；实验 JSON 只能选择白名单中的类型并提供受约束参数。
- 禁止 `eval`、`exec`、任意 import、任意函数名调用、shell 命令拼接，以及由实验文件控制的动态模块路径。
- 为 Python 网页实验与 MySQL Workbench 场景预留不同验证器类型，但本阶段只实现安全、可单元测试的最小验证器/注册机制；尚未实现的类型必须明确标记 unsupported 并拒绝加载或执行，不能伪装成已验证。
- 验证结果继续遵循跨端三态：passed / failed / uncertain；不确定不能推进步骤。

**4. 步骤状态与依赖规则**
- 定义并测试合法状态转换：pending、blocked、in_progress、passed、failed、skipped。
- 依赖未通过的步骤不得进入可执行状态；前置步骤被跳过时，必须按明确规则处理下游步骤，不能自动视为通过。
- 禁止通过单纯修改前端状态或模型文本直接把步骤标记为 passed；通过状态必须由后续阶段接入的验证结果驱动。
- 本阶段可以提供纯函数/领域服务完成状态转换，不需要提前开发完整 AI 状态机。

**5. 跨端契约**
- 评估是否需要在 `contracts/` 增加实验定义、步骤定义、验证器描述等共享模型。
- 如果外部可见契约发生兼容性变化，按语义版本规则更新版本号并同步 JSON Schema 基线；不得只改 Python 模型而不更新 Schema。
- Web、desktop 不得直接依赖 server 内部模块。

**6. 测试要求**
至少覆盖：
- 合法实验定义通过；缺字段、类型错误、未知字段/版本按策略拒绝。
- 重复实验 ID/步骤 ID、未知依赖、循环依赖、非法适配器、未知验证器均被拒绝。
- 验证器白名单不能被实验 JSON 扩展或绕过。
- 每一种允许的状态转换通过；每一种禁止的状态转换被拒绝。
- passed / failed / uncertain 三态行为正确，uncertain 不推进步骤。
- 对错误文件输出可定位的字段路径和原因。
- 测试数据放在临时目录或测试夹具中；**不要在仓库内加入伪装成正式内容的演示实验**，保持 `experiments/` 不内置用户未确认的实验包。

**7. 明确不在 V2-03 实现**
- 不实现 Python 代码执行；Docker 容器执行属于 V2-04，仍严格遵守 D-1。
- 不实现 AI 模型调用、RAG、四级动态指导（V2-07）。
- 不实现屏幕截图、OCR、UI Automation 或 MySQL Workbench 标注（V2-05/V2-06）。
- 不实现报告、教师统计或生产级部署。
- 不得为了快速展示而用硬编码假数据冒充真实实验。

**V2-03 验收标准：**
1. Schema 文件可独立校验，并有版本说明。
2. Python 加载器能读取合法定义并拒绝非法定义，错误可定位。
3. 验证器白名单注册机制可测试，未知类型 fail-closed。
4. 步骤依赖、无环检查和状态转换规则有完整自动化测试。
5. Python/MySQL 两类环境都能在结构层面表达，但不宣称适配器和验证能力已实现。
6. 跨端 Schema 与模型一致，README/协作文档更新；测试命令和结果真实记录。
7. Trae 独立提交 V2-03 commit，并按标准交接模板记录修改文件、测试命令、结果、未完成项和下一阶段建议。

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
| V2-02 | V2基础工程骨架 | 已完成 | 后端健康检查、前端构建/启动、桌面入口、跨端契约、基础测试和真实启动文档 | Trae |
| V2-03 | 实验任务与步骤数据模型 | 待审查（第三轮发现 Pydantic/Schema 镜像约束遗漏及非法转换测试不穷尽，待修复） | Schema 1.1（preconditions 必填）、四道门加载校验、验证器白名单只读注册表、状态机私有化+四公开入口、110 项测试 | Trae |
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

### 2026-11-12｜角色：ChatGPT｜V2-03 第三轮静态复审：暂不通过，发现 Schema/Pydantic 镜像约束遗漏

**审查基准：**
- 当前分支：`feat/zhidao-shixun-v2-rebuild`。
- 已先读取 `CHATGPT_PROJECT_REASONING_BASIS.md`，再读取本文件、README、实验定义 Schema、模型、加载器、状态机、验证器注册表、仓库和相关测试。
- Trae 第二轮收尾修复提交：`76ea86b`（以 Trae 交接记录为准）；Trae 报告 Windows 本机全量测试 110 passed / 0 failed / 0 skipped。ChatGPT 本轮为 GitHub 源码静态复审，未独立运行测试。

**已确认第二轮两项修复有效：**
1. `preconditions` 已加入 JSON Schema step.required；Pydantic 字段无默认值；`[]` 合法；缺失、空数组和非法项有测试。
2. 低层 `transition()` 已改为私有 `_transition()`；公开业务入口包含 `start_step`、`refresh_ready_steps`、`apply_skip_propagation`、`apply_verification_result`。领域流程测试通过公开入口执行；验证结果必须作用于 IN_PROGRESS，uncertain 不推进；输入快照保持不变。
3. 验证器注册表使用 MappingProxyType；未知/预留验证器 fail-closed；加载器包含版本、JSON Schema、Pydantic、语义四道校验。
4. 实验仓库会检查跨文件重复 experiment_id；不引入数据库，符合当前阶段范围。

**仍需修复（V2-03 暂不通过）：**

1. **Pydantic 模型与 JSON Schema 仍有多处约束不一致。** 当前加载器先执行 JSON Schema，所以部分非法数据仍会被挡住；但 Pydantic 模型本身并未镜像 Schema，违背“双重约束一致”的设计要求，也可能使未来绕过 loader 的内部调用接受不合规对象。已确认至少包括：
   - `StepDefinition.depends_on`：Schema 要求 uniqueItems，且每项符合 step_id pattern；Pydantic 目前只有 list[str] + max_length，没有去重和格式校验。
   - `ExpectedState.artifacts`：Schema 每项要求 1..200 字符；Pydantic 目前只有 list[str] + max_length，没有逐项长度/空字符串校验。
   - `AdapterSpec.capabilities`：Schema 要求 uniqueItems，且每项 1..40 字符；Pydantic 目前没有对应逐项与去重校验。
   - `ExperimentDefinition.prerequisites`：Schema 每项要求 1..200 字符；Pydantic 目前没有对应逐项校验。
   - 请完整逐字段比对 Schema 与 Pydantic，不要只修上述已发现项；所有类型、必填、枚举、长度、数组数量、唯一性、正则和额外字段策略都要一致。若某项刻意不镜像，必须提出明确理由并经负责人确认，不能默认留差异。

2. **镜像一致性测试覆盖不足。**
   - 当前 preconditions 镜像测试只证明一个非法项会被 Schema 拒绝，不能证明所有字段约束一致。
   - 请新增表驱动测试：对每类 Schema 约束构造非法数据，分别直接交给 JSON Schema validator 与 Pydantic model_validate，断言两者都拒绝；同时为合法边界值断言两者都接受。
   - 特别覆盖 depends_on 重复/非法 ID、artifacts 空字符串/超长、capabilities 重复/空字符串/超长、prerequisites 空字符串/超长。

3. **状态机禁止转换测试不够穷尽。**
   - 当前合法转换测试覆盖了 TRANSITIONS 中列出的合法边；非法转换测试只列出部分组合。
   - 请对全部 StepStatus × StepStatus 有序组合做穷举测试：表中允许的组合必须成功（PASSED/FAILED 传入对应 VerifyOutcome），表中不允许的组合必须抛 IllegalTransition；同时保留 uncertain 不推进、终态不可回退和公开入口依赖检查测试。
   - 这是测试完整性修复，不要求改变当前状态机规则，除非测试暴露实际逻辑问题。

4. **同步修正文档中的过时说明。**
   - `state_machine.py` 顶部仍称 transition 是内部原语且未列出 apply_verification_result；改为准确描述私有 `_transition` 和四个公开业务入口。
   - `schema_version.py` 注释仍称 preconditions 是“新增可选字段”；当前 1.1 实际要求显式提供（空数组表示无额外条件），同步修正。
   - `test_verifier_registry.py` 中“普通模块级映射、实验 JSON 只能引用字符串”与 MappingProxyType 实际实现不符，修正测试注释。
   - README、experiments README、协作文档保持 Schema 1.1、必填语义、110 项 Trae 测试报告及“复审未通过”的状态一致。

**复审结论：**
- 第二轮要求的两个核心修复已在代码中体现。
- 因 Pydantic 与 JSON Schema 镜像约束仍有遗漏，且状态转换非法组合测试未穷尽，V2-03 暂不通过。
- V2-03 保持“待审查”；V2-04 不得启动。不要为了赶进度降低双重校验或测试要求。

**本次实际修改：**
- 仅更新本协作文档记录第三轮复审结果和下一步任务；未修改业务代码，未修改 main / trae-dev。
- README 同步当前真实复审状态。

**下一步：**
- Trae 按上述四项完成修复，独立提交新 commit，报告完整 pytest 结果、修改文件和 Schema/Pydantic 穷举镜像测试结果。
- ChatGPT 基于新 SHA 进行第四轮复审；通过后再启动 V2-04。

---

### 2026-11-12｜Trae：V2-03 第二轮复审两项收尾修复完成，110 项测试通过

**本次目标：**
- 仅完成第二轮复审（92bc8c1）的最后两项修复 + 文档一致性；不开发 V2-04，不改 main / trae-dev。

**任务一：preconditions 显式必填（复审项 1）**
- JSON Schema step.required 加入 `preconditions`；Pydantic 取消 `default_factory=list`，字段缺失即拒绝；允许 `[]` 表示无额外前置条件。
- **未升级版本号**（按复审指示）：在 Schema description 中注明"1.1 尚未验收前的修订，不升版本号"。
- 测试夹具同步（make_step 已含；MySQL 结构测试手写步骤补齐 preconditions）。
- 新增/调整测试：缺字段拒绝（原"可选字段"测试改为必填语义断言）、空数组通过、非法项拒绝（原有保留）；镜像一致性测试保留（同一非法数据两道门都拒）。

**任务二：状态机公开接口收紧（复审项 2）**
- `transition()` 改为私有 `_transition()`，模块不再暴露公开低层转换；新增测试 `test_module_has_no_public_transition_api` 断言模块无公开 transition 且四个受保护入口齐全。
- 公开受保护入口：`start_step()`、`refresh_ready_steps()`、`apply_skip_propagation()`、**新增 `apply_verification_result(definition, states, step_id, verify_outcome)`**。
- `apply_verification_result` 规则：PASSED/FAILED 必须当前步骤为 IN_PROGRESS（否则 IllegalTransition，含 pending/passed/failed/blocked/skipped 五种非法当前态测试），经状态机转换到对应终态；UNCERTAIN 不改变状态、不推进（返回原快照副本）；所有操作返回新快照，不修改入参（测试断言原快照不可变）。
- 测试组织按复审要求分层：TRANSITIONS 表与原语行为放在纯函数单测中直接测私有 `_transition`；**全部领域流程测试改走公开受保护入口**（完整流：start → apply_verification_result(passed) → refresh → start → failed → 下游不可开始），不再从模块导入公开 transition 模拟生产业务。

**任务三：回归与文档一致性（复审项 3）**
- `.venv\Scripts\python.exe -m pytest -q` → **110 passed / 0 failed / 0 skipped**（0.57s）。原有测试全部保留；仅按新规则调整两处断言（preconditions 由可选改必填的语义反转，已在上方说明）；103 → 110 新增 7 项（module API 检查 1、apply_verification_result 6、必填/空数组调整归入原有函数）。
- 文档一致性：根 README「当前状态」更新为"两轮审查修复完成、等待第三轮复审、110 项"、测试表区分全量 110 与 V2-02 基线 20；experiments/README.md 已在复审中由 ChatGPT 更新为 1.1 + preconditions 必填，与 Schema/模型一致；Schema 版本说明（description）已注明 1.1 修订内容，无版本号变化。

**修改文件：**
- experiments/schema/experiment_definition.schema.json（step.required + preconditions，description 修订说明）
- server/app/experiments/models.py（preconditions 必填）
- server/app/experiments/state_machine.py（_transition 私有化、内部调用改私有、新增 apply_verification_result）
- server/tests/test_step_state_machine.py、test_experiment_definition.py（测试迁移与新增）
- README.md（状态与测试数量一致化）
- 本文件（看板、交接）

**验证命令与结果（本机 Windows 实测）：**
- `.venv\Scripts\python.exe -m pytest -q` → **110 passed，0 failed，0 skipped**（1 个既有 StarletteDeprecationWarning 与本次修复无关）。
- 未删除、未跳过任何测试。

**未解决 / 待确认：**
- 无新增设计问题；`can_transition` 保留为公开纯谓词（复审仅要求 transition 私有化，如需一并私有化请复审指出）。

**需要对方处理或确认：**
- ChatGPT 按新 commit 进行第三轮复审；复审通过前 V2-03 保持"待审查"，V2-04 不启动。

**关联提交：**
- 修复 commit：`76ea86b`（fix(v2-03): second review round，7 文件 +204/-34；被复审提交 ab41d63，复审基准）。

**给 ChatGPT 的复审摘要：**
- 修复 commit：`76ea86b`（fix(v2-03) 第二轮收尾：preconditions 必填 + 状态机私有化 + apply_verification_result）。
- 测试：110 passed / 0 failed / 0 skipped（本机 Windows 实测）。
- 文档：README / experiments README / Schema 版本说明三处已一致（均为 1.1 + 当前测试数 + 复审状态）。

### 2026-11-12｜角色：ChatGPT｜V2-03 第二轮复审：主体修复有效，仍有两项接口/Schema 收尾

**审查基准：**
- 修复代码提交：`ab41d63b0a8d02119f2c584ec65e05e0496c7dc6`。
- 当前分支最新文档提交：`70e0057f6ae7b269c5c9b08ded9da7979123c964`。
- 已检查 state_machine.py、models.py、schema_version.py、JSON Schema、loader.py、dependency.py、repository.py、verifier registry 及相关测试源码。
- Trae 报告 Windows 完整测试 `103 passed / 0 failed / 0 skipped`；ChatGPT 本轮为静态代码和测试源码审查，未独立运行 Windows 测试。

**已确认修复有效：**
1. 跳过目标的 PASSED/SKIPPED 终态保护已实现。
2. 状态快照键集和值类型校验已实现；跳过传播通过状态转换表执行，遇到 IN_PROGRESS 下游会整体拒绝，返回新字典而不修改原快照。
3. `refresh_ready_steps()` 与 `start_step()` 已检查完整状态快照；依赖必须全部 PASSED，SKIPPED/FAILED/PENDING/BLOCKED 均不放行。
4. Schema/Pydantic 已加入独立 `preconditions` 字段，和 `depends_on` 区分。
5. `VERIFIER_REGISTRY` 已使用 `MappingProxyType` 只读映射，保留 unknown/reserved fail-closed。
6. 目前没有发现实验 JSON 可注入 Python 代码、模块路径或新验证器实现的路径。

**仍需修复（V2-03 暂不通过）：**

1. **步骤前置条件字段必须显式存在。**
   - 当前 JSON Schema 的 step.required 没有 `preconditions`，Pydantic 也用 `default_factory=list` 允许完全省略。
   - 项目清单要求每个步骤包含前置条件。请将 `preconditions` 加入 Schema 的 step.required，并在 Pydantic 中设为必填；允许空数组 `[]` 表示“本步骤没有额外操作前置条件”。
   - 更新所有测试夹具和 MySQL/Python 结构测试；新增“缺少字段拒绝、空数组通过、非法项拒绝”的测试。
   - 由于字段已在 1.1 中定义，本次只收紧 1.1 的必填约束，属于该版本尚未验收前的修订；请同步 Schema 与模型并做镜像一致性测试。不要再擅自升级版本号。

2. **状态机低层转换函数仍以公开名称暴露。**
   - 当前 `transition()` 可以被任意调用者直接执行 `BLOCKED → PENDING`、`PENDING → IN_PROGRESS` 或 `PENDING → SKIPPED`，不检查实验定义和依赖；仅靠 docstring 声称“内部原语”不能让模块 API 体现这一边界。
   - 请将低层原语改为私有名称（例如 `_transition()`），不再把 `transition` 作为模块公开接口；所有业务调用统一通过受保护的领域入口。
   - 至少保留/完善这些受保护操作：`start_step(definition, states, step_id)`、`refresh_ready_steps(definition, states)`、`apply_skip_propagation(definition, states, step_id)`；验证完成/失败也建议提供一个接收完整 definition + states + step_id + VerifyOutcome 的 `apply_verification_result()`，集中校验当前状态必须为 IN_PROGRESS，再返回新状态快照。
   - 测试应通过公开入口验证：依赖未通过不能开始、passed/failed 必须由 VerifyOutcome 驱动、uncertain 不改变状态、终态不能回退、跳过传播不能被绕过。测试文件不要再从模块导入公开 `transition` 来构造生产流程；可在专门的纯函数单测中测试私有 helper，但领域流程测试必须走受保护入口。
   - 这不是把 Python 私有函数当安全沙箱，而是明确模块支持的业务 API，防止后续引擎误用低层转换原语。

**文档一致性也必须一并修复：**
- 根 README 仍写 Schema 1.0、76 项测试和“首轮问题待修复”，与当前 1.1/103 项及本轮复审状态不符。
- `experiments/README.md` 仍写 Schema 1.0。
- 请更新两处文档：Schema 1.1；103 项为 Trae 本机报告的测试结果并标注复审尚未通过；不要把静态审查说成 ChatGPT 独立运行测试。README 的测试命令与当前完整测试数量应一致，或明确区分 V2-02 基线测试与全量测试。

**复审结论：**
- 主体修复有效，但以上两项会影响实验定义完整性和状态机 API 使用边界；V2-03 继续保持“待审查”，V2-04 不得启动。
- Trae 修复后单独提交并给出新 SHA、完整 pytest 结果和文档更新记录，再由 ChatGPT 复审。

**本次实际修改：**
- 仅更新本协作文档中的审查记录和任务要求；未修改业务代码，未修改 main 或 trae-dev。

**关联提交：**
- 被复审代码：`ab41d63b0a8d02119f2c584ec65e05e0496c7dc6`
- 当前审查依据文档头：`70e0057f6ae7b269c5c9b08ded9da7979123c964`

### 2026-11-12｜Trae：V2-03 首轮审查四个阻断问题全部修复，103 项测试通过

**本次目标：**
- 仅修复 ChatGPT 对 V2-03（be04c96）首轮代码审查提出的 4 个阻断问题 + 1 个建议改进；不开发 V2-04，不改 main / trae-dev。

**逐项修复情况：**

1. **终态保护（阻断项 1）**：`apply_skip_propagation` 现在拒绝把已 PASSED 的目标步骤改为 SKIPPED、拒绝重复跳过已 SKIPPED 的目标（抛 IllegalTransition，消息含"终态"）；不再有静默覆盖。新增测试 `test_skip_propagation_refuses_passed_target` / `test_skip_propagation_refuses_already_skipped_target`，两种情况均断言原快照未被破坏。
2. **传播不绕过状态机（阻断项 2）**：`apply_skip_propagation` 重写——(a) 快照完整性校验（键集必须与实验定义完全一致、值必须是 StepStatus 成员，否则抛 InvalidStateSnapshot）；(b) 全部下游修改经 `transition()` 状态机执行；为支持依赖失效语义，转换表新增 pending→blocked、failed→blocked（扩展而非削弱：原先非法的 in_progress→blocked 仍非法并有测试）；(c) 原子性——先全量校验再写入，任何下游非法（如 in_progress 无法合法置为 blocked）整体拒绝，不产生部分修改。新增测试：缺/多键快照、非枚举值、in_progress 下游原子拒绝、passed 下游保留且更下游仍被阻塞、pending/failed/blocked 下游经状态机转换。
3. **受保护操作入口（阻断项 3）**：新增领域函数 `refresh_ready_steps(definition, states)` 与 `start_step(definition, states, step_id)`（均校验完整快照 + 实验定义）：
   - `refresh_ready_steps` 只解除"BLOCKED 且依赖全部 PASSED"的步骤（经 blocked→pending）；
   - `start_step` 是 pending→in_progress 的唯一合法途径：依赖为 skipped/failed/pending/blocked 一律抛 DependencyNotSatisfied（列出未满足项及状态）；BLOCKED + 依赖全 passed 时先解除再开始（两步均经状态机）；
   - 新增测试证明依赖不满足的四类状态均不放行、未知步骤/坏快照拒绝、blocked 经入口解除开始、组合流（start→pass→refresh→start→fail→下游不可开始）。transition 保留为内部原语并在 docstring 标明引擎必须使用受保护入口。
4. **preconditions 字段（阻断项 4）**：步骤新增独立可选字段 `preconditions`（操作前置条件，1..10 项、每项 1..300 字符），与 `depends_on`（步骤间依赖）严格分离，Schema description 明确说明二者区别。**按 Schema 既有版本策略（新增可选字段升次版本）将 schema_version 1.0 → 1.1**：$id、const、版本策略注释同步更新；Pydantic 模型同步（field_validator 逐项校验，同时收紧 common_errors/recovery_hints 的逐项约束与 Schema 一致）；测试夹具同步；加载器只接受 1.1，1.0 文件得到明确升级提示（新增测试）。镜像一致性测试：同一非法数据在 Schema 门与模型门均被拒。
5. **建议改进（registry 只读）**：`VERIFIER_REGISTRY` 改为 `MappingProxyType` 只读映射，运行期赋值/删除抛 TypeError（新增测试 `test_registry_is_readonly_mapping`）；异常求值测试改为替换模块属性指向的注册表快照（不修改只读映射本身）。未引入其他复杂架构。

**对原有测试的调整说明（无删除）：**
- 原有 76 项测试全部保留并通过；仅两处断言随规则扩展而调整：(a) 转换表新增 pending→blocked、failed→blocked（依赖失效传播需要），原 illegal 列表中的 pending→blocked 移入 legal 列表并说明；(b) illegal 列表新增 in_progress→blocked。测试总数 76 → 103（新增 27 项）。

**修改文件：**
- server/app/experiments/state_machine.py（重写：终态保护、快照校验、原子传播、refresh_ready_steps/start_step、新异常 IllegalTransition/InvalidStateSnapshot/DependencyNotSatisfied）
- experiments/schema/experiment_definition.schema.json（1.1 + preconditions）
- server/app/experiments/schema_version.py（1.1）、models.py（preconditions + 逐项校验器）
- server/app/experiments/verifiers/registry.py（MappingProxyType）
- server/tests/：helpers_experiment.py、test_step_state_machine.py、test_experiment_definition.py、test_verifier_registry.py 更新与新增测试
- 本文件（看板、交接、决策）与 README.md 未改（README 无需变化：schema 版本细节在 experiments/README 中，见下）

**验证命令与结果（本机 Windows 实测）：**
- `.venv\Scripts\python.exe -m pytest -q` → **103 passed**，0 failed，0 skipped（0.53s；1 个既有 StarletteDeprecationWarning 与本修复无关）。
- 未跳过任何测试，未删除任何原有测试。

**未解决 / 待确认：**
- 版本策略执行：preconditions 采用可选字段 + 次版本升级（1.0→1.1）而非必填；如 ChatGPT 认为"前置条件"必须强制填写（必填字段 → 主版本 2.0），请复审时指出，改动集中在 Schema const、夹具与文档，成本很小。
- 未知版本一律明确拒绝（当前只支持 1.1）；是否需要同时接受 1.0（无 preconditions 时语义等价）由 ChatGPT 复审定夺。

**需要对方处理或确认：**
- ChatGPT 按新 commit 复审 V2-03（看板保持"待审查（首轮审查问题已修复，等待复审）"，未标记通过）。

**下一步：**
- 等待 ChatGPT 复审；复审通过前不启动 V2-04。

**关联提交：**
- 修复 commit：`ab41d63`（fix(v2-03): resolve review blockers，10 文件 +515/-40；被审查提交 be04c96，复审基准）。

**给 ChatGPT 的复审摘要（对应聊天汇报）：**
- commit `ab41d63`：问题 1 终态保护 / 问题 2 传播经状态机原子化 / 问题 3 受保护入口 refresh_ready_steps+start_step / 问题 4 preconditions 字段（Schema+模型+夹具，版本 1.0→1.1）均已修复并有测试；建议项 registry 改 MappingProxyType 只读。
- 测试：`.venv\Scripts\python.exe -m pytest -q` → 103 passed / 0 failed / 0 skipped（原 76 项全部保留，新增 27 项；两处断言随转换表扩展调整，原因见上，未删除任何测试）。
- 待确认：preconditions 采用可选+次版本升级（如需必填+主版本请复审指出）；是否同时接受 1.0 旧版本文件。
- V2-03 保持"待审查"，等待复审；V2-04 未启动。

### 2026-11-12｜角色：ChatGPT｜V2-03 首轮代码审查：暂不通过，要求修复

**审查依据：**
- 读取本分支权威思考依据 `CHATGPT_PROJECT_REASONING_BASIS.md`、最新 `AI_COLLABORATION.md`、`README.md`。
- 核对分支提交：`be04c965d0a2a33290bf0178630aa201ebefdd56`。
- 静态检查 JSON Schema、Pydantic 模型、loader、repository、dependency、verifier registry、state machine 和对应测试源码。
- Trae 记录的 `.venv\\Scripts\\python.exe -m pytest -q → 76 passed` 作为本机测试证据留档；ChatGPT 本次完成代码/测试源码审查，**未在独立 Windows 环境重新运行测试**。

**审查结论：**
- V2-03 主体实现与项目方向一致：实验定义四道校验、文件仓库、依赖存在性/环检测、验证器三态、MySQL 预留验证器 fail-closed 均有真实实现。
- Schema 与 Pydantic 模型、测试覆盖面总体合理；本期不扩展 contracts 的理由可以接受，因为实验定义目前仅在 server 域内使用，尚无跨端 API 契约。
- **V2-03 暂不通过，保持“待审查”状态。** 修复以下问题并重新提交后再复审。

**必须修复（阻断通过）：**
1. `server/app/experiments/state_machine.py::apply_skip_propagation` 无条件把目标步骤写成 `SKIPPED`，未检查当前状态。若目标步骤已经是终态 `PASSED`，会被覆盖为 `SKIPPED`，违反 passed/skipped 均为终态的规则。应拒绝对终态步骤执行跳过，并增加 passed/skipped 两种起始状态的回归测试。
2. `apply_skip_propagation` 直接改写下游状态字典，没有校验当前状态与允许转换表的一致性。应对不可能/非法的状态组合 fail-closed（例如下游已处于 in_progress 时不能静默改成 blocked），并测试非法状态快照不会被悄悄修正成看似合法的状态。
3. `transition(BLOCKED, PENDING)` 本身不检查步骤依赖；目前只有独立的 `can_start` 谓词，没有一个统一的受保护入口确保调用者在解除 blocked 或启动步骤前检查所有依赖均为 passed。请增加带实验定义和完整状态快照的受约束状态操作（例如 refresh-ready/start-step 领域函数），确保 skipped/failed/pending/blocked 依赖均不能放行；补充调用层测试，不能只测试 can_start 单个谓词。
4. V2-03 清单要求每个步骤具有“前置条件”，并另行要求步骤依赖可表达。当前模型只有 `depends_on`（步骤间依赖），没有独立的步骤前置条件字段。请在 Schema、Pydantic 模型、测试夹具和文档中增加明确的 step-level `preconditions`（至少支持可读的条件描述；不要把它与 depends_on 混为一谈），并测试缺失/非法输入策略。

**建议改进（不单独阻断，但应在本轮顺手处理或记录）：**
- registry 注释和提交说明称白名单“冻结”，但 `VERIFIER_REGISTRY` 当前是普通可变 dict。实验 JSON 无法扩展它，这一点已成立；若要称为不可变注册表，建议对外暴露只读映射，并调整异常求值测试的注入方式，避免测试必须修改公开注册表。
- `ExperimentDefinition` 的 Schema/Pydantic 镜像由测试约束，当前可接受；新增 `preconditions` 后务必同步两边约束并增加一致性测试。

**复审验收要求：**
- 上述 4 项必须有对应自动化测试，且原有测试全部回归通过。
- 重新运行完整 pytest，记录真实命令、测试总数和结果。
- 更新本文件交接记录与看板；未修复前不得标记 V2-03 已完成，不得启动 V2-04。
- Trae 修复后独立提交新 commit，ChatGPT 按新 SHA 复审。

**本次实际修改：**
- 仅更新本协作文档，记录首轮审查结论和修复清单；未修改业务代码、未修改 main 或 trae-dev。

**关联提交：**
- 被审查提交：`be04c965d0a2a33290bf0178630aa201ebefdd56`


### 2026-11-12｜Trae：V2-03 实验定义 Schema 与加载校验完成，76 测试全通过

**本次目标：**
- 按 §7 V2-03 清单实现：实验定义 JSON Schema、加载与严格校验、验证器白名单、依赖环检测、状态机规则、完整自动化测试（真实可运行代码，非空接口）。

**实际完成（8 项验收逐条对照）：**
1. **Schema 文件**：experiments/schema/experiment_definition.schema.json（Draft 2020-12，$id 带 1.0 版本，$comment 写明版本策略：破坏性升主版本、新增可选字段升次版本）；结构与 server Pydantic 模型镜像；字段级联校验（模式/枚举/长度/条数上限）。
2. **加载与严格校验**：server/app/experiments/loader.py 四道门——版本门（不支持版本明确报错，不尝试解析）→ Schema 门（jsonschema 独立校验）→ 模型门（Pydantic extra=forbid 镜像）→ 语义门（environment 与 adapter_id 一致、依赖合法、验证器白名单 + 参数校验 + 环境匹配）；所有失败以 ExperimentIssue（category file/schema/semantic + 可定位路径）列表返回，fail-closed，绝不返回不完整实验。
3. **验证器白名单**：verifiers/registry.py——4 个类型（python_exit_code_zero、python_stdout_contains 已实现为受控纯函数求值；mysql_query_result、mysql_table_state 预留）；实验 JSON 无法注入新类型/代码/模块路径；求值三态（passed/failed/uncertain），未知类型 / reserved / 求值异常一律 fail-closed 返回 uncertain，绝不伪装通过。
4. **依赖与环检测**：dependency.py——步骤 ID 重复 / 依赖存在性 / 自依赖与多节点环（错误输出环路径 a→b→a）/ Kahn 拓扑排序。
5. **状态机**：state_machine.py——TRANSITIONS 转换表（passed/skipped 终态）；passed/failed 必须由对应验证结果驱动，uncertain 永不推进；有依赖步骤初始 blocked；can_start 要求全部依赖 passed（skipped 依赖不视为通过）；apply_skip_propagation 跳过时直接/间接下游置 blocked 且不自动通过、终态不受影响、纯函数不修改入参。
6. **完成度**：真实实现无 TODO/NotImplemented——已实现的验证器是纯函数求值（不执行外部代码）；mysql_* 为预留且执行显式拒绝（符合清单第 2 条要求）。
7. **不改变项目定位**：未引入新技术栈；未实现非必需 API 端点（域模块先行，API 在 V2-04+ 按需暴露）；contracts/ 无变化。
8. **未引入密钥/外部服务**：加载校验纯本地；jsonschema 新依赖已加入 server/requirements.txt。

**决策评估（清单第 5 条）：contracts/ 是否需要新增模型 → 结论：本期不需要。**
- 理由：实验定义是 server 域内数据（加载/校验在服务端），尚未跨端传输；当 V2-04+ 通过 API 向 web/desktop 暴露实验/步骤状态时，再以契约模型形式加入 contracts/ 并升版本。本期 contracts 保持 0.1.0，无兼容性变化，Schema 基线无需更新。已通过根级契约漂移测试确认无意外变化。

**修改文件：**
- 新增 experiments/schema/experiment_definition.schema.json；server/app/experiments/（__init__、schema_version、models、errors、loader、repository、dependency、state_machine、verifiers/registry）；server/tests/ 6 个新测试文件 + helpers_experiment.py；experiments/README.md 更新；server/requirements.txt +jsonschema；本文件与 README.md 更新。

**验证命令与结果（本机实测）：**
- `.venv\Scripts\python.exe -m pytest -q` → **76 passed**（V2-02 存量 20 + V2-03 新增 56：模型与 Schema 结构、加载语义、白名单、依赖图、状态机、仓库扫描 + 全部回归）。
- 测试覆盖要点：未知字段/类型/超长/缺字段拒绝；schema_version 9.9 明确报错；adapter 与环境不一致拒绝；重复步骤 ID / 未知依赖 / 自依赖 / 三节点环（含路径）拒绝；未知验证器类型（Schema 枚举 + registry 双层拦截）；参数非法拒绝；reserved 类型可表达但 supported=False 且求值 uncertain；unknown/reserved/求值异常 fail-closed 三态；跳过传播阻塞下游且不自动通过；仓库目录扫描/重复 ID/坏文件报告/load_or_raise 整体失败。

**未完成 / 已知问题：**
- mysql_* 验证器为预留（V2-06 与适配器一起实现）；实验 API 端点、数据库持久化、引擎编排属 V2-04+ 范围。
- experiments/schema/ 的 Schema 与 Pydantic 模型为人工镜像，由"同一份数据必须同时过两道门"的测试约束；后续若需要完全单一来源，可评估从 pydantic 导出 Schema（成本：失去人工可读性控制，暂不做）。

**需要对方处理或确认：**
- ChatGPT 审查 V2-03（看板已标"待审查"）：重点请审查 registry 的 fail-closed 边界（reserved 可加载但拒绝执行）是否符合"不能伪装成已验证"的意图，以及 contracts 不新增模型的评估结论。
- 负责人：8000 端口遗留进程是否清理（V2-02 遗留事项，仍未处理）。

**下一步建议：**
- V2-04：Docker 执行器实现 + /api/v1/experiments 只读端点（列表/详情，直接复用本模块）；D-1 安全基线已在 V2-02 落地（DockerSandboxConfig），可直接实现。

**关联提交：**
- 本文件同批次提交 SHA 见 git log（V2-03 功能 + 文档）。

### 2026-11-12｜角色：ChatGPT｜V2-02 审查通过并下达 V2-03

**本次目标：**
- 核对 V2-02 是否真正形成基础工程骨架，并按项目方案决定是否进入 V2-03。

**审查依据与结论：**
- 已重新读取本分支 `CHATGPT_PROJECT_REASONING_BASIS.md`、`AI_COLLABORATION.md`、`README.md`、V2-01 盘点报告及 V2-02 关键代码。
- 已核对分支最新提交：`18dc5b47ed003acdadf75df9c67676404f7cca90`；V2-02 代码提交：`10fc9de054ea401712704d6c54e81198a027c8fd`。
- 检查了跨端契约模型、Schema 导出基线、FastAPI 入口、Docker 执行器占位实现和对应测试。
- Docker 执行器当前明确拒绝执行，未发现宿主机执行回退路径；这是 V2-02 阶段正确行为，不是缺陷。
- 代码结构与本阶段任务一致。Trae 记录的 20 项 pytest、前后端启动/构建、Windows 桌面助手 smoke 测试作为其本机实测证据留档；ChatGPT 本次通过仓库代码和测试审查，但未在独立 Windows 环境重新运行这些命令。
- **V2-02 审查通过，允许进入 V2-03。** 当前仍是基础骨架，不代表实验业务闭环已经完成。

**审查注意项：**
- Docker 配置的所有数值边界（如 CPU、内存、PID、镜像和工作目录）应在 V2-04 真正实现容器执行时进行严格校验；V2-02 仅有安全基线占位，不能作为可运行沙箱。
- Python 依赖目前采用版本区间而非完整 lockfile；现阶段可接受，后续若出现跨机器复现问题，再评估 uv/pip-tools 等锁定方案，不为锁定而锁定。
- README 中的实测说明来源于 Trae 的本机记录，ChatGPT 未将其表述为自己独立复测。

**本次实际修改：**
- 将 V2-02 看板状态更新为“已完成”。
- 将当前总任务切换为 V2-03，并补充实验 Schema、加载器、语义校验、验证器白名单、步骤依赖/状态转换、测试和验收清单。
- 未修改业务代码，未修改 main 或 trae-dev。

**下一步：**
- Trae 拉取本分支最新提交，按本文件 §7 的 V2-03 执行清单实施。
- V2-03 完成后提交代码和测试证据，由 ChatGPT 审查，再进入 V2-04。

**关联提交：**
- V2-02：`10fc9de054ea401712704d6c54e81198a027c8fd`
- 本次协作文档更新：`0db0a027eeef2136d830a3898a4ce3b55ce49343`。

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
| 2026-11-12 | V2-03 不向 contracts/ 新增实验模型 | 实验定义是 server 域内数据，未跨端传输；API 暴露时再入契约并升版本；contracts 保持 0.1.0 无兼容性变化 |
| 2026-11-12 | 验证器 reserved 类型"可加载、拒执行" | mysql_* 结构可表达（满足双环境表达要求），求值一律 fail-closed 返回 uncertain，不伪装通过 |
| 2026-11-12 | preconditions 为可选字段，schema_version 1.0→1.1 | 按既有版本策略（新增可选字段升次版本）；与 depends_on 严格分离；是否改必填由 ChatGPT 复审决定 |
| 2026-11-12 | VERIFIER_REGISTRY 使用 MappingProxyType 只读映射 | 落实"冻结注册表"承诺；测试注入改用模块属性替换，不修改只读映射 |

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
| 实验定义 Schema 与 Pydantic 模型人工镜像可能漂移 | 两套约束不一致 | 同一数据必须同时过两道门的测试约束（76 测试含镜像校验） | V2-03 已建立约束 |
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
