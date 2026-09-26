"""Схемы договора взаимодействия.

Договор необязателен: до подписания его может не быть или он черновик
внутри взаимодействия. Вуз и ответственный в договоре не дублируются -
они берутся из взаимодействия.
"""

import uuid
from datetime import date, datetime

from pydantic import BaseModel, Field, model_validator

from app.enums import ContractClosureReason, ContractStatus
from app.schemas.common import ORMModel


class ContractWrite(BaseModel):
    """Создание и правка договора. Проверки дат и статусов - здесь и в базе."""

    number: str = Field(min_length=1, max_length=100)
    title: str | None = Field(default=None, max_length=500)
    signed_at: date | None = None
    valid_from: date | None = None
    valid_to: date | None = None
    status: ContractStatus = ContractStatus.DRAFT
    closure_reason: ContractClosureReason | None = None
    comment: str | None = None

    @model_validator(mode="after")
    def _rules(self) -> "ContractWrite":
        if self.valid_from and self.valid_to and self.valid_from > self.valid_to:
            raise ValueError("Срок действия начинается позже, чем заканчивается")
        if self.signed_at and self.valid_to and self.signed_at > self.valid_to:
            raise ValueError("Дата подписания позже окончания срока действия")
        signed_statuses = (
            ContractStatus.ACTIVE,
            ContractStatus.SUSPENDED,
            ContractStatus.CLOSED,
        )
        if self.status in signed_statuses and self.signed_at is None:
            raise ValueError("Действующий договор должен быть подписан: укажите дату")
        if self.status == ContractStatus.CLOSED and self.closure_reason is None:
            raise ValueError(
                "Для закрытого договора укажите причину: исполнен, истёк или расторгнут"
            )
        if self.status != ContractStatus.CLOSED:
            self.closure_reason = None
        if self.status == ContractStatus.CANCELLED and self.signed_at is not None:
            raise ValueError("Подписанный договор не отменяют, а закрывают (расторгнут)")
        return self


class ContractRead(ORMModel):
    id: uuid.UUID
    workflow_instance_id: uuid.UUID
    number: str
    title: str | None
    signed_at: date | None
    valid_from: date | None
    valid_to: date | None
    status: ContractStatus
    closure_reason: ContractClosureReason | None
    comment: str | None
    created_at: datetime | None = None
    updated_at: datetime | None = None


class ContractBrief(BaseModel):
    """Краткое состояние договора - для реестра и обзора взаимодействия."""

    id: uuid.UUID
    number: str
    status: ContractStatus
    signed_at: date | None = None
    valid_to: date | None = None
    days_left: int | None = None
