"""Рабочий процесс и взаимодействие с вузом.

Шаблон описывает типовой путь, версия - его редакцию, экземпляр - конкретное
взаимодействие с вузом (раздел 1 «Решений по бизнес-модели»). Отдельной
таблицы взаимодействий нет: бизнес-сущностью стал ``workflow_instances``.
Договор появляется в ходе взаимодействия и к запуску процесса не нужен
(``Взаимодействие 0 -> 1 Договор``).

Ключевое правило раздела 3.1: изменение шаблона не меняет уже запущенные
процессы. Поэтому этапы и переходы принадлежат версии шаблона, экземпляр
навсегда привязан к конкретной версии, а опубликованную версию структурно
менять нельзя - это держит и база (триггеры в app.db.guards).
"""

import uuid
from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import (
    Boolean,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
    text,
)
from sqlalchemy.dialects.postgresql import ARRAY
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, CreatedAtMixin, TimestampMixin, UUIDPrimaryKeyMixin
from app.enums import InteractionSource, InteractionStatus, WorkflowVersionStatus
from app.models.university import University
from app.models.user import User

if TYPE_CHECKING:
    from app.models.contract import Contract
    from app.models.interaction import (
        InteractionContact,
        InteractionProduct,
        InteractionProgram,
    )


class WorkflowTemplate(UUIDPrimaryKeyMixin, CreatedAtMixin, Base):
    """Тип процесса, например «Базовый процесс взаимодействия с вузом»."""

    __tablename__ = "workflow_templates"

    name: Mapped[str] = mapped_column(String(255), unique=True)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    # enabled / disabled: отключённый шаблон не предлагается для новых взаимодействий.
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, server_default="true")

    versions: Mapped[list["WorkflowVersion"]] = relationship(
        back_populates="template", cascade="all, delete-orphan"
    )


class WorkflowVersion(UUIDPrimaryKeyMixin, CreatedAtMixin, Base):
    """Редакция шаблона: draft -> active -> deprecated -> retired."""

    __tablename__ = "workflow_versions"
    __table_args__ = (
        UniqueConstraint("template_id", "version_number"),
        # Действующая версия у шаблона одна - это гарантирует база.
        Index(
            "uq_workflow_versions_active",
            "template_id",
            unique=True,
            postgresql_where=text("status = 'active'"),
        ),
    )

    template_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("workflow_templates.id", ondelete="CASCADE"), index=True
    )
    version_number: Mapped[int] = mapped_column(Integer, default=1)
    status: Mapped[str] = mapped_column(
        String(16),
        default=WorkflowVersionStatus.DRAFT,
        server_default=WorkflowVersionStatus.DRAFT,
    )
    published_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    # Когда версию сменила новая действующая и когда вывели из использования.
    deprecated_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    retired_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

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
        return self.status != WorkflowVersionStatus.DRAFT

    @property
    def is_draft(self) -> bool:
        return self.status == WorkflowVersionStatus.DRAFT


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
    # Стартовый этап задаётся явно, а не выбирается по сортировке.
    is_initial: Mapped[bool] = mapped_column(Boolean, default=False, server_default="false")
    is_optional: Mapped[bool] = mapped_column(Boolean, default=False, server_default="false")
    is_final: Mapped[bool] = mapped_column(Boolean, default=False, server_default="false")
    # Какой бизнес-результат даёт финальный этап: successful / partial /
    # unsuccessful. У нефинальных этапов пусто.
    outcome: Mapped[str | None] = mapped_column(String(16), nullable=True)
    # Через сколько дней без движения этап считается просроченным (раздел 7).
    sla_days: Mapped[int | None] = mapped_column(Integer, nullable=True)
    # Типы документов, без которых с этапа нельзя уйти вперёд (DocumentType).
    required_documents: Mapped[list[str]] = mapped_column(
        ARRAY(String(32)), default=list, server_default="{}"
    )
    # Статусы программ и продуктов взаимодействия, которые этап ставит сам
    # при входе в него: внедрение согласовано с ходом процесса, а ручное
    # изменение - исключение с комментарием.
    program_status_on_enter: Mapped[str | None] = mapped_column(String(32), nullable=True)
    product_status_on_enter: Mapped[str | None] = mapped_column(String(32), nullable=True)
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


class WorkflowInstance(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """Взаимодействие с вузом: отдельная инициатива со своим ответственным,
    составом программ и продуктов и ходом по workflow."""

    __tablename__ = "workflow_instances"

    university_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("universities.id", ondelete="RESTRICT"), index=True
    )
    # Ответственный за это взаимодействие. Пусто - ждёт назначения руководителем.
    manager_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), nullable=True, index=True
    )
    title: Mapped[str | None] = mapped_column(String(500), nullable=True)
    source: Mapped[str] = mapped_column(
        String(16), default=InteractionSource.MANUAL, server_default=InteractionSource.MANUAL
    )
    comment: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_by_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )

    workflow_version_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("workflow_versions.id", ondelete="RESTRICT"), index=True
    )
    # Пусто, пока взаимодействие в черновике и процесс не запущен.
    current_stage_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("workflow_stages.id", ondelete="RESTRICT"), nullable=True
    )
    status: Mapped[str] = mapped_column(
        String(32),
        default=InteractionStatus.DRAFT,
        server_default=InteractionStatus.DRAFT,
        index=True,
    )
    current_stage_started_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    # Блокировка: причина видна в карточке и на главной, а не только в истории.
    blocked_reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    blocked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    # Закрытие: бизнес-результат не подменяется жизненным статусом.
    outcome: Mapped[str | None] = mapped_column(String(16), nullable=True)
    closure_reason: Mapped[str | None] = mapped_column(String(32), nullable=True)
    closure_comment: Mapped[str | None] = mapped_column(Text, nullable=True)
    closed_by_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    closed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    university: Mapped[University] = relationship()
    manager: Mapped[User | None] = relationship(foreign_keys=[manager_id])
    created_by: Mapped[User | None] = relationship(foreign_keys=[created_by_id])
    closed_by: Mapped[User | None] = relationship(foreign_keys=[closed_by_id])
    version: Mapped[WorkflowVersion] = relationship()
    current_stage: Mapped[WorkflowStage | None] = relationship()
    events: Mapped[list["WorkflowEvent"]] = relationship(
        back_populates="instance",
        cascade="all, delete-orphan",
        order_by="WorkflowEvent.created_at",
    )
    contract: Mapped["Contract | None"] = relationship(
        back_populates="interaction", uselist=False
    )
    programs: Mapped[list["InteractionProgram"]] = relationship(
        back_populates="interaction", cascade="all, delete-orphan"
    )
    products: Mapped[list["InteractionProduct"]] = relationship(
        back_populates="interaction", cascade="all, delete-orphan"
    )
    contacts: Mapped[list["InteractionContact"]] = relationship(
        back_populates="interaction", cascade="all, delete-orphan"
    )


# Бизнес-имя экземпляра процесса.
Interaction = WorkflowInstance


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
