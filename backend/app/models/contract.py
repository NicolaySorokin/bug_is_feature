"""Договор и лицензии.

Договор - самостоятельная юридическая сущность, которая появляется в ходе
взаимодействия с вузом (раздел 5 «Решений по бизнес-модели»). У одного
взаимодействия в MVP не больше одного договора - это держит уникальный
ключ ``workflow_instance_id``. Вуз и ответственный в договоре не
дублируются: они берутся из взаимодействия.

Подписант договора со стороны вуза хранится в самом договоре: подписывает
не обязательно ответственный за взаимодействие контакт, а, например,
проректор по доверенности. Это данные на момент подписания - они не
меняются, если контакт потом сменит должность.

Лицензия относится к конкретному продукту взаимодействия и оформляется
по договору.

Типовой шаблон договора ведёт руководитель: текст с полями ``{{...}}``,
которые при формировании документа заполняются из взаимодействия, вуза
и договора (app/services/contract_documents.py).
"""

import uuid
from datetime import date
from typing import TYPE_CHECKING

from sqlalchemy import CheckConstraint, Date, ForeignKey, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, TimestampMixin, UUIDPrimaryKeyMixin
from app.enums import ContractStatus, LicenseStatus
from app.models.user import User

if TYPE_CHECKING:
    from app.models.interaction import InteractionProduct
    from app.models.workflow import WorkflowInstance


class Contract(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "contracts"
    __table_args__ = (
        CheckConstraint(
            "valid_from IS NULL OR valid_to IS NULL OR valid_from <= valid_to",
            name="valid_period",
        ),
        CheckConstraint(
            "signed_at IS NULL OR valid_to IS NULL OR signed_at <= valid_to",
            name="signed_before_end",
        ),
    )

    workflow_instance_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("workflow_instances.id", ondelete="RESTRICT"), unique=True
    )
    number: Mapped[str] = mapped_column(String(100), index=True)
    title: Mapped[str | None] = mapped_column(String(500), nullable=True)
    signed_at: Mapped[date | None] = mapped_column(Date, nullable=True)
    valid_from: Mapped[date | None] = mapped_column(Date, nullable=True)
    valid_to: Mapped[date | None] = mapped_column(Date, nullable=True)
    status: Mapped[str] = mapped_column(
        String(32), default=ContractStatus.DRAFT, server_default=ContractStatus.DRAFT
    )
    # Для закрытого договора: исполнен, истёк срок или расторгнут.
    closure_reason: Mapped[str | None] = mapped_column(String(32), nullable=True)
    comment: Mapped[str | None] = mapped_column(Text, nullable=True)
    # Кто подписывает со стороны вуза - не то же самое, что ответственный.
    signatory_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    signatory_position: Mapped[str | None] = mapped_column(String(255), nullable=True)
    # На основании чего действует: «Устава», «доверенности № 12 от 15.01.2026».
    signatory_basis: Mapped[str | None] = mapped_column(String(255), nullable=True)

    interaction: Mapped["WorkflowInstance"] = relationship(back_populates="contract")
    licenses: Mapped[list["License"]] = relationship(
        back_populates="contract", cascade="all, delete-orphan"
    )


class License(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """Лицензия на продукт взаимодействия, оформленная по договору."""

    __tablename__ = "licenses"
    __table_args__ = (
        CheckConstraint(
            "valid_from IS NULL OR valid_to IS NULL OR valid_from <= valid_to",
            name="valid_period",
        ),
    )

    contract_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("contracts.id", ondelete="CASCADE"), index=True
    )
    interaction_product_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("interaction_products.id", ondelete="CASCADE"), index=True
    )
    number: Mapped[str | None] = mapped_column(String(100), nullable=True)
    seats: Mapped[int | None] = mapped_column(nullable=True)
    signed_at: Mapped[date | None] = mapped_column(Date, nullable=True)
    valid_from: Mapped[date | None] = mapped_column(Date, nullable=True)
    valid_to: Mapped[date | None] = mapped_column(Date, nullable=True)
    status: Mapped[str] = mapped_column(
        String(32), default=LicenseStatus.ACTIVE, server_default=LicenseStatus.ACTIVE
    )

    contract: Mapped[Contract] = relationship(back_populates="licenses")
    interaction_product: Mapped["InteractionProduct"] = relationship(back_populates="licenses")


class ContractTemplate(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """Типовой шаблон договора: текст с полями ``{{...}}``.

    Шаблон не удаляется, а выключается - как записи справочников: по нему
    уже могли сформировать документы.
    """

    __tablename__ = "contract_templates"

    name: Mapped[str] = mapped_column(String(255))
    body: Mapped[str] = mapped_column(Text)
    is_active: Mapped[bool] = mapped_column(default=True, server_default="true")
    updated_by_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )

    updated_by: Mapped[User | None] = relationship()
