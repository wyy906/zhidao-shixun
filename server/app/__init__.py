"""智导实训 V2 服务端（FastAPI）。

分层：api（协议转换）→ engine（AI 实训引擎，V2-03 起）→ services（沙箱执行、AI 客户端）。
跨端数据契约一律来自 zhidao_contracts 包，不在本服务内重复定义。
"""
