"""Схемы интеграций: источники и запуски синхронизации."""

import uuid
from datetime import datetime

from pydantic import BaseModel

from app.enums import IntegrationRunStatus
from app.schemas.common import ORMModel


class IntegrationSourceRead(ORMModel):
    id: uuid.UUID
    code: str
    name: str
    base_url: str | None
    is_enabled: bool
    # Адрес внешней системы не задан - адаптер отвечает тестовыми данными.
    uses_fixture: bool = False


class IntegrationSourceUpdate(BaseModel):
    is_enabled: bool


class IntegrationRunRead(ORMModel):
    id: uuid.UUID
    source_id: uuid.UUID
    source_code: str = ""
    triggered_by: uuid.UUID | None
    status: IntegrationRunStatus
    started_at: datetime | None
    finished_at: datetime | None
    records_received: int
    records_created: int
    records_updated: int
    records_failed: int
    error_message: str | None
    notes: str | None = None

    @classmethod
    def from_model(cls, run, code: str | None = None) -> "IntegrationRunRead":  # noqa: ANN001
        """Код источника берём из связи, а если она не подгружена - из аргумента."""
        model = cls.model_validate(run)
        source = run.__dict__.get("source")
        model.source_code = source.code if source is not None else (code or "")
        return model
