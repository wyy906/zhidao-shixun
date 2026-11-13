"""PySide6 桌面智能实训助手

职责：
1. 观察学生的 Windows 桌面操作（截图、窗口识别、UI Automation）
2. 通过 HTTP 与后端 AI 实训引擎通信
3. 在真实软件界面上叠加透明悬浮层，展示 AI 操作指导和标注

首期目标：
- 可启动的 PySide6 应用
- 主窗口 + 系统托盘
- 透明悬浮层框架（标注目标区域 + 显示指导文字）
- 截图 / OCR / UI Automation 的接口占位（真实实现后置）
- 与后端 AI 指导接口的 Stub 通信
"""

---

## Windows 打包

前置条件：

- Windows 10/11 x64，Python 3.13（与 `desktop/requirements.txt` 一致）
- 安装构建依赖：`python -m pip install -r desktop/requirements-build.txt`

构建：

```powershell
powershell -ExecutionPolicy Bypass -File desktop\build_windows.ps1
# 需要 zip 分发包时：
powershell -ExecutionPolicy Bypass -File desktop\build_windows.ps1 -Zip
```

产物：

- `desktop/dist/ZhidaoShixun/ZhidaoShixun.exe`（onedir，目录约 268 MB）
- 可选 `desktop/dist/ZhidaoShixun-win64.zip`（约 106 MB）

说明：

- 采用 **onedir** 模式：整个 `ZhidaoShixun` 目录一起分发，不能只拷贝 exe；
  目标机不需要安装 Python。
- 产物**不包含** `backend/.env`、AI 密钥或任何令牌；配置仍从
  `~/.zd_shixun/desktop_config.json` 读取。
- 产物**未签名**。若目标机启用了 Smart App Control / WDAC，未签名 exe 会被
  应用控制策略拦截，需要先用组织代码签名证书签名再分发。
- `dist/`、`build/` 已在 `.gitignore` 中，构建产物不入库。
