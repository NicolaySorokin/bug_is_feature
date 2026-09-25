"""Заявки на обучение и обучающиеся - данные сайта и LMS ИТ Школы.

ТЗ, раздел «Актуальность»: востребованность программы видна по статистике -
заявкам на обучение, количеству обучающихся и параллельных потоков. Эти
данные приходят извне:

* сайт отдаёт заявки: номер заявки, курс, ФИО, телефон, почта, номер
  потока (формат передан кейсодержателем, см. fixtures/site.json);
* LMS отдаёт анкеты обучающихся.

Персональные данные хранятся в минимально нужном объёме (ст. 5 152-ФЗ):
для статистики и сопоставления заявки с обучающимся хватает ФИО и
контактов. Паспорт, СНИЛС, адрес и сведения о дипломе из анкеты LMS
не сохраняются вовсе - их отбрасывает адаптер ещё до записи в базу.
Телефон хранится цифрами, почта - в нижнем регистре: так заявка
и анкета одного человека находят друг друга.
"""

import uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Integer, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, TimestampMixin, UUIDPrimaryKeyMixin
from app.models.catalog import ItProgram
from app.models.integration import IntegrationSource


class LearningApplication(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """Заявка на обучение по ИТ-программе."""

    __tablename__ = "learning_applications"
    __table_args__ = (UniqueConstraint("source_id", "external_id"),)

    source_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("integration_sources.id", ondelete="SET NULL"), nullable=True
    )
    # «Номер заявки» из внешней системы.
    external_id: Mapped[str] = mapped_column(String(100))
    program_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("it_programs.id", ondelete="SET NULL"), nullable=True, index=True
    )
    # Название курса как пришло: по нему программа сопоставляется и заводится.
    course_name: Mapped[str] = mapped_column(String(500))
    stream_number: Mapped[int | None] = mapped_column(Integer, nullable=True)
    last_name: Mapped[str] = mapped_column(String(100), default="")
    first_name: Mapped[str] = mapped_column(String(100), default="")
    middle_name: Mapped[str | None] = mapped_column(String(100), nullable=True)
    phone: Mapped[str | None] = mapped_column(String(20), nullable=True, index=True)
    email: Mapped[str | None] = mapped_column(String(255), nullable=True, index=True)
    # Если источник передал вуз - заявка попадает в процесс по его договору.
    university_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("universities.id", ondelete="SET NULL"), nullable=True, index=True
    )
    contract_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("contracts.id", ondelete="SET NULL"), nullable=True, index=True
    )
    # Дата подачи: из номера заявки, если он её содержит, иначе - дата получения.
    submitted_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)

    program: Mapped[ItProgram | None] = relationship()
    source: Mapped[IntegrationSource | None] = relationship()


class Learner(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """Обучающийся по данным LMS - только то, что нужно для статистики."""

    __tablename__ = "learners"

    source_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("integration_sources.id", ondelete="SET NULL"), nullable=True
    )
    last_name: Mapped[str] = mapped_column(String(100), default="")
    first_name: Mapped[str] = mapped_column(String(100), default="")
    middle_name: Mapped[str | None] = mapped_column(String(100), nullable=True)
    email: Mapped[str | None] = mapped_column(
        String(255), nullable=True, unique=True, index=True
    )
    phone: Mapped[str | None] = mapped_column(String(20), nullable=True, index=True)
    # Обезличиваемые признаки для разрезов статистики.
    gender: Mapped[str | None] = mapped_column(String(1), nullable=True)
    education: Mapped[str | None] = mapped_column(String(255), nullable=True)
    region: Mapped[str | None] = mapped_column(String(255), nullable=True)
