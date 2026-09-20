"""Схемы комментариев и вложений."""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import TYPE_CHECKING

from pydantic import BaseModel, Field

from app.schemas.common import ORMModel
from app.schemas.user import UserRead

if TYPE_CHECKING:  # pragma: no cover - только для подсказок типов
    from app.models.content import Attachment


class CommentCreate(BaseModel):
    text: str = Field(min_length=1)
    # Комментарий можно привязать к конкретному событию процесса.
    workflow_event_id: uuid.UUID | None = None


class CommentRead(ORMModel):
    id: uuid.UUID
    contract_id: uuid.UUID
    workflow_event_id: uuid.UUID | None
    author_id: uuid.UUID | None
    text: str
    created_at: datetime
    author: UserRead | None = None


class AttachmentRead(ORMModel):
    id: uuid.UUID
    contract_id: uuid.UUID
    workflow_event_id: uuid.UUID | None
    uploaded_by: uuid.UUID | None
    original_name: str
    mime_type: str | None
    size_bytes: int | None
    created_at: datetime
    uploader: UserRead | None = None
    # Заполняется в from_model: в самой модели такого поля нет.
    download_url: str = ""

    @classmethod
    def from_model(cls, attachment: Attachment, prefix: str) -> AttachmentRead:
        """Ссылку на скачивание собираем здесь, чтобы клиент её не строил сам."""
        model = cls.model_validate(attachment)
        model.download_url = f"{prefix}/attachments/{attachment.id}/download"
        return model
