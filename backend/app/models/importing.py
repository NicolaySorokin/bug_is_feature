"""Импорт каталогов из XLS/XLSX.

Раздел 6.2 концепции: загрузка, предпросмотр, сопоставление колонок,
проверка, импорт и итог. Файл живёт на диске до конца импорта, сопоставление
колонок хранится в самой записи о загрузке - это позволяет показать
предпросмотр, а импорт выполнить отдельным вызовом.
"""

import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import DateTime, ForeignKey, Integer, String, Text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, CreatedAtMixin, UUIDPrimaryKeyMixin
from app.enums import ImportRunStatus
from app.models.user import User


class ImportRun(UUIDPrimaryKeyMixin, CreatedAtMixin, Base):
    __tablename__ = "import_runs"

    uploaded_by: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    filename: Mapped[str] = mapped_column(String(500))
    storage_path: Mapped[str] = mapped_column(String(1000))
    import_type: Mapped[str] = mapped_column(String(64))
    status: Mapped[str] = mapped_column(
        String(32),
        default=ImportRunStatus.UPLOADED,
        server_default=ImportRunStatus.UPLOADED,
    )
    # Сопоставление «поле системы -> заголовок колонки файла».
    mapping: Mapped[dict[str, Any] | None] = mapped_column(JSONB, nullable=True)
    rows_total: Mapped[int] = mapped_column(Integer, default=0, server_default="0")
    rows_created: Mapped[int] = mapped_column(Integer, default=0, server_default="0")
    rows_updated: Mapped[int] = mapped_column(Integer, default=0, server_default="0")
    rows_failed: Mapped[int] = mapped_column(Integer, default=0, server_default="0")
    finished_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    user: Mapped[User | None] = relationship()
    errors: Mapped[list["ImportRowError"]] = relationship(
        back_populates="run",
        cascade="all, delete-orphan",
        order_by="ImportRowError.row_number",
    )


class ImportRowError(UUIDPrimaryKeyMixin, Base):
    """Ошибка по конкретной строке файла.

    Имя класса отличается от имени таблицы намеренно: ``ImportError`` -
    встроенное исключение Python, перекрывать его нельзя.
    """

    __tablename__ = "import_errors"

    import_run_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("import_runs.id", ondelete="CASCADE"), index=True
    )
    row_number: Mapped[int] = mapped_column(Integer)
    field_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    message: Mapped[str] = mapped_column(Text)

    run: Mapped[ImportRun] = relationship(back_populates="errors")
