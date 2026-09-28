"""Схемы лицензий. Лицензия оформляется на продукт взаимодействия по его договору."""

import uuid
from datetime import date

from pydantic import BaseModel, Field, model_validator

from app.enums import LicenseStatus
from app.schemas.common import ORMModel
from app.schemas.university import UniversityBrief


def _check_period(valid_from: date | None, valid_to: date | None) -> None:
    if valid_from and valid_to and valid_from > valid_to:
        raise ValueError("Срок лицензии начинается позже, чем заканчивается")


class LicenseCreate(BaseModel):
    number: str | None = Field(default=None, max_length=100)
    seats: int | None = Field(default=None, ge=0)
    signed_at: date | None = None
    valid_from: date | None = None
    valid_to: date | None = None
    status: LicenseStatus = LicenseStatus.ACTIVE

    @model_validator(mode="after")
    def _dates(self) -> "LicenseCreate":
        _check_period(self.valid_from, self.valid_to)
        return self


class LicenseUpdate(BaseModel):
    number: str | None = Field(default=None, max_length=100)
    seats: int | None = Field(default=None, ge=0)
    signed_at: date | None = None
    valid_from: date | None = None
    valid_to: date | None = None
    status: LicenseStatus | None = None


class LicenseRead(ORMModel):
    id: uuid.UUID
    contract_id: uuid.UUID
    interaction_product_id: uuid.UUID
    number: str | None
    seats: int | None
    signed_at: date | None
    valid_from: date | None
    valid_to: date | None
    status: LicenseStatus


class LicenseListItem(LicenseRead):
    """Лицензия вместе с контекстом: чьё взаимодействие и какой продукт."""

    interaction_id: uuid.UUID
    contract_number: str
    university: UniversityBrief
    product_id: uuid.UUID
    product_name: str
    days_left: int | None = None
