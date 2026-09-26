"""Схемы вузов и контактных лиц.

Краткое название - основное в компактных местах (списки, выпадающие
списки, уведомления, результаты поиска); полное - в карточке вуза.
Поэтому любая модель ответа с вузом отдаёт оба названия и готовое
``display_name`` - клиент не сокращает названия сам.
"""

import uuid
from datetime import datetime

from pydantic import BaseModel, Field, field_validator

from app.enums import UniversityStatus
from app.schemas.common import ORMModel
from app.schemas.user import UserBrief


def _clean_inn(value: str | None) -> str | None:
    if value is None:
        return None
    digits = "".join(char for char in value if char.isdigit())
    if not digits:
        return None
    if len(digits) not in (10, 12):
        raise ValueError("ИНН - 10 цифр у организации (12 - у ИП)")
    return digits


class UniversityBrief(ORMModel):
    """Вуз в компактном виде: для списков, строк реестров и уведомлений."""

    id: uuid.UUID
    name: str
    short_name: str | None = None
    display_name: str = ""

    @classmethod
    def of(cls, university) -> "UniversityBrief | None":  # noqa: ANN001 - модель
        if university is None:
            return None
        return cls(
            id=university.id,
            name=university.name,
            short_name=university.short_name,
            display_name=university.short_name or university.name,
        )


class UniversityContactCreate(BaseModel):
    full_name: str = Field(min_length=1, max_length=255)
    position: str | None = Field(default=None, max_length=255)
    email: str | None = Field(default=None, max_length=255)
    phone: str | None = Field(default=None, max_length=50)


class UniversityContactUpdate(BaseModel):
    full_name: str | None = Field(default=None, min_length=1, max_length=255)
    position: str | None = Field(default=None, max_length=255)
    email: str | None = Field(default=None, max_length=255)
    phone: str | None = Field(default=None, max_length=50)
    is_active: bool | None = None


class UniversityContactRead(ORMModel):
    id: uuid.UUID
    university_id: uuid.UUID
    full_name: str
    position: str | None
    email: str | None
    phone: str | None
    is_active: bool


class UniversityCreate(BaseModel):
    name: str = Field(min_length=1, max_length=500)
    short_name: str | None = Field(default=None, max_length=100)
    inn: str | None = Field(default=None, max_length=20)
    city: str | None = Field(default=None, max_length=255)
    website: str | None = Field(default=None, max_length=500)
    description: str | None = None
    manager_id: uuid.UUID | None = None

    _inn = field_validator("inn")(_clean_inn)


class UniversityUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=500)
    short_name: str | None = Field(default=None, max_length=100)
    inn: str | None = Field(default=None, max_length=20)
    city: str | None = Field(default=None, max_length=255)
    website: str | None = Field(default=None, max_length=500)
    description: str | None = None
    manager_id: uuid.UUID | None = None

    _inn = field_validator("inn")(_clean_inn)


class UniversityMerge(BaseModel):
    """Объединение дублей: эта запись поглощается итоговой."""

    target_id: uuid.UUID


class UniversityRead(ORMModel):
    id: uuid.UUID
    name: str
    short_name: str | None
    display_name: str = ""
    inn: str | None = None
    city: str | None
    website: str | None
    description: str | None
    # Менеджер по умолчанию: его назначают ответственным за новые
    # взаимодействия вуза.
    manager_id: uuid.UUID | None
    status: UniversityStatus
    origin: str = "manual"
    merged_into_id: uuid.UUID | None = None
    is_active: bool = True


class UniversityListItem(UniversityRead):
    manager: UserBrief | None = None
    interactions_count: int = 0
    active_interactions_count: int = 0
    # Видит ли сотрудник бизнес-данные вуза (контакты, взаимодействия).
    in_scope: bool = True


class UniversityDetail(UniversityListItem):
    contacts: list[UniversityContactRead] = []
    created_at: datetime | None = None
    confirmed_at: datetime | None = None


class DuplicateCandidate(BaseModel):
    """Похоже, что два вуза - одна организация."""

    first: UniversityBrief
    second: UniversityBrief
    reason: str
