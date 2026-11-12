"""统一错误响应。

所有错误返回统一结构：{"error": {"code": str, "message": str, "details": object}}。
前端与桌面助手只依赖该结构，不解析 FastAPI 默认的 {"detail": ...}。
"""

import logging

from fastapi import FastAPI, status
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

logger = logging.getLogger("zhidao.errors")


class AppError(Exception):
    """业务错误基类。code 用于机器识别，message 面向用户。"""

    def __init__(self, code: str, message: str, status_code: int = 400, details: object | None = None):
        super().__init__(message)
        self.code = code
        self.message = message
        self.status_code = status_code
        self.details = details


def _error_payload(code: str, message: str, details: object | None = None) -> dict:
    return {"error": {"code": code, "message": message, "details": details or {}}}


def register_error_handlers(app: FastAPI) -> None:
    @app.exception_handler(AppError)
    async def app_error_handler(request: object, exc: AppError) -> JSONResponse:
        return JSONResponse(
            status_code=exc.status_code,
            content=_error_payload(exc.code, exc.message, exc.details),
        )

    @app.exception_handler(StarletteHTTPException)
    async def http_error_handler(request: object, exc: StarletteHTTPException) -> JSONResponse:
        return JSONResponse(
            status_code=exc.status_code,
            content=_error_payload(f"http_{exc.status_code}", str(exc.detail)),
        )

    @app.exception_handler(RequestValidationError)
    async def validation_error_handler(request: object, exc: RequestValidationError) -> JSONResponse:
        return JSONResponse(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            content=_error_payload("validation_error", "请求参数校验失败", {"errors": exc.errors()}),
        )

    @app.exception_handler(Exception)
    async def unhandled_error_handler(request: object, exc: Exception) -> JSONResponse:
        logger.exception("未处理异常")
        return JSONResponse(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            content=_error_payload("internal_error", "服务内部错误"),
        )
