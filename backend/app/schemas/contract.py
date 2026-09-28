"""Схемы договора взаимодействия и типовых шаблонов договоров.

Вуз и ответственный в договоре не дублируются, они берутся из взаимодействия.
"""

import uuid
from datetime import date, datetime

from pydantic import BaseModel, Field, model_validator

from app.enums import ContractClosureReason, ContractStatus
from app.schemas.common import ORMModel
from app.schemas.user import UserBrief


class ContractWrite(BaseModel):
    """Создание и правка договора. Даты и статусы проверяются здесь и в базе."""

    number: str = Field(min_length=1, max_length=100)
    title: str | None = Field(default=None, max_length=500)
    signed_at: date | None = None
    valid_from: date | None = None
    valid_to: date | None = None
    status: ContractStatus = ContractStatus.DRAFT
    closure_reason: ContractClosureReason | None = None
    comment: str | None = None
    signatory_name: str | None = Field(
        default=None, max_length=255, description="Подписант со стороны вуза: ФИО"
    )
    signatory_position: str | None = Field(
        default=None, max_length=255, description="Должность подписанта"
    )
    signatory_basis: str | None = Field(
        default=None,
        max_length=255,
        description="Основание полномочий: «Устава», «доверенности № 12 от 15.01.2026»",
    )

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
    signatory_name: str | None = None
    signatory_position: str | None = None
    signatory_basis: str | None = None
    created_at: datetime | None = None
    updated_at: datetime | None = None


class ContractBrief(BaseModel):
    """Краткое состояние договора для реестра и обзора взаимодействия."""

    id: uuid.UUID
    number: str
    status: ContractStatus
    signed_at: date | None = None
    valid_to: date | None = None
    days_left: int | None = None


# Типовые шаблоны договоров


class ContractTemplateWrite(BaseModel):
    """Шаблон: название и текст с полями {{поле}}.

    Неизвестное поле считается ошибкой, иначе опечатка всплыла бы только
    в готовом договоре.
    """

    name: str = Field(min_length=1, max_length=255)
    body: str = Field(
        min_length=1,
        max_length=50_000,
        description=(
            "Текст договора. Строка «# ...» - заголовок по центру, «## ...» - "
            "заголовок раздела, поля - в двойных фигурных скобках: {{вуз}}."
        ),
    )
    is_active: bool = True


class ContractTemplateRead(ORMModel):
    id: uuid.UUID
    name: str
    body: str
    is_active: bool
    updated_at: datetime | None = None
    updated_by: UserBrief | None = None


class TemplateFieldRead(BaseModel):
    """Поле шаблона: что подставляется вместо ``{{key}}``."""

    key: str
    label: str
    group: str


class ContractDocumentRequest(BaseModel):
    template_id: uuid.UUID
    # К какому событию процесса привязать приложенный файл. Без него файл
    # лежит во взаимодействии без этапа.
    workflow_event_id: uuid.UUID | None = None


class ContractDocumentPreview(BaseModel):
    """Текст договора с подставленными значениями, до формирования файла."""

    template_name: str
    filename: str
    text: str
    # Поля без значения: в документе на их месте остаётся пропуск.
    missing: list[TemplateFieldRead]
