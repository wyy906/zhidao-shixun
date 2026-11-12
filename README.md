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

**V2-02 基础工程骨架、V2-03 实验定义与步骤数据模型已完成。** V2-03 第五轮源码复审通过；Trae 报告 Windows 本机全量测试为 238 passed / 0 failed / 0 skipped，前端 vue-tsc + vite 构建通过。V2-04A：Trae 已完成第九轮架构修订，解决 ChatGPT 第八轮复审四项阻塞——①文件/目录句柄访问掩码分离：第八轮错误共用 0x00120089（其中 0x1 在目录对象上即 FILE_LIST_DIRECTORY，与“目录句柄不列目录”声明矛盾）；第九轮逐位推导为文件句柄 0x00120081（FILE_READ_DATA+FILE_READ_ATTRIBUTES+READ_CONTROL+SYNCHRONIZE，读 .env 内容+元数据+安全描述符）与目录句柄 0x00120080（FILE_READ_ATTRIBUTES+READ_CONTROL+SYNCHRONIZE，仅元数据与安全描述符，不含 0x1，不获 FILE_LIST_DIRECTORY），逐位写明各 bit 在文件/目录对象上的双语义、必要性及去除后果。②目录 DACL 权限缺口修复：第八轮父目录仅 3 ACE（OWNER RIGHTS/SYSTEM/Administrators），运行服务账户无目录 ACE，却被要求用目录句柄执行 GetSecurityInfo、查询 Owner/DACL/属性/FileId/卷序列号并作为 NtCreateFile RootDirectory——不可运行；第九轮选方案 A（最小化目录元数据读取权限），目录模板回 4 ACE：OWNER RIGHTS 0x00020000 + 运行账户 0x00100080（FILE_READ_ATTRIBUTES+SYNCHRONIZE） + SYSTEM 0x001F01FF + Administrators 0x001F01FF，运行账户目录有效权限 0x00120080 与句柄掩码逐位吻合，逐位证明不含 FILE_LIST_DIRECTORY/FILE_ADD_FILE/FILE_ADD_SUBDIRECTORY/FILE_DELETE_CHILD/DELETE/WRITE_DAC/WRITE_OWNER；方案 B（高权限组件传句柄）评估后弃用。③FILE_SHARE_DELETE 保护范围分层：分别界定 .env 文件本身（无 SHARE_WRITE/SHARE_DELETE → 他人写/删打开报 sharing violation）、直接父目录（目录句柄仅保护目录对象本身的删除/重命名，FILE_DELETE_CHILD 决定子项删除且运行账户不持有）、子文件五操作表（删目录/删内部文件/重命名目录/重命名内部文件/同名替换），不再笼统宣称目录句柄 SHARE_READ 阻止整树删除。④NtCreateFile ctypes 前置条件补齐：UNICODE_STRING 16B、OBJECT_ATTRIBUTES 48B（64 位）、IO_STATUS_BLOCK 16B、自然对齐规则、NTSTATUS 经 RtlNtStatusToDosError 转换、OBJ_CASE_INSENSITIVE=0x40、FILE_OPEN_REPARSE_POINT=0x00200000、FILE_OPEN/FILE_DIRECTORY_FILE/FILE_NON_DIRECTORY_FILE/FILE_SYNCHRONOUS_IO_NONALERT 等值、RootDirectory 句柄权限、句柄关闭与异常清理——全部标注【未验证】，实机验证前不写实现代码。⑤负向测试 N-A49~N-A64（16 项：掩码混用、意外 LIST_DIRECTORY、缺目录 ACE、READ_CONTROL 不足、SHARE 保护范围、DELETE_CHILD 误授、重命名/同名替换攻击、ctypes 结构错误、NTSTATUS 误按 Win32 处理、句柄关闭后竞争等，逐项标注 mock 可验/需 Windows 实机；累计 N-A 64 项）。以上权限语义均未实机验证。镜像锁定文件保持 pending/null 未动。**ChatGPT 第九轮复审结论：暂不批准 V2-04A。** 第九轮已修正文件/目录句柄掩码、开发模式目录元数据 ACE 和共享模式分层；但最终安装模式目录 owner=SYSTEM 时，服务账户目录 ACE `0x00100080` 不含 READ_CONTROL，无法按文档预期通过 GetSecurityInfo 读取 Owner/DACL，N-A54 的成功预期不成立；最终安装模式文件 ACE 还残留旧值 `0x00120089`，与第九轮文件句柄掩码 `0x00120081` 不一致。第十轮修订及复审通过前不实现容器执行（V2-04B）。 本机未安装 Docker，真实容器测试依赖具备 Docker Desktop 的环境。AI 指导、屏幕标注等业务功能尚未实现。

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
