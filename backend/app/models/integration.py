"""Интеграции с внешними системами: источники, запуски, связи объектов.

Раздел 5 концепции: данные приходят из LMS и с сайта ИТ Школы. Источник
описывает, куда ходить, запуск - что из этого вышло, а связь с внешним
объектом позволяет при повторной синхронизации обновить ту же запись,
а не создать дубль.
"""

import uuid
from datetime import datetime

from sqlalchemy import (
    Boolean,
    DateTime,
    ForeignKey,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, UUIDPrimaryKeyMixin
from app.enums import IntegrationRunStatus
from app.models.user import User


class IntegrationSource(UUIDPrimaryKeyMixin, Base):
    __tablename__ = "integration_sources"

    code: Mapped[str] = mapped_column(String(64), unique=True)
    name: Mapped[str] = mapped_column(String(255))
    base_url: Mapped[str | None] = mapped_column(String(500), nullable=True)
    is_enabled: Mapped[bool] = mapped_column(Boolean, default=True, server_default="true")

    runs: Mapped[list["IntegrationRun"]] = relationship(
        back_populates="source", cascade="all, delete-orphan"
    )


class IntegrationRun(UUIDPrimaryKeyMixin, Base):
    """Один запуск синхронизации: когда, чем кончился, сколько записей."""

    __tablename__ = "integration_runs"

    source_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("integration_sources.id", ondelete="CASCADE"), index=True
    )
    triggered_by: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    status: Mapped[str] = mapped_column(
        String(32),
        default=IntegrationRunStatus.RUNNING,
        server_default=IntegrationRunStatus.RUNNING,
    )
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    finished_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    records_received: Mapped[int] = mapped_column(Integer, default=0, server_default="0")
    records_created: Mapped[int] = mapped_column(Integer, default=0, server_default="0")
    records_updated: Mapped[int] = mapped_column(Integer, default=0, server_default="0")
    records_failed: Mapped[int] = mapped_column(Integer, default=0, server_default="0")
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)

    source: Mapped[IntegrationSource] = relationship(back_populates="runs")
    user: Mapped[User | None] = relationship()


class ExternalLink(UUIDPrimaryKeyMixin, Base):
    """Соответствие нашей записи и объекта во внешней системе."""

    __tablename__ = "external_links"
    __table_args__ = (UniqueConstraint("source_id", "entity_type", "external_id"),)

    source_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("integration_sources.id", ondelete="CASCADE"), index=True
    )
    entity_type: Mapped[str] = mapped_column(String(64))
    entity_id: Mapped[uuid.UUID] = mapped_column(index=True)
    external_id: Mapped[str] = mapped_column(String(255))

    source: Mapped[IntegrationSource] = relationship()
