"""Адаптер LMS ИТ Школы.

Из LMS берём две вещи:

* учебную часть - ИТ-программы с направлениями и ИТ-продукты (прежний
  формат: объект с programs и products);
* обучающихся - анкеты слушателей. Состав полей анкеты передан
  кейсодержателем (фамилия, имя, отчество, телефон, почта, СНИЛС, паспорт,
  адрес, образование, диплом...). Анкета приходит списком объектов
  или в ключе learners.

Из анкеты сохраняется только то, что нужно для статистики обучения
и сопоставления с заявкой: ФИО, телефон, почта, пол, уровень образования
и регион. СНИЛС, паспорт, адрес, дата рождения и сведения о дипломе
отбрасываются здесь же и в базу не попадают - это требование минимизации
персональных данных (ст. 5 152-ФЗ): обработка не должна быть избыточной
по отношению к её целям. Какие поля отброшены, пишется в журнал запуска.
"""

from __future__ import annotations

from typing import Any

from app.core.config import settings
from app.services.integrations.base import (
    ExternalLearner,
    ExternalProduct,
    ExternalProgram,
    IntegrationPayload,
    fetch_json,
    key,
    load_fixture,
    normalize_email,
    normalize_phone,
    pick,
    text,
)

# Поля анкеты, которые система использует. Остальное не сохраняется.
LEARNER_FIELDS: dict[str, tuple[str, ...]] = {
    "last_name": ("Фамилия", "last_name"),
    "first_name": ("Имя", "first_name"),
    "middle_name": ("Отчество (при наличии)", "Отчество", "middle_name"),
    "phone": ("Номер телефона", "Телефон", "phone"),
    "email": ("Email", "Почта", "email"),
    "gender": ("Пол", "gender"),
    "education": ("Образование", "education"),
    "region": ("Регион регистрации", "Регион", "region"),
}
_USED_KEYS = {key(name) for names in LEARNER_FIELDS.values() for name in names}


def _gender(value: Any) -> str | None:
    raw = (text(value) or "").upper()[:1]
    return {"М": "М", "M": "М", "Ж": "Ж", "F": "Ж", "W": "Ж"}.get(raw)


def parse_learner(item: dict[str, Any], dropped: set[str]) -> ExternalLearner | None:
    dropped.update(
        str(name) for name, value in item.items() if key(name) not in _USED_KEYS and value
    )
    last_name = text(pick(item, *LEARNER_FIELDS["last_name"]))
    first_name = text(pick(item, *LEARNER_FIELDS["first_name"]))
    email = normalize_email(pick(item, *LEARNER_FIELDS["email"]))
    phone = normalize_phone(pick(item, *LEARNER_FIELDS["phone"]))
    if not last_name or not first_name or not (email or phone):
        return None
    return ExternalLearner(
        last_name=last_name,
        first_name=first_name,
        middle_name=text(pick(item, *LEARNER_FIELDS["middle_name"])),
        phone=phone,
        email=email,
        gender=_gender(pick(item, *LEARNER_FIELDS["gender"])),
        education=text(pick(item, *LEARNER_FIELDS["education"])),
        region=text(pick(item, *LEARNER_FIELDS["region"])),
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
    def parse(raw: Any) -> IntegrationPayload:
        payload = IntegrationPayload()
        if isinstance(raw, dict):
            learners = raw.get("learners") or []
            payload.programs = [
                ExternalProgram(
                    external_id=str(item["id"]),
                    name=item["name"],
                    direction_name=item.get("direction"),
                    description=item.get("description"),
                )
                for item in raw.get("programs", [])
                if item.get("id") and item.get("name")
            ]
            payload.products = [
                ExternalProduct(
                    external_id=str(item["id"]),
                    name=item["name"],
                    vendor_name=item.get("vendor"),
                    description=item.get("description"),
                )
                for item in raw.get("products", [])
                if item.get("id") and item.get("name")
            ]
        elif isinstance(raw, list):
            learners = raw
        else:
            learners = []

        for item in learners:
            learner = (
                parse_learner(item, payload.dropped_fields) if isinstance(item, dict) else None
            )
            if learner is None:
                payload.skipped += 1
            else:
                payload.learners.append(learner)
        return payload
