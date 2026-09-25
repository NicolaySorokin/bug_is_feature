"""Вузы и их контактные лица."""

import uuid
from typing import TYPE_CHECKING

from sqlalchemy import Boolean, ForeignKey, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, TimestampMixin, UUIDPrimaryKeyMixin
from app.models.user import User

if TYPE_CHECKING:
    from app.models.contract import Contract


class University(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "universities"

    name: Mapped[str] = mapped_column(String(500), index=True)
    short_name: Mapped[str | None] = mapped_column(String(100), nullable=True)
    city: Mapped[str | None] = mapped_column(String(255), nullable=True)
    website: Mapped[str | None] = mapped_column(String(500), nullable=True)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    # Закреплённый за вузом менеджер ИТ Школы.
    manager_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, server_default="true")

    manager: Mapped[User | None] = relationship()
    contacts: Mapped[list["UniversityContact"]] = relationship(
        back_populates="university",
        cascade="all, delete-orphan",
        order_by="UniversityContact.full_name",
    )
    contracts: Mapped[list["Contract"]] = relationship(back_populates="university")


class UniversityContact(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """Контактное лицо хранится на уровне вуза.

    Связь с конкретным договором задаётся через contract_contacts, поэтому
    один человек не дублируется для каждого договора.
    """

    __tablename__ = "university_contacts"

    university_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("universities.id", ondelete="CASCADE"), index=True
    )
    full_name: Mapped[str] = mapped_column(String(255))
    position: Mapped[str | None] = mapped_column(String(255), nullable=True)
    email: Mapped[str | None] = mapped_column(String(255), nullable=True)
    phone: Mapped[str | None] = mapped_column(String(50), nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, server_default="true")

    university: Mapped[University] = relationship(back_populates="contacts")
