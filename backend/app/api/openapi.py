"""Общее описание ответов с ошибками для схемы OpenAPI.

Тела успешных ответов FastAPI выводит из моделей pydantic сам, а вот про
ошибки он знает только то, что мы ему расскажем. Поэтому описание отказов
собрано здесь один раз и подключается ко всем маршрутам сразу
(``app/api/v1/router.py``): клиент видит в Swagger и формат тела, и список
кодов, с которыми ему придётся иметь дело.

Тот же набор кодов приезжает в ``GET /api/v1/meta/enums`` - фронтенду
не нужно держать его у себя.
"""

from typing import Any

from app.core.errors import ErrorCode, ErrorResponse


def _response(code: ErrorCode, description: str, message: str) -> dict[str, Any]:
    return {
        "model": ErrorResponse,
        "description": description,
        "content": {
            "application/json": {
                "example": {"code": code.value, "message": message, "details": None}
            }
        },
    }


# Эти отказы возможны почти в любом методе, поэтому описываются разом.
# Точечные коды - например, file_type_not_allowed при загрузке файла -
# указаны в описании соответствующих методов.
COMMON_ERRORS: dict[int | str, dict[str, Any]] = {
    401: _response(
        ErrorCode.UNAUTHORIZED,
        "Не пройдена авторизация",
        "Требуется Bearer-токен",
    ),
    403: _response(
        ErrorCode.FORBIDDEN,
        "Недостаточно прав или запись вне области данных сотрудника",
        "Взаимодействие не входит в вашу область данных",
    ),
    404: _response(
        ErrorCode.NOT_FOUND,
        "Запись не найдена",
        "Взаимодействие не найдено",
    ),
    409: _response(
        ErrorCode.WORKFLOW_RULE_VIOLATED,
        "Действие противоречит правилам предметной области",
        "Такой переход не предусмотрен шаблоном процесса",
    ),
    422: _response(
        ErrorCode.VALIDATION_ERROR,
        "Запрос не прошёл проверку: текст правила, если его нарушили, - в message, "
        "все замечания по полям - в details.errors",
        "Для закрытого договора укажите причину: исполнен, истёк или расторгнут",
    ),
}
