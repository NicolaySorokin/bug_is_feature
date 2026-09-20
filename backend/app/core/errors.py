"""Коды ошибок и единый формат ответа при сбое.

Нефункциональное требование 3 ТЗ: «должны быть предусмотрены коды ошибок».
Поэтому любой отказ API возвращает одно и то же тело::

    {"code": "workflow_rule_violated", "message": "...", "details": {...}}

``code`` машиночитаем и не меняется при правке текста сообщения - на него
опирается клиент, ``message`` предназначен человеку.
"""

from __future__ import annotations

from enum import StrEnum
from typing import Any

from fastapi import FastAPI, HTTPException, Request, status
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from pydantic import BaseModel


class ErrorCode(StrEnum):
    UNAUTHORIZED = "unauthorized"
    FORBIDDEN = "forbidden"
    NOT_FOUND = "not_found"
    VALIDATION_ERROR = "validation_error"
    CONFLICT = "conflict"
    WORKFLOW_RULE_VIOLATED = "workflow_rule_violated"
    FILE_TYPE_NOT_ALLOWED = "file_type_not_allowed"
    FILE_TOO_LARGE = "file_too_large"
    IMPORT_FAILED = "import_failed"
    INTEGRATION_FAILED = "integration_failed"
    REPORT_FAILED = "report_failed"
    INTERNAL_ERROR = "internal_error"


class ErrorResponse(BaseModel):
    """Тело ответа при любой ошибке. Используется в схеме OpenAPI."""

    code: ErrorCode
    message: str
    details: dict[str, Any] | None = None


class AppError(Exception):
    """Ошибка предметной области, которую API отдаёт клиенту как есть."""

    status_code: int = status.HTTP_400_BAD_REQUEST
    code: ErrorCode = ErrorCode.VALIDATION_ERROR

    def __init__(
        self,
        message: str,
        *,
        code: ErrorCode | None = None,
        status_code: int | None = None,
        details: dict[str, Any] | None = None,
    ) -> None:
        super().__init__(message)
        self.message = message
        self.details = details
        if code is not None:
            self.code = code
        if status_code is not None:
            self.status_code = status_code


class NotFoundError(AppError):
    status_code = status.HTTP_404_NOT_FOUND
    code = ErrorCode.NOT_FOUND


class ConflictError(AppError):
    status_code = status.HTTP_409_CONFLICT
    code = ErrorCode.CONFLICT


class ForbiddenError(AppError):
    status_code = status.HTTP_403_FORBIDDEN
    code = ErrorCode.FORBIDDEN


# HTTPException не знает про коды, поэтому сопоставляем их по статусу.
_STATUS_TO_CODE = {
    status.HTTP_400_BAD_REQUEST: ErrorCode.VALIDATION_ERROR,
    status.HTTP_401_UNAUTHORIZED: ErrorCode.UNAUTHORIZED,
    status.HTTP_403_FORBIDDEN: ErrorCode.FORBIDDEN,
    status.HTTP_404_NOT_FOUND: ErrorCode.NOT_FOUND,
    status.HTTP_409_CONFLICT: ErrorCode.CONFLICT,
    # Числами, а не константами starlette: их имена в последних версиях
    # переименованы, и предупреждения об устаревании шумят в логах.
    413: ErrorCode.FILE_TOO_LARGE,
    415: ErrorCode.FILE_TYPE_NOT_ALLOWED,
    422: ErrorCode.VALIDATION_ERROR,
}


def error_payload(
    code: ErrorCode, message: str, details: dict[str, Any] | None = None
) -> dict[str, Any]:
    return {"code": code.value, "message": message, "details": details}


def register_error_handlers(app: FastAPI) -> None:
    """Приводит все ошибки приложения к общему формату."""

    @app.exception_handler(AppError)
    async def _app_error(_: Request, exc: AppError) -> JSONResponse:
        return JSONResponse(
            status_code=exc.status_code,
            content=error_payload(exc.code, exc.message, exc.details),
        )

    @app.exception_handler(HTTPException)
    async def _http_error(_: Request, exc: HTTPException) -> JSONResponse:
        code = _STATUS_TO_CODE.get(exc.status_code, ErrorCode.INTERNAL_ERROR)
        return JSONResponse(
            status_code=exc.status_code,
            content=error_payload(code, str(exc.detail)),
            headers=exc.headers,
        )

    @app.exception_handler(RequestValidationError)
    async def _validation_error(_: Request, exc: RequestValidationError) -> JSONResponse:
        return JSONResponse(
            status_code=422,
            content=error_payload(
                ErrorCode.VALIDATION_ERROR,
                "Запрос не прошёл проверку",
                # jsonable: в ошибках Pydantic встречаются несериализуемые объекты.
                {"errors": [
                    {
                        "loc": [str(part) for part in error.get("loc", ())],
                        "msg": error.get("msg", ""),
                        "type": error.get("type", ""),
                    }
                    for error in exc.errors()
                ]},
            ),
        )
