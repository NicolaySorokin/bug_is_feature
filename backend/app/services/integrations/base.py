"""Общий контракт адаптеров LMS и сайта и заглушки их API.

Контрактов API LMS и сайта организаторы не дали. Поэтому, пока не задан
LMS_BASE_URL или SITE_BASE_URL, адаптер вместо запроса берёт тестовый ответ
из fixtures в формате данных кейсодержателя. Всё остальное (разбор, запись,
журнал, повторы) работает как с настоящим API, для подключения достаточно
задать адрес и токен.
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
    # Необязательные поля. Вуз заявителя нужен только для статистики.
    university_name: str | None = None
    submitted_at: datetime | None = None
    # Стабильный идентификатор потока, если источник его передаёт.
    stream_id: str | None = None


@dataclass(slots=True)
class ExternalLearner:
    """Обучающийся из LMS, уже без лишних персональных данных."""

    last_name: str
    first_name: str
    middle_name: str | None = None
    phone: str | None = None
    email: str | None = None
    gender: str | None = None
    education: str | None = None
    region: str | None = None
    # Если LMS передаёт программу и поток, зачисление берётся отсюда,
    # а не угадывается по контактам заявки.
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
    """Тестовый ответ источника, заглушка его API."""
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

# Текст для сотрудника при сбое внешней системы: без кодов ответа и адресов,
# только что случилось и что делать. Причина пишется в журнал сервера.
UNAVAILABLE_MESSAGE = (
    "Внешняя система сейчас недоступна. Повторите обмен позже, "
    "а если ошибка повторится - обратитесь к разработчику."
)


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

    Сбой сети, тайм-аут и 5xx повторяются, 4xx нет: повтор её не исправит.
    """
    headers = {"Accept": "application/json"}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    reason = "нет связи"
    cause: Exception | None = None
    for attempt in range(1, FETCH_ATTEMPTS + 1):
        try:
            return await _fetch_once(url, headers), attempt
        except httpx.HTTPStatusError as exc:
            reason = f"ответ {exc.response.status_code}"
            cause = exc
            break
        except _Retryable as exc:
            reason = f"ответ {exc.args[0]}"
            cause = exc
        except httpx.TimeoutException as exc:
            reason = f"нет ответа за {settings.integration_timeout_seconds:g} с"
            cause = exc
        except httpx.HTTPError as exc:
            reason = "нет связи"
            cause = exc
        except ValueError as exc:
            reason = "ответ не в формате JSON"
            cause = exc
            break
        if attempt < FETCH_ATTEMPTS:
            await asyncio.sleep(
                FETCH_BACKOFF_SECONDS[min(attempt - 1, len(FETCH_BACKOFF_SECONDS) - 1)]
            )
    logger.warning("Обмен с %s не удался: %s, попыток %d (%r)", url, reason, attempt, cause)
    raise AppError(
        UNAVAILABLE_MESSAGE,
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


# Нормализация значений


def key(name: object) -> str:
    """Имя поля без регистра, пробелов и знаков, чтобы испорченные при выгрузке
    заголовки тоже находились.
    """
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
    """Телефон цифрами в виде 7XXXXXXXXXX."""
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

    Если номер испорчен (месяц 17, секунда 69), берём момент получения заявки.
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
