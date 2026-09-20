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

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Protocol

import httpx

from app.core.config import settings
from app.core.errors import AppError, ErrorCode

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
    """Заявка на обучение: повод завести договор и запустить процесс."""

    external_id: str
    university_external_id: str
    program_external_ids: list[str] = field(default_factory=list)
    comment: str | None = None


@dataclass(slots=True)
class IntegrationPayload:
    universities: list[ExternalUniversity] = field(default_factory=list)
    programs: list[ExternalProgram] = field(default_factory=list)
    products: list[ExternalProduct] = field(default_factory=list)
    requests: list[ExternalRequest] = field(default_factory=list)

    @property
    def size(self) -> int:
        return (
            len(self.universities)
            + len(self.programs)
            + len(self.products)
            + len(self.requests)
        )


class SourceAdapter(Protocol):
    """Контракт, который реализует адаптер любой внешней системы."""

    code: str
    name: str
    base_url: str

    async def fetch(self) -> IntegrationPayload: ...


def load_fixture(name: str) -> dict[str, Any]:
    path = FIXTURES / f"{name}.json"
    if not path.is_file():
        raise AppError(
            f"Нет тестовых данных для источника «{name}»",
            code=ErrorCode.INTEGRATION_FAILED,
        )
    return json.loads(path.read_text(encoding="utf-8"))


async def fetch_json(url: str, token: str) -> dict[str, Any]:
    """Запрос к внешнему API. Ошибки сети превращаются в понятный код."""
    headers = {"Accept": "application/json"}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    try:
        async with httpx.AsyncClient(timeout=settings.integration_timeout_seconds) as client:
            response = await client.get(url, headers=headers)
            response.raise_for_status()
            return response.json()
    except httpx.HTTPError as exc:
        raise AppError(
            f"Внешняя система не ответила: {exc}", code=ErrorCode.INTEGRATION_FAILED
        ) from exc


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
