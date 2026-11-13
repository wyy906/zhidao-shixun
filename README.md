# 智导实训 V2

> AI视觉感知与实时操作引导平台  
> 当前开发分支：feat/zhidao-shixun-v2-rebuild

## 项目是什么？

「智导实训」面向多学科数字化实验教学。平台通过视觉感知、操作状态理解和实验流程建模，观察学生的实际电脑操作，并提供步骤指导、错误诊断和结果验证。

核心架构：**通用 AI 实训引擎 + 专业软件适配器**。

首期验证两种环境：
- **Python 网页实验**：在平台内部完成编辑、运行和结果验证。
- **MySQL Workbench**：由 Windows 桌面助手识别外部软件界面并提供实时指导。

不同软件根据实际能力采用控件接口、浏览器接口、OCR/视觉识别或专用适配器。本项目不承诺未经适配就支持所有软件。

## 当前状态

**V2-02 基础工程骨架、V2-03 实验定义与步骤数据模型已完成。** V2-03 第五轮源码复审通过；Trae 报告 Windows 本机全量测试为 238 passed / 0 failed / 0 skipped（既有回归结果，不代表安全边界已获 Windows 实机证明），前端 vue-tsc + vite 构建通过。V2-04A：Trae 已完成第十五轮架构修订（docs-only，最终安全边界裁决）——①问题 A 裁决：OBJ_DONT_REPARSE 用于用户态 NtCreateFile 的支持范围官方未解决——winternl NtCreateFile 页 Attributes 描述仅列"zero or OBJ_CASE_INSENSITIVE"，与 ntdef OBJECT_ATTRIBUTES 页通用描述不一致；Microsoft External Staff Moderator（官方托管 Q&A，非产品文档）明确判定"support for the exact combination remains unresolved from these references...Authoritative clarification is still needed"，且"文档缺省≠不支持、单机成功≠契约保证"；OBJ_DONT_REPARSE 据此降级为加固标志（行为属可实测项而非文档保证项），安全闭环不再依赖其生效。②问题 B 裁决：受信任根首次打开（RootDirectory=NULL 绝对路径）的安全闭环由打开后逐级核验层独立兜底——若 reparse 被跟随，落点对象 FileId 必然不同或 owner/DACL 不符模板 → 拒绝启动；仅落点为同一对象（同卷同 FileId）时通过且无安全影响；OBJ_DONT_REPARSE 失效不影响安全性、只影响实现路径；DOS 盘符映射（对象管理器符号链接，非 NTFS reparse point）无官方背书，列为实机必测项。③最终结论选 B（官方依据不完整的有界本地演示方案）：保证三分法——文档保证（RootDirectory 相对打开、FILE_SHARE_READ 阻止重命名/删除共享语义、FILE_ID_INFO 判同一文件等）/仅实机证据（OBJ_DONT_REPARSE 实际行为、STATUS_REPARSE_POINT_ENCOUNTERED=0xC000050B 由 Moderator 答复给出、FileId/卷核验）/明确接受风险（R-4B-7/8/9、并发非快照语义、跨版本不保证）；限 Windows 10/11 + NTFS + 固定部署位置。④不推翻方案 A′ 参数（NtCreateFile + FILE_DIRECTORY_FILE/FILE_NON_DIRECTORY_FILE + Attributes=0x1040 + RootDirectory 逐级相对）；逐级 component-by-component 路线获 Moderator 印证（"combining documented behavior rather than relying on an undocumented guarantee"）；FILE_ID_INFO 判同一文件但不证明路径授权 → 核验顺序=模板/Owner 比对→卷/FileId 同一性，缺一拒绝。⑤实机验证矩阵移至 V2-04B 环境准备阶段作为前置门禁（不新增测试编号、不重跑既有测试）。⑥建议 V2-04A 进入最终复审；若 ChatGPT 第十五轮复审批准，V2-04B 可启动 Docker 执行器开发（Docker 沙箱维持不可信代码主要隔离边界 D-1；Docker 不可用仍 fail-closed）。**V2-04A 尚未获批准；V2-04B 禁止启动。** 本机未安装 Docker，真实容器测试依赖具备 Docker Desktop 的环境。AI 指导、屏幕标注等业务功能尚未实现。

仓库不内置任何演示 / 测试实验数据；实验内容由用户在 `experiments/` 导入。

## 目录结构

```
contracts/   跨端统一数据契约（独立 Python 包 + JSON Schema 基线，web/desktop 不依赖 server 内部模块）
server/      后端 FastAPI（健康检查、实验定义加载校验、验证器白名单、状态机、执行器接口占位）
web/         前端 Vue 3 + Vite + TypeScript（最小页面，显示后端连接状态）
desktop/     Windows 助手 PySide6（最小窗口：连接状态 / 暂停 / 停止）
experiments/ 实验定义 JSON（规范化 Schema 1.1 见 experiments/schema/；内容由用户导入）
scripts/     安装与启动脚本（Windows PowerShell）
docs/        设计文档与决策记录
tests/       根级测试（契约模型校验、Schema 漂移检测）
```

## 环境要求

- Windows 10/11（桌面助手仅支持 Windows）
- Python 3.11+（本仓库在 3.13.14 验证）
- Node.js 20+（本仓库在 26.13.0 验证）

## 获取代码（Windows PowerShell）

~~~powershell
git clone https://github.com/wyy906/zhidao-shixun.git
cd zhidao-shixun
git switch feat/zhidao-shixun-v2-rebuild
~~~

## 安装（已实际验证）

~~~powershell
# 需要代理时加 -Proxy 参数，例如 -Proxy "http://127.0.0.1:10808"
./scripts/setup-dev.ps1
~~~

脚本会创建根目录 `.venv`，安装 contracts（可编辑）+ server + desktop 的 Python 依赖，并执行 web 的 `npm install`。

## 当前可运行版本（V2-02 骨架，均已实测）

| 组件 | 启动命令 | 验证方式 |
|---|---|---|
| 后端 | `./scripts/start-server.ps1`（默认 8000 端口，`-Port` 可改） | `curl http://127.0.0.1:8000/health` 返回 `{"status":"ok",...}` |
| 前端 | `./scripts/start-web.ps1` | 浏览器访问 http://localhost:5173，页面显示「后端连接正常」 |
| 桌面助手 | `./scripts/start-desktop.ps1` | 窗口出现；`-Check` 仅探测后端；`-Smoke` 启动后 1.5 秒自动退出 |
| 测试 | `.venv\Scripts\python.exe -m pytest` | 全量 238 项测试通过（含 V2-02 基线 20 项：契约模型 / Schema 漂移 / 配置 / 执行器 / 健康检查；V2-03 实验定义体系 218 项，含 Schema/Pydantic 双通道镜像表驱动、schema_version 与 verifier.type 枚举镜像、状态机穷举测试） |
| 前端构建 | `npm run build`（web/ 目录内） | vue-tsc 类型检查 + vite 构建通过 |

前后端端口说明：
- 后端默认 8000；前端代理目标默认 http://127.0.0.1:8000。
- 8000 被占用时：`./scripts/start-server.ps1 -Port 8100`，并对应使用 `./scripts/start-web.ps1 -ApiTarget http://127.0.0.1:8100`、`./scripts/start-desktop.ps1 -ApiTarget http://127.0.0.1:8100`。

## 配置

- 环境变量示例见根目录 [.env.example](./.env.example)；复制为 `.env` 后修改。全部变量使用 `ZD_` 前缀。
- 项目**不内置任何默认账号 / 密码 / 密钥**；真实 `.env` 已被 .gitignore 忽略，禁止提交。

## 本机已知问题（Windows 开发注意）

1. **Smart App Control 会拦截未签名原生模块**（本机策略已开启）。rollup 原生二进制被拦截导致 `vite build` 失败，已在 web/package.json 通过 `rollup → @rollup/wasm-node` 依赖别名解决（WASM 构建，无原生模块；构建速度略慢）。
2. **npm 11 的 install-scripts 安全特性**会提示 esbuild 的 postinstall 未批准；esbuild.exe 本体随平台包安装，不影响构建，可忽略提示。
3. **PowerShell 5.1 编码**：仓库内所有 .ps1 脚本均使用 ASCII 英文注释，避免中文注释在 GBK 代码页下破坏脚本解析。自行新增 .ps1 时注意同样问题（保存为 UTF-8 with BOM 或只用 ASCII）。

## 尚未实现 / 待验证

- 业务功能（实验任务、AI 指导、屏幕标注、Docker 沙箱执行）尚未实现，当前为骨架。
- Docker 沙箱执行器：接口与安全基线已定义并测试，容器实现在 V2-04（见 AI_COLLABORATION.md 决策 D-1）。
- 生产部署、HTTPS、多用户并发：未做。

## 部署说明

首期优先保证 Windows 本地开发和演示。后续补充服务器部署、环境变量配置、数据库初始化、升级和备份说明。

**维护要求：** 启动方式、依赖、端口、配置项或部署方式发生变化时，必须同步更新本 README。所有命令必须在干净环境中实际验证后才能写成"可用"。

## 项目协作

[AI_COLLABORATION.md](./AI_COLLABORATION.md)：ChatGPT、Trae 与项目负责人共用的项目方向、开发指令、进度和交接记录（唯一协作文档）。开始工作前必须先阅读。
