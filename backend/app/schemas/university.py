"""Схемы вузов и контактных лиц."""

import uuid
from datetime import datetime

from pydantic import BaseModel, Field

from app.schemas.common import ORMModel
from app.schemas.user import UserRead


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
    city: str | None = Field(default=None, max_length=255)
    website: str | None = Field(default=None, max_length=500)
    description: str | None = None
    manager_id: uuid.UUID | None = None


class UniversityUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=500)
    short_name: str | None = Field(default=None, max_length=100)
    city: str | None = Field(default=None, max_length=255)
    website: str | None = Field(default=None, max_length=500)
    description: str | None = None
    manager_id: uuid.UUID | None = None
    is_active: bool | None = None


class UniversityRead(ORMModel):
    id: uuid.UUID
    name: str
    short_name: str | None
    city: str | None
    website: str | None
    description: str | None
    manager_id: uuid.UUID | None
    is_active: bool


class UniversityListItem(UniversityRead):
    manager: UserRead | None = None
    contracts_count: int = 0
    active_contracts_count: int = 0


class UniversityDetail(UniversityListItem):
    contacts: list[UniversityContactRead] = []
    created_at: datetime | None = None
