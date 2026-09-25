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


class VendorContactRead(ORMModel):
    id: uuid.UUID
    vendor_id: uuid.UUID
    full_name: str
    phone: str | None
    email: str | None
    contact_channel: str | None
    is_active: bool


class VendorContactCreate(BaseModel):
    full_name: str = Field(min_length=1, max_length=255)
    phone: str | None = Field(default=None, max_length=50)
    email: str | None = Field(default=None, max_length=255)
    contact_channel: str | None = Field(default=None, max_length=255)


class VendorContactUpdate(BaseModel):
    full_name: str | None = Field(default=None, min_length=1, max_length=255)
    phone: str | None = Field(default=None, max_length=50)
    email: str | None = Field(default=None, max_length=255)
    contact_channel: str | None = Field(default=None, max_length=255)
    is_active: bool | None = None


class VendorRead(ItDirectionRead):
    contacts: list[VendorContactRead] = []


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
    contact_id: uuid.UUID | None = None


class ItProductRead(ORMModel):
    id: uuid.UUID
    vendor_id: uuid.UUID | None
    # Ответственный со стороны вендора за этот продукт.
    contact_id: uuid.UUID | None = None
    name: str
    description: str | None
    is_active: bool


class NamedUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=500)
    description: str | None = None
    # Запись справочника, на которую ссылаются договоры, не удаляют, а выключают.
    is_active: bool | None = None


class ItProgramUpdate(NamedUpdate):
    direction_id: uuid.UUID | None = None


class ItProductUpdate(NamedUpdate):
    vendor_id: uuid.UUID | None = None
    contact_id: uuid.UUID | None = None


class ProgramProductLink(BaseModel):
    program_id: uuid.UUID
    product_id: uuid.UUID


class ProgramProductsWrite(BaseModel):
    product_ids: list[uuid.UUID] = Field(default_factory=list)
