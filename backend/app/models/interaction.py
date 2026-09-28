"""Состав взаимодействия: программы, продукты, их связь и контакты вуза.

Продукт во взаимодействии всегда связан хотя бы с одной программой. Связь
вне справочника program_products руководитель разрешает как исключение.
"""

import uuid
from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import Boolean, DateTime, ForeignKey, String, Text, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, CreatedAtMixin, UUIDPrimaryKeyMixin
from app.enums import ProductTransferStatus, ProgramImplementationStatus
from app.models.catalog import ItProduct, ItProgram
from app.models.university import UniversityContact
from app.models.user import User

if TYPE_CHECKING:
    from app.models.contract import License
    from app.models.workflow import WorkflowInstance


class InteractionProgram(UUIDPrimaryKeyMixin, CreatedAtMixin, Base):
    """ИТ-программа во взаимодействии со своим статусом внедрения."""

    __tablename__ = "interaction_programs"
    __table_args__ = (UniqueConstraint("workflow_instance_id", "program_id"),)

    workflow_instance_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("workflow_instances.id", ondelete="CASCADE"), index=True
    )
    program_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("it_programs.id", ondelete="RESTRICT"), index=True
    )
    implementation_status: Mapped[str] = mapped_column(
        String(32),
        default=ProgramImplementationStatus.NOT_STARTED,
        server_default=ProgramImplementationStatus.NOT_STARTED,
    )

    interaction: Mapped["WorkflowInstance"] = relationship(back_populates="programs")
    program: Mapped[ItProgram] = relationship()
    product_links: Mapped[list["InteractionProgramProduct"]] = relationship(
        back_populates="program_link", cascade="all, delete-orphan"
    )


class InteractionProduct(UUIDPrimaryKeyMixin, CreatedAtMixin, Base):
    """ИТ-продукт во взаимодействии со своим статусом передачи."""

    __tablename__ = "interaction_products"
    __table_args__ = (UniqueConstraint("workflow_instance_id", "product_id"),)

    workflow_instance_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("workflow_instances.id", ondelete="CASCADE"), index=True
    )
    product_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("it_products.id", ondelete="RESTRICT"), index=True
    )
    transfer_status: Mapped[str] = mapped_column(
        String(32),
        default=ProductTransferStatus.NOT_STARTED,
        server_default=ProductTransferStatus.NOT_STARTED,
    )

    interaction: Mapped["WorkflowInstance"] = relationship(back_populates="products")
    product: Mapped[ItProduct] = relationship()
    program_links: Mapped[list["InteractionProgramProduct"]] = relationship(
        back_populates="product_link", cascade="all, delete-orphan"
    )
    licenses: Mapped[list["License"]] = relationship(
        back_populates="interaction_product", cascade="all, delete-orphan"
    )


class InteractionProgramProduct(Base):
    """Продукт используется в программе этого взаимодействия."""

    __tablename__ = "interaction_program_products"

    interaction_program_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("interaction_programs.id", ondelete="CASCADE"), primary_key=True
    )
    interaction_product_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("interaction_products.id", ondelete="CASCADE"), primary_key=True
    )
    # Связи нет в справочнике program_products: исключение с комментарием.
    is_exception: Mapped[bool] = mapped_column(Boolean, default=False, server_default="false")
    exception_comment: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_by_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    program_link: Mapped[InteractionProgram] = relationship(back_populates="product_links")
    product_link: Mapped[InteractionProduct] = relationship(back_populates="program_links")
    created_by: Mapped[User | None] = relationship()


class InteractionContact(Base):
    """Ответственный от вуза по взаимодействию. Сам контакт хранится у вуза."""

    __tablename__ = "interaction_contacts"

    workflow_instance_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("workflow_instances.id", ondelete="CASCADE"), primary_key=True
    )
    contact_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("university_contacts.id", ondelete="CASCADE"), primary_key=True
    )
    role: Mapped[str | None] = mapped_column(String(255), nullable=True)
    is_primary: Mapped[bool] = mapped_column(Boolean, default=False, server_default="false")

    interaction: Mapped["WorkflowInstance"] = relationship(back_populates="contacts")
    contact: Mapped[UniversityContact] = relationship()
