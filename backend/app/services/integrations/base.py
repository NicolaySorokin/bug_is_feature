"""Общий контракт адаптеров внешних систем.

Раздел 5 концепции: контрактов LMS и сайта у нас пока нет, поэтому между
внешней системой и остальным кодом стоит адаптер. Он приводит любой ответ
к структурам этого модуля. Когда организаторы передадут реальный контракт,
меняется только разбор ответа внутри адаптера - сервис синхронизации,
модель данных и отчёты остаются прежними.

Пока базовый адрес источника не задан, адаптер берёт тестовый ответ из
``fixtures`` - той же формы, что ожидается от настоящего API.
"""

from __future__ import annotations

import asyncio
import json
import logging
import re
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Protocol

import httpx

from app.core.config import settings
from app.core.errors import AppError, ErrorCode

logger = logging.getLogger(__name__)

FIXTURES = Path(__file__).parent / "fixtures"


@dataclass(slots=True)
class ExternalContact:
    full_name: str
    position: str | None = None
    email: str | None = None
    phone: str | None = None


@dataclass(slots=True)
class ExternalUniversity:
    external_id: str
    name: str
    short_name: str | None = None
    city: str | None = None
    website: str | None = None
    contacts: list[ExternalContact] = field(default_factory=list)


@dataclass(slots=True)
class ExternalProgram:
    external_id: str
    name: str
    direction_name: str | None = None
    description: str | None = None


@dataclass(slots=True)
class ExternalProduct:
    external_id: str
    name: str
    vendor_name: str | None = None
    description: str | None = None


@dataclass(slots=True)
class ExternalRequest:
    """Заявка вуза на сотрудничество: повод для взаимодействия с вузом."""

    external_id: str
    university_external_id: str
    program_external_ids: list[str] = field(default_factory=list)
    comment: str | None = None


@dataclass(slots=True)
class ExternalApplication:
    """Заявка на обучение в формате сайта ИТ Школы (передан кейсодержателем)."""

    external_id: str
    course_name: str
    stream_number: int | None = None
    last_name: str = ""
    first_name: str = ""
    middle_name: str | None = None
    phone: str | None = None
    email: str | None = None
    # Необязательные поля. Вуз заявителя - только разрез статистики:
    # заявка студента взаимодействие с вузом не создаёт.
    university_name: str | None = None
    submitted_at: datetime | None = None
    # Стабильный идентификатор потока, если источник его передаёт.
    stream_id: str | None = None


@dataclass(slots=True)
class ExternalLearner:
    """Обучающийся из LMS - уже без лишних персональных данных."""

    last_name: str
    first_name: str
    middle_name: str | None = None
    phone: str | None = None
    email: str | None = None
    gender: str | None = None
    education: str | None = None
    region: str | None = None
    # Если LMS передаёт, на какой программе и в каком потоке человек учится,
    # зачисление берётся отсюда, а не угадывается по контактам заявки.
    external_id: str | None = None
    course_name: str | None = None
    program_external_id: str | None = None
    stream_external_id: str | None = None
    stream_number: int | None = None


@dataclass(slots=True)
class IntegrationPayload:
    universities: list[ExternalUniversity] = field(default_factory=list)
    programs: list[ExternalProgram] = field(default_factory=list)
    products: list[ExternalProduct] = field(default_factory=list)
    requests: list[ExternalRequest] = field(default_factory=list)
    applications: list[ExternalApplication] = field(default_factory=list)
    learners: list[ExternalLearner] = field(default_factory=list)
    # Записи, которые не удалось разобрать (пустые, без обязательных полей).
    skipped: int = 0
    # Поля источника, которые намеренно не сохраняются (минимизация ПДн).
    dropped_fields: set[str] = field(default_factory=set)
    # Сколько попыток обращения к источнику понадобилось.
    attempts: int = 1

    @property
    def size(self) -> int:
        return (
            len(self.universities)
            + len(self.programs)
            + len(self.products)
            + len(self.requests)
            + len(self.applications)
            + len(self.learners)
        )


class SourceAdapter(Protocol):
    """Контракт, который реализует адаптер любой внешней системы."""

    code: str
    name: str
    base_url: str

    async def fetch(self) -> IntegrationPayload: ...


def load_fixture(name: str) -> Any:
    path = FIXTURES / f"{name}.json"
    if not path.is_file():
        raise AppError(
            f"Нет тестовых данных для источника «{name}»",
            code=ErrorCode.INTEGRATION_FAILED,
        )
    return json.loads(path.read_text(encoding="utf-8"))


# Повторы при сбоях сети и ошибках 5xx: сколько попыток и пауза между ними.
FETCH_ATTEMPTS = 3
FETCH_BACKOFF_SECONDS = (1.0, 3.0)


class _Retryable(Exception):
    """Сбой, после которого имеет смысл повторить запрос."""


async def _fetch_once(url: str, headers: dict[str, str]) -> Any:
    async with httpx.AsyncClient(timeout=settings.integration_timeout_seconds) as client:
        response = await client.get(url, headers=headers)
        if response.status_code >= 500:
            raise _Retryable(response.status_code)
        response.raise_for_status()
        return response.json()


async def fetch_json(url: str, token: str) -> tuple[Any, int]:
    """Запрос к внешнему API с повторами. Возвращает ответ и число попыток.

    Сбой сети, тайм-аут и ответ 5xx повторяются (до FETCH_ATTEMPTS раз
    с паузой); ошибка 4xx - сразу: повтор её не исправит. Текст ошибки
    попадает в журнал обмена, который видят сотрудники, поэтому он короткий
    и по-русски, без адресов и внутренностей HTTP-клиента; подробности -
    в журнале сервера.
    """
    headers = {"Accept": "application/json"}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    message = "Не удалось связаться с внешней системой"
    cause: Exception | None = None
    for attempt in range(1, FETCH_ATTEMPTS + 1):
        try:
            return await _fetch_once(url, headers), attempt
        except httpx.HTTPStatusError as exc:
            status = exc.response.status_code
            message = f"Внешняя система ответила ошибкой {status}"
            if status in (401, 403):
                message += ": проверьте токен доступа к API"
            elif status == 404:
                message += ": проверьте адрес API"
            cause = exc
            break
        except _Retryable as exc:
            message = f"Внешняя система ответила ошибкой {exc.args[0]}"
            cause = exc
        except httpx.TimeoutException as exc:
            message = (
                f"Внешняя система не ответила за {settings.integration_timeout_seconds:g} с"
            )
            cause = exc
        except httpx.HTTPError as exc:
            message = "Не удалось связаться с внешней системой: проверьте адрес API и сеть"
            cause = exc
        except ValueError as exc:
            message = "Внешняя система прислала ответ не в формате JSON"
            cause = exc
            break
        if attempt < FETCH_ATTEMPTS:
            await asyncio.sleep(
                FETCH_BACKOFF_SECONDS[min(attempt - 1, len(FETCH_BACKOFF_SECONDS) - 1)]
            )
    logger.warning("Обмен с %s не удался: %r", url, cause)
    raise AppError(
        f"{message} (попыток: {attempt})",
        code=ErrorCode.INTEGRATION_FAILED,
        details={"attempts": attempt},
    ) from cause


def contacts_from(raw: list[dict[str, Any]] | None) -> list[ExternalContact]:
    return [
        ExternalContact(
            full_name=item.get("full_name") or item.get("fio") or "",
            position=item.get("position"),
            email=item.get("email"),
            phone=item.get("phone"),
        )
        for item in raw or []
        if item.get("full_name") or item.get("fio")
    ]


# --- Нормализация значений ------------------------------------------------------


def key(name: object) -> str:
    """Имя поля без регистра, пробелов и знаков: «Отчество (при наличии)» и
    испорченное при выгрузке «Отчествопри наличии)» дают одно и то же."""
    return re.sub(r"[^0-9a-zа-яё]+", "", str(name).lower())


def pick(item: dict[str, Any], *names: str) -> Any:
    """Значение поля по любому из допустимых имён."""
    wanted = {key(name) for name in names}
    for field_name, value in item.items():
        if key(field_name) in wanted and value not in (None, ""):
            return value
    return None


def text(value: Any) -> str | None:
    if value is None:
        return None
    if isinstance(value, float) and value.is_integer():
        value = int(value)
    result = str(value).strip()
    return result or None


def normalize_phone(value: Any) -> str | None:
    """Телефон цифрами в виде 7XXXXXXXXXX: «7 (999) 023-43-65» и 79990234365 совпадут."""
    digits = re.sub(r"\D", "", text(value) or "")
    if not digits:
        return None
    if len(digits) == 10:
        digits = "7" + digits
    elif len(digits) == 11 and digits.startswith("8"):
        digits = "7" + digits[1:]
    return digits[:20]


def normalize_email(value: Any) -> str | None:
    email = (text(value) or "").lower()
    return email if "@" in email else None


def parse_int(value: Any) -> int | None:
    try:
        return int(float(str(value).strip()))
    except (TypeError, ValueError):
        return None


_ORDER_STAMP = re.compile(r"(\d{14})")


def date_from_number(number: str) -> datetime | None:
    """Номер заявки сайта содержит момент подачи: ORD-20260522061330-...

    В тестовой выгрузке встречаются и испорченные номера (месяц 17,
    секунда 69) - тогда даты нет, и берётся момент получения заявки.
    """
    match = _ORDER_STAMP.search(number or "")
    if match is None:
        return None
    try:
        return datetime.strptime(match.group(1), "%Y%m%d%H%M%S").replace(tzinfo=UTC)
    except ValueError:
        return None


def parse_datetime(value: Any) -> datetime | None:
    raw = text(value)
    if raw is None:
        return None
    for pattern in ("%Y-%m-%dT%H:%M:%S%z", "%Y-%m-%dT%H:%M:%S", "%Y-%m-%d", "%d.%m.%Y"):
        try:
            parsed = datetime.strptime(raw, pattern)
        except ValueError:
            continue
        return parsed if parsed.tzinfo else parsed.replace(tzinfo=UTC)
    return None
