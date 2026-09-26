"""Интеграции с внешними системами: источники, запуски, связи и сопоставление.

Раздел 5 концепции: данные приходят из LMS и с сайта ИТ Школы. Источник
описывает, куда ходить, запуск - что из этого вышло (включая ошибки по
отдельным записям), а связь с внешним объектом позволяет при повторной
синхронизации обновить ту же запись, а не создать дубль.

Идентификатор внешнего объекта уникален в пределах источника и типа.
Запись без связи по названию не сопоставляется молча: она попадает
в очередь сопоставления, где администратор выбирает существующую запись
системы или разрешает завести новую.
"""

import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import (
    Boolean,
    DateTime,
    ForeignKey,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, CreatedAtMixin, UUIDPrimaryKeyMixin
from app.enums import IntegrationRunStatus, MappingStatus
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
    # manual - кнопка в интерфейсе, schedule - расписание, file - загрузка ответа файлом.
    trigger: Mapped[str] = mapped_column(String(16), default="manual", server_default="manual")
    status: Mapped[str] = mapped_column(
        String(32),
        default=IntegrationRunStatus.RUNNING,
        server_default=IntegrationRunStatus.RUNNING,
    )
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    finished_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    # Сколько попыток обращения к источнику понадобилось (повторы при сбоях сети).
    attempts: Mapped[int] = mapped_column(Integer, default=1, server_default="1")
    records_received: Mapped[int] = mapped_column(Integer, default=0, server_default="0")
    records_created: Mapped[int] = mapped_column(Integer, default=0, server_default="0")
    records_updated: Mapped[int] = mapped_column(Integer, default=0, server_default="0")
    records_failed: Mapped[int] = mapped_column(Integer, default=0, server_default="0")
    # Записи, ожидающие ручного сопоставления.
    records_pending: Mapped[int] = mapped_column(Integer, default=0, server_default="0")
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    # Пояснения к запуску: что пропущено и какие поля не сохранены.
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)

    source: Mapped[IntegrationSource] = relationship(back_populates="runs")
    user: Mapped[User | None] = relationship()
    errors: Mapped[list["IntegrationRunError"]] = relationship(
        back_populates="run", cascade="all, delete-orphan", order_by="IntegrationRunError.id"
    )


class IntegrationRunError(UUIDPrimaryKeyMixin, Base):
    """Ошибка по отдельной записи источника: запуск при этом не падает целиком."""

    __tablename__ = "integration_run_errors"

    run_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("integration_runs.id", ondelete="CASCADE"), index=True
    )
    entity_type: Mapped[str] = mapped_column(String(64))
    external_id: Mapped[str | None] = mapped_column(String(255), nullable=True)
    message: Mapped[str] = mapped_column(Text)

    run: Mapped[IntegrationRun] = relationship(back_populates="errors")


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


class IntegrationMapping(UUIDPrimaryKeyMixin, CreatedAtMixin, Base):
    """Внешняя запись, которую система не смогла опознать сама.

    Пока решения нет, запись не загружается; после решения следующий
    обмен подхватит её по созданной связи.
    """

    __tablename__ = "integration_mappings"
    __table_args__ = (UniqueConstraint("source_id", "entity_type", "external_id"),)

    source_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("integration_sources.id", ondelete="CASCADE"), index=True
    )
    entity_type: Mapped[str] = mapped_column(String(64))
    external_id: Mapped[str] = mapped_column(String(255))
    # Как запись называется в источнике и её данные - для решения человеком.
    external_name: Mapped[str] = mapped_column(String(500))
    payload: Mapped[dict[str, Any] | None] = mapped_column(JSONB, nullable=True)
    # Предложение системы: запись с таким же названием.
    suggested_entity_id: Mapped[uuid.UUID | None] = mapped_column(nullable=True)
    status: Mapped[str] = mapped_column(
        String(16), default=MappingStatus.PENDING, server_default=MappingStatus.PENDING
    )
    entity_id: Mapped[uuid.UUID | None] = mapped_column(nullable=True)
    resolved_by_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    resolved_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    source: Mapped[IntegrationSource] = relationship()
