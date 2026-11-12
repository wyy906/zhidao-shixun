"""智导实训 Windows 桌面助手。

职责边界（AI_COLLABORATION.md §7）：只做本地感知与标注渲染，不持有 AI 密钥，
不直接依赖 server 内部模块（跨端契约来自 zhidao_contracts，通信走 HTTP）。
"""

__version__ = "0.1.0"
