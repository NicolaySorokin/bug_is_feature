"""Коды ошибок и единый формат ответа при сбое.

Нефункциональное требование 3 ТЗ: «должны быть предусмотрены коды ошибок».
Поэтому любой отказ API возвращает одно и то же тело::

    {"code": "workflow_rule_violated", "message": "...", "details": {...}}

``code`` машиночитаем и не меняется при правке текста сообщения - на него
опирается клиент, ``message`` предназначен человеку.
"""

from __future__ import annotations

import logging
from enum import StrEnum
from typing import Any

from fastapi import FastAPI, HTTPException, Request, status
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from pydantic import BaseModel
from sqlalchemy.exc import IntegrityError

logger = logging.getLogger("app.errors")


class ErrorCode(StrEnum):
    UNAUTHORIZED = "unauthorized"
    FORBIDDEN = "forbidden"
    ACCOUNT_DISABLED = "account_disabled"
    NOT_FOUND = "not_found"
    VALIDATION_ERROR = "validation_error"
    CONFLICT = "conflict"
    WORKFLOW_RULE_VIOLATED = "workflow_rule_violated"
    FILE_TYPE_NOT_ALLOWED = "file_type_not_allowed"
    FILE_TOO_LARGE = "file_too_large"
    IMPORT_FAILED = "import_failed"
    INTEGRATION_FAILED = "integration_failed"
    REPORT_FAILED = "report_failed"
    IDENTITY_PROVIDER_ERROR = "identity_provider_error"
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


VALIDATION_MESSAGE = "Запрос не прошёл проверку"
# Так Pydantic начинает текст ошибки, которую бросила наша проверка (ValueError).
_VALUE_ERROR_PREFIX = "Value error, "


def validation_message(errors: list[dict[str, Any]]) -> str:
    """Текст для человека: нарушенные правила предметной области как есть.

    Проверки схем («подписанный договор не отменяют», «период начинается
    позже окончания») пишут понятный текст - его и показываем, а не общее
    «запрос не прошёл проверку». Технические ошибки формата (нет поля,
    не тот тип) остаются в details.errors.
    """
    rules = [
        str(error.get("msg", "")).removeprefix(_VALUE_ERROR_PREFIX).strip()
        for error in errors
        if error.get("type") == "value_error"
    ]
    rules = [rule for rule in dict.fromkeys(rules) if rule]
    return "; ".join(rules) if rules else VALIDATION_MESSAGE


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

    @app.exception_handler(IntegrityError)
    async def _integrity_error(_: Request, exc: IntegrityError) -> JSONResponse:
        # Нарушение ограничений базы - дубль или ссылка на удалённую запись.
        # Это ошибка запроса, а не сбой сервиса: отвечаем 409, а не 500.
        logger.info("Нарушение ограничения базы: %s", exc.orig)
        return JSONResponse(
            status_code=status.HTTP_409_CONFLICT,
            content=error_payload(
                ErrorCode.CONFLICT,
                "Изменение противоречит данным: такая запись уже есть "
                "или на неё ссылаются другие записи",
            ),
        )

    @app.exception_handler(Exception)
    async def _unexpected_error(request: Request, exc: Exception) -> JSONResponse:
        # Непредвиденный сбой: подробности - в журнал сервера, клиенту -
        # общий код без внутренностей (стек и SQL наружу не уходят).
        logger.exception("Необработанная ошибка: %s %s", request.method, request.url.path)
        return JSONResponse(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            content=error_payload(
                ErrorCode.INTERNAL_ERROR,
                "Внутренняя ошибка сервиса. Повторите действие или обратитесь "
                "к администратору",
            ),
        )

    @app.exception_handler(RequestValidationError)
    async def _validation_error(_: Request, exc: RequestValidationError) -> JSONResponse:
        errors = list(exc.errors())
        return JSONResponse(
            status_code=422,
            content=error_payload(
                ErrorCode.VALIDATION_ERROR,
                validation_message(errors),
                # jsonable: в ошибках Pydantic встречаются несериализуемые объекты.
                {
                    "errors": [
                        {
                            "loc": [str(part) for part in error.get("loc", ())],
                            "msg": str(error.get("msg", "")),
                            "type": error.get("type", ""),
                        }
                        for error in errors
                    ]
                },
            ),
        )
