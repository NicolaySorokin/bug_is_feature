"""Комментарии и вложения.

Содержимое файлов лежит на диске сервера, в PostgreSQL хранятся только
сведения о файле и путь к нему (раздел 9.2).
"""

import uuid

from sqlalchemy import BigInteger, ForeignKey, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, CreatedAtMixin, UUIDPrimaryKeyMixin
from app.models.contract import Contract
from app.models.user import User


class Comment(UUIDPrimaryKeyMixin, CreatedAtMixin, Base):
    __tablename__ = "comments"

    contract_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("contracts.id", ondelete="CASCADE"), index=True
    )
    workflow_event_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("workflow_events.id", ondelete="SET NULL"), nullable=True, index=True
    )
    author_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    text: Mapped[str] = mapped_column(Text)

    contract: Mapped[Contract] = relationship()
    author: Mapped[User | None] = relationship()


class Attachment(UUIDPrimaryKeyMixin, CreatedAtMixin, Base):
    __tablename__ = "attachments"

    contract_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("contracts.id", ondelete="CASCADE"), index=True
    )
    workflow_event_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("workflow_events.id", ondelete="SET NULL"), nullable=True, index=True
    )
    uploaded_by: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    original_name: Mapped[str] = mapped_column(String(500))
    storage_path: Mapped[str] = mapped_column(String(1000))
    mime_type: Mapped[str | None] = mapped_column(String(255), nullable=True)
    size_bytes: Mapped[int | None] = mapped_column(BigInteger, nullable=True)

    contract: Mapped[Contract] = relationship()
    uploader: Mapped[User | None] = relationship()
