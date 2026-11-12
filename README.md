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

**V2 正在独立重建，尚未达到可运行/可部署状态。** 不得编造尚未实现的启动命令、端口或默认账号。首个可运行版本验收后，Trae 必须补齐下面的实际步骤。

## 获取代码（Windows PowerShell）

~~~powershell
git clone https://github.com/wyy906/zhidao-shixun.git
cd zhidao-shixun
git fetch origin
git switch feat/zhidao-shixun-v2-rebuild
~~~

已有仓库：

~~~powershell
git fetch origin
git switch feat/zhidao-shixun-v2-rebuild
git pull origin feat/zhidao-shixun-v2-rebuild
~~~

## 普通用户运行方式

项目完成首个可运行版本后，本节必须写成普通用户照着做就能运行的步骤，目标是：
1. 安装必要环境（只列真正需要的依赖）。
2. 下载项目。
3. 双击启动脚本，或复制一条命令启动。
4. 打开浏览器访问本地地址。
5. 如需外部软件指导，再启动 Windows 桌面助手。

## 当前可运行版本（待开发后填写）

- 状态：开发中。
- Web 前端启动命令：待实现后填写。
- 后端启动命令：待实现后填写。
- Windows 助手启动方式：待实现后填写。
- 本地访问地址：待实现后填写。
- 测试账号：如确有需要再填写，禁止提交真实密码或密钥。

## 部署说明

首期优先保证 Windows 本地开发和演示。后续补充服务器部署、环境变量配置、数据库初始化、升级和备份说明。

**维护要求：** 启动方式、依赖、端口、配置项或部署方式发生变化时，必须同步更新本 README。所有命令必须在干净环境中实际验证后才能写成“可用”。

## 项目协作

[AI_COLLABORATION.md](./AI_COLLABORATION.md)：ChatGPT、Trae 与项目负责人共用的项目方向、开发指令、进度和交接记录。开始工作前必须先阅读。
