"""Схемы лицензий.

Лицензия относится к конкретному продукту в конкретном договоре
(раздел 9.2 концепции), поэтому создаётся внутри строки состава договора.
"""

import uuid
from datetime import date

from pydantic import BaseModel, Field

from app.enums import LicenseStatus
from app.schemas.common import ORMModel


class LicenseCreate(BaseModel):
    number: str | None = Field(default=None, max_length=100)
    seats: int | None = Field(default=None, ge=0)
    signed_at: date | None = None
    valid_from: date | None = None
    valid_to: date | None = None
    status: LicenseStatus = LicenseStatus.ACTIVE


class LicenseUpdate(BaseModel):
    number: str | None = Field(default=None, max_length=100)
    seats: int | None = Field(default=None, ge=0)
    signed_at: date | None = None
    valid_from: date | None = None
    valid_to: date | None = None
    status: LicenseStatus | None = None


class LicenseRead(ORMModel):
    id: uuid.UUID
    contract_product_id: uuid.UUID
    number: str | None
    seats: int | None
    signed_at: date | None
    valid_from: date | None
    valid_to: date | None
    status: LicenseStatus


class LicenseListItem(LicenseRead):
    """Лицензия вместе с контекстом: чей договор и какой продукт."""

    contract_id: uuid.UUID
    contract_number: str
    university_id: uuid.UUID
    university_name: str
    product_id: uuid.UUID
    product_name: str
    days_left: int | None = None
