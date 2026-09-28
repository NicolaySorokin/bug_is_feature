"""Справочники: ИТ-направления, ИТ-программы, вендоры, ИТ-продукты."""

import uuid

from sqlalchemy import Boolean, ForeignKey, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, TimestampMixin, UUIDPrimaryKeyMixin


class ItDirection(UUIDPrimaryKeyMixin, Base):
    __tablename__ = "it_directions"

    name: Mapped[str] = mapped_column(String(255), unique=True)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, server_default="true")

    programs: Mapped[list["ItProgram"]] = relationship(back_populates="direction")


class ItProgram(UUIDPrimaryKeyMixin, Base):
    __tablename__ = "it_programs"

    direction_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("it_directions.id", ondelete="SET NULL"), nullable=True, index=True
    )
    name: Mapped[str] = mapped_column(String(500), index=True)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, server_default="true")

    direction: Mapped[ItDirection | None] = relationship(back_populates="programs")
    products: Mapped[list["ItProduct"]] = relationship(
        secondary="program_products", back_populates="programs"
    )


class Vendor(UUIDPrimaryKeyMixin, Base):
    __tablename__ = "vendors"

    name: Mapped[str] = mapped_column(String(255), unique=True)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, server_default="true")

    products: Mapped[list["ItProduct"]] = relationship(back_populates="vendor")
    contacts: Mapped[list["VendorContact"]] = relationship(
        back_populates="vendor",
        cascade="all, delete-orphan",
        order_by="VendorContact.full_name",
    )


class VendorContact(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """Ответственный со стороны вендора.

    У одной компании по разным продуктам бывают разные люди, поэтому ссылка
    на контакт лежит у продукта.
    """

    __tablename__ = "vendor_contacts"

    vendor_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("vendors.id", ondelete="CASCADE"), index=True
    )
    full_name: Mapped[str] = mapped_column(String(255))
    phone: Mapped[str | None] = mapped_column(String(50), nullable=True)
    email: Mapped[str | None] = mapped_column(String(255), nullable=True)
    # «Способ связи»: почта, Telegram и т. п.
    contact_channel: Mapped[str | None] = mapped_column(String(255), nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, server_default="true")

    vendor: Mapped[Vendor] = relationship(back_populates="contacts")


class ItProduct(UUIDPrimaryKeyMixin, Base):
    __tablename__ = "it_products"

    vendor_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("vendors.id", ondelete="SET NULL"), nullable=True, index=True
    )
    # Ответственный со стороны вендора за этот продукт.
    contact_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("vendor_contacts.id", ondelete="SET NULL"), nullable=True
    )
    name: Mapped[str] = mapped_column(String(500), index=True)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, server_default="true")

    vendor: Mapped[Vendor | None] = relationship(back_populates="products")
    programs: Mapped[list[ItProgram]] = relationship(
        secondary="program_products", back_populates="products"
    )


class ProgramProduct(Base):
    """Связь программ и продуктов вне контекста договора."""

    __tablename__ = "program_products"

    program_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("it_programs.id", ondelete="CASCADE"), primary_key=True
    )
    product_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("it_products.id", ondelete="CASCADE"), primary_key=True
    )
