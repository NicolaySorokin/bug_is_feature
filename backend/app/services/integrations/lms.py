"""Адаптер LMS ИТ Школы.

Из LMS берём учебную часть: ИТ-программы с направлениями и ИТ-продукты,
на которых идёт обучение. Разбор ответа собран в одном методе - именно
он и переписывается, когда появится настоящий контракт API.
"""

from __future__ import annotations

from typing import Any

from app.core.config import settings
from app.services.integrations.base import (
    ExternalProduct,
    ExternalProgram,
    IntegrationPayload,
    fetch_json,
    load_fixture,
)


class LmsAdapter:
    code = "lms"
    name = "LMS ИТ Школы Ростелекома"

    def __init__(self) -> None:
        self.base_url = settings.lms_base_url.rstrip("/")
        self._token = settings.lms_token

    @property
    def uses_fixture(self) -> bool:
        return not self.base_url

    async def fetch(self) -> IntegrationPayload:
        if self.uses_fixture:
            raw = load_fixture("lms")
        else:
            raw = await fetch_json(f"{self.base_url}/api/v1/programs", self._token)
        return self.parse(raw)

    @staticmethod
    def parse(raw: dict[str, Any]) -> IntegrationPayload:
        programs = [
            ExternalProgram(
                external_id=str(item["id"]),
                name=item["name"],
                direction_name=item.get("direction"),
                description=item.get("description"),
            )
            for item in raw.get("programs", [])
            if item.get("id") and item.get("name")
        ]
        products = [
            ExternalProduct(
                external_id=str(item["id"]),
                name=item["name"],
                vendor_name=item.get("vendor"),
                description=item.get("description"),
            )
            for item in raw.get("products", [])
            if item.get("id") and item.get("name")
        ]
        return IntegrationPayload(programs=programs, products=products)
