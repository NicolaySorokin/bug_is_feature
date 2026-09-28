"""Схемы импорта каталогов из XLS и XLSX."""

import uuid
from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field

from app.enums import ImportRunStatus, ImportType
from app.schemas.common import ORMModel


class ImportFieldInfo(BaseModel):
    key: str
    title: str
    aliases: list[str] = Field(default_factory=list)
    required: bool


class ImportTypeInfo(BaseModel):
    import_type: ImportType
    title: str
    description: str
    fields: list[ImportFieldInfo]


class ImportRunRead(ORMModel):
    id: uuid.UUID
    filename: str
    import_type: ImportType
    status: ImportRunStatus
    mapping: dict[str, Any] | None
    rows_total: int
    rows_created: int
    rows_updated: int
    rows_failed: int
    created_at: datetime
    finished_at: datetime | None


class ImportErrorRead(BaseModel):
    row_number: int
    field_name: str | None
    message: str


class ImportPreview(BaseModel):
    """Предпросмотр: что нашли в файле и как предлагаем сопоставить колонки."""

    run: ImportRunRead
    headers: list[str]
    suggested_mapping: dict[str, str | None]
    sample_rows: list[list[str]]
    rows_total: int
    fields: list[ImportFieldInfo]


class ImportMappingRequest(BaseModel):
    """Сопоставление «поле системы: заголовок колонки файла».

    Пустое сопоставление значит «взять предложенное при загрузке».
    """

    mapping: dict[str, str | None] = Field(default_factory=dict)


class ImportResult(BaseModel):
    run: ImportRunRead
    errors: list[ImportErrorRead] = Field(default_factory=list)
