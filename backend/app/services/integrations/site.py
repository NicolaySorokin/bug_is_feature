"""Адаптер сайта ИТ Школы (CMS Laravel).

С сайта приходят вузы-партнёры с контактными лицами и заявки на обучение.
Заявка - повод завести договор и запустить по нему рабочий процесс
(функциональное требование 5 ТЗ: данные из внешней системы добавляются
в существующий или новый workflow).
"""

from __future__ import annotations

from typing import Any

from app.core.config import settings
from app.services.integrations.base import (
    ExternalRequest,
    ExternalUniversity,
    IntegrationPayload,
    contacts_from,
    fetch_json,
    load_fixture,
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
        if self.uses_fixture:
            raw = load_fixture("site")
        else:
            raw = await fetch_json(f"{self.base_url}/api/partners", self._token)
        return self.parse(raw)

    @staticmethod
    def parse(raw: dict[str, Any]) -> IntegrationPayload:
        universities = [
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
        requests = [
            ExternalRequest(
                external_id=str(item["id"]),
                university_external_id=str(item["university_id"]),
                program_external_ids=[str(value) for value in item.get("program_ids", [])],
                comment=item.get("comment"),
            )
            for item in raw.get("requests", [])
            if item.get("id") and item.get("university_id")
        ]
        return IntegrationPayload(universities=universities, requests=requests)
