"""Вузы и их контакты.

Путь записи: pending, confirmed, archived. ИНН служит стабильным ключом,
при объединении дублей поглощённая запись остаётся в архиве.
"""

import uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, TimestampMixin, UUIDPrimaryKeyMixin
from app.enums import UniversityStatus
from app.models.user import User


class University(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "universities"

    name: Mapped[str] = mapped_column(String(500), index=True)
    short_name: Mapped[str | None] = mapped_column(String(100), nullable=True)
    # ИНН: по нему вуз узнаётся в любом источнике.
    inn: Mapped[str | None] = mapped_column(String(12), nullable=True, unique=True)
    city: Mapped[str | None] = mapped_column(String(255), nullable=True)
    website: Mapped[str | None] = mapped_column(String(500), nullable=True)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    # Реквизиты для договора одним текстом: у вузов разные форматы.
    requisites: Mapped[str | None] = mapped_column(Text, nullable=True)
    # Менеджер по умолчанию для новых взаимодействий вуза.
    manager_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    status: Mapped[str] = mapped_column(
        String(16),
        default=UniversityStatus.CONFIRMED,
        server_default=UniversityStatus.CONFIRMED,
        index=True,
    )
    # Откуда запись: manual, import, site, lms.
    origin: Mapped[str] = mapped_column(String(16), default="manual", server_default="manual")
    confirmed_by_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    confirmed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    # Если запись поглощена при объединении, ссылка на итоговую.
    merged_into_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("universities.id", ondelete="SET NULL"), nullable=True
    )

    manager: Mapped[User | None] = relationship(foreign_keys=[manager_id])
    contacts: Mapped[list["UniversityContact"]] = relationship(
        back_populates="university",
        cascade="all, delete-orphan",
        order_by="UniversityContact.full_name",
    )

    @property
    def is_active(self) -> bool:
        return self.status != UniversityStatus.ARCHIVED

    @property
    def display_name(self) -> str:
        """Краткое название, а если его нет, полное."""
        return self.short_name or self.name


class UniversityContact(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """Контактное лицо вуза. С взаимодействиями связано через interaction_contacts."""

    __tablename__ = "university_contacts"

    university_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("universities.id", ondelete="CASCADE"), index=True
    )
    full_name: Mapped[str] = mapped_column(String(255))
    position: Mapped[str | None] = mapped_column(String(255), nullable=True)
    email: Mapped[str | None] = mapped_column(String(255), nullable=True)
    phone: Mapped[str | None] = mapped_column(String(50), nullable=True)
    is_active: Mapped[bool] = mapped_column(default=True, server_default="true")

    university: Mapped[University] = relationship(back_populates="contacts")
