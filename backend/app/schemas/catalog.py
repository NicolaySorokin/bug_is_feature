"""Схемы справочников: направления, программы, вендоры, продукты."""

import uuid

from pydantic import BaseModel, Field

from app.schemas.common import ORMModel


class NamedCreate(BaseModel):
    name: str = Field(min_length=1, max_length=500)
    description: str | None = None


class ItDirectionRead(ORMModel):
    id: uuid.UUID
    name: str
    description: str | None
    is_active: bool


class VendorRead(ItDirectionRead):
    pass


class ItProgramCreate(NamedCreate):
    direction_id: uuid.UUID | None = None


class ItProgramRead(ORMModel):
    id: uuid.UUID
    direction_id: uuid.UUID | None
    name: str
    description: str | None
    is_active: bool


class ItProductCreate(NamedCreate):
    vendor_id: uuid.UUID | None = None


class ItProductRead(ORMModel):
    id: uuid.UUID
    vendor_id: uuid.UUID | None
    name: str
    description: str | None
    is_active: bool
