"""Схемы интеграций: источники, запуски, ошибки по записям и сопоставление."""

import uuid
from datetime import datetime
from typing import Any

from pydantic import BaseModel

from app.enums import IntegrationRunStatus, MappingStatus
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


class IntegrationRunErrorRead(ORMModel):
    id: uuid.UUID
    entity_type: str
    external_id: str | None
    message: str


class IntegrationRunRead(ORMModel):
    id: uuid.UUID
    source_id: uuid.UUID
    source_code: str = ""
    triggered_by: uuid.UUID | None
    trigger: str = "manual"
    status: IntegrationRunStatus
    started_at: datetime | None
    finished_at: datetime | None
    attempts: int = 1
    records_received: int
    records_created: int
    records_updated: int
    records_failed: int
    records_pending: int = 0
    error_message: str | None
    notes: str | None = None
    errors: list[IntegrationRunErrorRead] = []

    @classmethod
    def from_model(cls, run, code: str | None = None) -> "IntegrationRunRead":  # noqa: ANN001
        """Код источника и ошибки берём из связей, если они подгружены."""
        errors = run.__dict__.get("errors")
        source = run.__dict__.get("source")
        model = cls.model_validate(
            {
                **{
                    key: getattr(run, key)
                    for key in cls.model_fields
                    if key not in {"source_code", "errors"}
                },
                "errors": errors or [],
            }
        )
        model.source_code = source.code if source is not None else (code or "")
        return model


class MappingRead(BaseModel):
    """Внешняя запись в очереди ручного сопоставления."""

    id: uuid.UUID
    source_code: str
    entity_type: str
    entity_title: str
    external_id: str
    external_name: str
    payload: dict[str, Any] | None = None
    suggested_entity_id: uuid.UUID | None = None
    suggested_name: str | None = None
    status: MappingStatus
    entity_id: uuid.UUID | None = None
    entity_name: str | None = None
    created_at: datetime
    resolved_at: datetime | None = None


class MappingResolve(BaseModel):
    """Решение по записи: сопоставить с существующей записью системы."""

    entity_id: uuid.UUID
