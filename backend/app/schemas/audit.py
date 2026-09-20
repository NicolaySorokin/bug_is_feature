"""Схемы журнала изменений."""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from app.enums import AuditAction
from app.schemas.common import ORMModel


class AuditEntryRead(ORMModel):
    id: uuid.UUID
    user_id: uuid.UUID | None
    user_name: str = ""
    entity_type: str
    entity_id: uuid.UUID | None
    action: AuditAction
    before_data: dict[str, Any] | None
    after_data: dict[str, Any] | None
    created_at: datetime

    @classmethod
    def from_model(cls, entry) -> AuditEntryRead:  # noqa: ANN001 - модель SQLAlchemy
        model = cls.model_validate(entry)
        user = entry.__dict__.get("user")
        if user is not None:
            model.user_name = user.full_name
        return model
