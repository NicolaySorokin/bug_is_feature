"""Адаптер сайта ИТ Школы (CMS Laravel).

Сайт отдаёт заявки студентов на обучение: они идут только в статистику.
Пустые элементы пропускаются. Заявка вуза на сотрудничество приходит
отдельным объектом и попадает во взаимодействие с этим вузом.
"""

from __future__ import annotations

from typing import Any

from app.core.config import settings
from app.services.integrations.base import (
    ExternalApplication,
    ExternalRequest,
    ExternalUniversity,
    IntegrationPayload,
    contacts_from,
    fetch_json,
    load_fixture,
    normalize_email,
    normalize_phone,
    parse_datetime,
    parse_int,
    pick,
    text,
)


def parse_application(item: dict[str, Any]) -> ExternalApplication | None:
    number = text(pick(item, "Номер заявки", "id", "number"))
    course = text(pick(item, "Курс", "course", "program"))
    if not number or not course:
        return None
    return ExternalApplication(
        external_id=number,
        course_name=course,
        stream_number=parse_int(pick(item, "Номер потока", "stream")),
        last_name=text(pick(item, "Фамилия", "last_name")) or "",
        first_name=text(pick(item, "Имя", "first_name")) or "",
        middle_name=text(pick(item, "Отчество", "Отчество (при наличии)", "middle_name")),
        phone=normalize_phone(pick(item, "Телефон", "Номер телефона", "phone")),
        email=normalize_email(pick(item, "Email", "Почта", "email")),
        university_name=text(pick(item, "Вуз", "Учебное заведение", "university")),
        submitted_at=parse_datetime(pick(item, "Дата заявки", "Дата", "created_at")),
        stream_id=text(pick(item, "ID потока", "Идентификатор потока", "stream_id")),
    )


class SiteAdapter:
    code = "site"
    name = "Сайт ИТ Школы Ростелекома"

    def __init__(self) -> None:
        self.base_url = settings.site_base_url.rstrip("/")
        self._token = settings.site_token

    @property
    def uses_fixture(self) -> bool:
        return not self.base_url

    async def fetch(self) -> IntegrationPayload:
        attempts = 1
        if self.uses_fixture:
            # Заглушка внешнего API: без SITE_BASE_URL
            # берём тестовый ответ из fixtures/site.json.
            raw = load_fixture("site")
        else:
            raw, attempts = await fetch_json(f"{self.base_url}/api/applications", self._token)
        payload = self.parse(raw)
        payload.attempts = attempts
        return payload

    @staticmethod
    def parse(raw: Any) -> IntegrationPayload:
        payload = IntegrationPayload()
        if isinstance(raw, dict):
            items = raw.get("applications") or []
            payload.universities = [
                ExternalUniversity(
                    external_id=str(item["id"]),
                    name=item["name"],
                    short_name=item.get("short_name"),
                    city=item.get("city"),
                    website=item.get("website"),
                    contacts=contacts_from(item.get("contacts")),
                )
                for item in raw.get("universities", [])
                if item.get("id") and item.get("name")
            ]
            payload.requests = [
                ExternalRequest(
                    external_id=str(item["id"]),
                    university_external_id=str(item["university_id"]),
                    program_external_ids=[str(value) for value in item.get("program_ids", [])],
                    comment=item.get("comment"),
                )
                for item in raw.get("requests", [])
                if item.get("id") and item.get("university_id")
            ]
        elif isinstance(raw, list):
            items = raw
        else:
            items = []

        for item in items:
            application = parse_application(item) if isinstance(item, dict) else None
            if application is None:
                payload.skipped += 1
            else:
                payload.applications.append(application)
        return payload
