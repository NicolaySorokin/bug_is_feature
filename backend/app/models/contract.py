"""Договоры: состав программ и продуктов, ответственные, лицензии."""

import uuid
from datetime import date
from typing import TYPE_CHECKING

from sqlalchemy import Boolean, Date, ForeignKey, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, CreatedAtMixin, TimestampMixin, UUIDPrimaryKeyMixin
from app.enums import ContractStatus, ImplementationStatus, LicenseStatus
from app.models.catalog import ItProduct, ItProgram
from app.models.university import University, UniversityContact
from app.models.user import User

if TYPE_CHECKING:
    from app.models.workflow import WorkflowInstance


class Contract(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """Основной объект работы. У одного вуза может быть несколько договоров."""

    __tablename__ = "contracts"

    university_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("universities.id", ondelete="RESTRICT"), index=True
    )
    manager_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), nullable=True, index=True
    )
    number: Mapped[str] = mapped_column(String(100), index=True)
    title: Mapped[str | None] = mapped_column(String(500), nullable=True)
    signed_at: Mapped[date | None] = mapped_column(Date, nullable=True)
    valid_from: Mapped[date | None] = mapped_column(Date, nullable=True)
    valid_to: Mapped[date | None] = mapped_column(Date, nullable=True)
    status: Mapped[str] = mapped_column(
        String(32), default=ContractStatus.DRAFT, server_default=ContractStatus.DRAFT
    )
    comment: Mapped[str | None] = mapped_column(Text, nullable=True)

    university: Mapped[University] = relationship(back_populates="contracts")
    manager: Mapped[User | None] = relationship()
    programs: Mapped[list["ContractProgram"]] = relationship(
        back_populates="contract", cascade="all, delete-orphan"
    )
    products: Mapped[list["ContractProduct"]] = relationship(
        back_populates="contract", cascade="all, delete-orphan"
    )
    contacts: Mapped[list["ContractContact"]] = relationship(
        back_populates="contract", cascade="all, delete-orphan"
    )
    workflow_instances: Mapped[list["WorkflowInstance"]] = relationship(
        back_populates="contract", cascade="all, delete-orphan"
    )


class ContractContact(Base):
    """Ответственные от вуза по конкретному договору."""

    __tablename__ = "contract_contacts"

    contract_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("contracts.id", ondelete="CASCADE"), primary_key=True
    )
    contact_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("university_contacts.id", ondelete="CASCADE"), primary_key=True
    )
    role: Mapped[str | None] = mapped_column(String(255), nullable=True)
    is_primary: Mapped[bool] = mapped_column(Boolean, default=False, server_default="false")

    contract: Mapped[Contract] = relationship(back_populates="contacts")
    contact: Mapped[UniversityContact] = relationship()


class ContractProgram(UUIDPrimaryKeyMixin, CreatedAtMixin, Base):
    """Программа в составе договора со своим статусом внедрения."""

    __tablename__ = "contract_programs"
    __table_args__ = (UniqueConstraint("contract_id", "program_id"),)

    contract_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("contracts.id", ondelete="CASCADE"), index=True
    )
    program_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("it_programs.id", ondelete="RESTRICT"), index=True
    )
    implementation_status: Mapped[str] = mapped_column(
        String(32),
        default=ImplementationStatus.NOT_STARTED,
        server_default=ImplementationStatus.NOT_STARTED,
    )

    contract: Mapped[Contract] = relationship(back_populates="programs")
    program: Mapped[ItProgram] = relationship()


class ContractProduct(UUIDPrimaryKeyMixin, CreatedAtMixin, Base):
    """ИТ-продукт в составе договора со своим статусом передачи."""

    __tablename__ = "contract_products"
    __table_args__ = (UniqueConstraint("contract_id", "product_id"),)

    contract_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("contracts.id", ondelete="CASCADE"), index=True
    )
    product_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("it_products.id", ondelete="RESTRICT"), index=True
    )
    transfer_status: Mapped[str] = mapped_column(
        String(32),
        default=ImplementationStatus.NOT_STARTED,
        server_default=ImplementationStatus.NOT_STARTED,
    )

    contract: Mapped[Contract] = relationship(back_populates="products")
    product: Mapped[ItProduct] = relationship()
    licenses: Mapped[list["License"]] = relationship(
        back_populates="contract_product", cascade="all, delete-orphan"
    )


class License(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """Лицензия относится к конкретному продукту в конкретном договоре."""

    __tablename__ = "licenses"

    contract_product_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("contract_products.id", ondelete="CASCADE"), index=True
    )
    number: Mapped[str | None] = mapped_column(String(100), nullable=True)
    seats: Mapped[int | None] = mapped_column(nullable=True)
    signed_at: Mapped[date | None] = mapped_column(Date, nullable=True)
    valid_from: Mapped[date | None] = mapped_column(Date, nullable=True)
    valid_to: Mapped[date | None] = mapped_column(Date, nullable=True)
    status: Mapped[str] = mapped_column(
        String(32), default=LicenseStatus.ACTIVE, server_default=LicenseStatus.ACTIVE
    )

    contract_product: Mapped[ContractProduct] = relationship(back_populates="licenses")
