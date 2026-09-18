"""Рабочий процесс по договору: шаблоны, версии, этапы, переходы, история.

Ключевое правило раздела 3.1: изменение шаблона не меняет уже запущенные
процессы. Поэтому этапы и переходы принадлежат версии шаблона, а экземпляр
процесса жёстко привязан к конкретной версии.
"""

import uuid
from datetime import datetime
from typing import TYPE_CHECKING

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

from app.db.base import Base, CreatedAtMixin, UUIDPrimaryKeyMixin
from app.enums import WorkflowInstanceStatus
from app.models.user import User

if TYPE_CHECKING:
    from app.models.contract import Contract


class WorkflowTemplate(UUIDPrimaryKeyMixin, CreatedAtMixin, Base):
    __tablename__ = "workflow_templates"

    name: Mapped[str] = mapped_column(String(255), unique=True)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, server_default="true")

    versions: Mapped[list["WorkflowVersion"]] = relationship(
        back_populates="template", cascade="all, delete-orphan"
    )


class WorkflowVersion(UUIDPrimaryKeyMixin, CreatedAtMixin, Base):
    __tablename__ = "workflow_versions"
    __table_args__ = (UniqueConstraint("template_id", "version_number"),)

    template_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("workflow_templates.id", ondelete="CASCADE"), index=True
    )
    version_number: Mapped[int] = mapped_column(Integer, default=1)
    published_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    template: Mapped[WorkflowTemplate] = relationship(back_populates="versions")
    stages: Mapped[list["WorkflowStage"]] = relationship(
        back_populates="version",
        cascade="all, delete-orphan",
        order_by="WorkflowStage.sort_order",
    )
    transitions: Mapped[list["WorkflowTransition"]] = relationship(
        back_populates="version", cascade="all, delete-orphan"
    )

    @property
    def is_published(self) -> bool:
        return self.published_at is not None


class WorkflowStage(UUIDPrimaryKeyMixin, Base):
    __tablename__ = "workflow_stages"
    __table_args__ = (UniqueConstraint("workflow_version_id", "code"),)

    workflow_version_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("workflow_versions.id", ondelete="CASCADE"), index=True
    )
    code: Mapped[str] = mapped_column(String(64))
    name: Mapped[str] = mapped_column(String(255))
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    sort_order: Mapped[int] = mapped_column(Integer, default=0)
    is_optional: Mapped[bool] = mapped_column(Boolean, default=False, server_default="false")
    is_final: Mapped[bool] = mapped_column(Boolean, default=False, server_default="false")
    # Через сколько дней без движения этап считается просроченным (раздел 7).
    sla_days: Mapped[int | None] = mapped_column(Integer, nullable=True)
    # Координаты узла на схеме. Перемещение узла меняет только расположение
    # схемы и не влияет на бизнес-логику (раздел 3.2).
    layout_x: Mapped[int | None] = mapped_column(Integer, nullable=True)
    layout_y: Mapped[int | None] = mapped_column(Integer, nullable=True)

    version: Mapped[WorkflowVersion] = relationship(back_populates="stages")


class WorkflowTransition(UUIDPrimaryKeyMixin, Base):
    """Допустимый переход между этапами внутри одной версии шаблона."""

    __tablename__ = "workflow_transitions"
    __table_args__ = (UniqueConstraint("from_stage_id", "to_stage_id"),)

    workflow_version_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("workflow_versions.id", ondelete="CASCADE"), index=True
    )
    from_stage_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("workflow_stages.id", ondelete="CASCADE"), index=True
    )
    to_stage_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("workflow_stages.id", ondelete="CASCADE"), index=True
    )
    name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    # Возврат назад по разрешённому переходу (раздел 3.3).
    is_backward: Mapped[bool] = mapped_column(Boolean, default=False, server_default="false")
    requires_comment: Mapped[bool] = mapped_column(
        Boolean, default=False, server_default="false"
    )

    version: Mapped[WorkflowVersion] = relationship(back_populates="transitions")
    from_stage: Mapped[WorkflowStage] = relationship(foreign_keys=[from_stage_id])
    to_stage: Mapped[WorkflowStage] = relationship(foreign_keys=[to_stage_id])


class WorkflowInstance(UUIDPrimaryKeyMixin, Base):
    """Ход работы по конкретному договору."""

    __tablename__ = "workflow_instances"

    contract_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("contracts.id", ondelete="CASCADE"), index=True
    )
    workflow_version_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("workflow_versions.id", ondelete="RESTRICT"), index=True
    )
    current_stage_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("workflow_stages.id", ondelete="RESTRICT"), nullable=True
    )
    status: Mapped[str] = mapped_column(
        String(32),
        default=WorkflowInstanceStatus.IN_PROGRESS,
        server_default=WorkflowInstanceStatus.IN_PROGRESS,
    )
    current_stage_started_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    completed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    contract: Mapped["Contract"] = relationship(back_populates="workflow_instances")
    version: Mapped[WorkflowVersion] = relationship()
    current_stage: Mapped[WorkflowStage | None] = relationship()
    events: Mapped[list["WorkflowEvent"]] = relationship(
        back_populates="instance",
        cascade="all, delete-orphan",
        order_by="WorkflowEvent.created_at",
    )


class WorkflowEvent(UUIDPrimaryKeyMixin, CreatedAtMixin, Base):
    """Запись истории: кто, когда, откуда, куда и с каким комментарием."""

    __tablename__ = "workflow_events"

    workflow_instance_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("workflow_instances.id", ondelete="CASCADE"), index=True
    )
    from_stage_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("workflow_stages.id", ondelete="SET NULL"), nullable=True
    )
    to_stage_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("workflow_stages.id", ondelete="SET NULL"), nullable=True
    )
    user_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    event_type: Mapped[str] = mapped_column(String(32))
    comment: Mapped[str | None] = mapped_column(Text, nullable=True)

    instance: Mapped[WorkflowInstance] = relationship(back_populates="events")
    from_stage: Mapped[WorkflowStage | None] = relationship(foreign_keys=[from_stage_id])
    to_stage: Mapped[WorkflowStage | None] = relationship(foreign_keys=[to_stage_id])
    user: Mapped[User | None] = relationship()
