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

**V2-02 基础工程骨架、V2-03 实验定义与步骤数据模型已完成。** V2-03 第五轮源码复审通过；Windows 本机全量测试 238 passed / 0 failed / 0 skipped，前端 vue-tsc + vite 构建通过。**V2-04A 已获 ChatGPT 第十六轮独立复审批准**（方案 A′ 有界采用；OBJ_DONT_REPARSE 官方组合契约仍标注 unresolved；FileId 仅作句柄间身份一致性比较；首次信任根由安装/部署阶段带外条件建立；Docker 为不可信代码主要隔离边界）。**V2-04B 阶段 A 已完成：Windows 实机环境盘点与 NTFS 门禁报告（可复现脚本 scripts/ntfs_gate_check.py）——脚本修正前原口径实测 19 PASS / 0 FAIL / 0 BLOCKED**（修正后真实重跑 18 PASS / 1 FAIL / 0 BLOCKED：T073 因子文件按 Windows 语义继承创建者令牌默认 DACL、空 DACL 前提无法建立而诚实记 FAIL；父目录 FILE_DELETE_CHILD 授权已单独实证 ev_b=True，父路径删除隔离证据由 T072 承担；FILE_ID_INFO 已按复审修正为 64 位 VolumeSerialNumber@0 + FileId@8 共 24 字节）：①方案 A′ 主路径实机验证成功——NtCreateFile(FILE_OPEN + FILE_DIRECTORY_FILE + OBJ_CASE_INSENSITIVE|OBJ_DONT_REPARSE + 绝对 \??\ 路径) 打开目录、RootDirectory 相对打开文件（FILE_NON_DIRECTORY_FILE）/子目录均 STATUS_SUCCESS；②OBJ_DONT_REPARSE 三态实证——终末 junction 与中间级 junction 均恰返回 0xC000050B（STATUS_REPARSE_POINT_ENCOUNTERED 实机值），无标志对照下 junction 被跟随且 FileId 与目标一致；③DOS 盘符映射（\??\C:）在 OBJ_DONT_REPARSE 下正常解析；④FileId/卷序列号同一性核验 same=True（仅作句柄间身份比较）；⑤删除双授权路径实测：文件 DACL deny DELETE 不阻止删除（父目录授权路径）、父目录仅授 FILE_DELETE_CHILD(0x40)+FILE_ADD_FILE 时空 DACL 子文件经父路径删除成功——R-4B-11 由威胁模型转为实测证据；**icacls 无法授予 FILE_DELETE_CHILD，需 PowerShell FileSystemAccessRule（对安装程序实现有直接影响）**；⑥共享模式对照：ERROR_SHARING_VIOLATION(32) 与 DACL 拒绝明确区分；⑦ctypes 结构实测：UNICODE_STRING=16B/OBJECT_ATTRIBUTES=48B/IO_STATUS_BLOCK=16B/FILE_ID_INFO=24B（8 字节对齐，传 20B 缓冲会越界写）；⑧GetSecurityInfo 句柄上读取 Owner/DACL 成功；⑨当前用户为 UAC 过滤令牌（Administrators deny-only、Medium IL）——令牌分类实证。**Docker 未安装：Docker 相关门禁全部 BLOCKED（不得冒充 PASS）；安装阶段带外信任根建立=NOT TESTED；阶段 C 真实 Docker 集成测试待具备 Docker Desktop 环境。** pytest 238 passed 基线不变。阶段 B（Docker 隔离执行器核心实现）按门禁结果推进，其安全声明必须以真实 Docker 环境实测为准。AI 指导、屏幕标注等业务功能尚未实现。

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
