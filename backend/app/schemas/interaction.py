"""Схемы взаимодействия с вузом.

Взаимодействие - основной объект работы (раздел 8 «Решений по бизнес-
модели»): вуз, ответственный, программы и продукты, ход по workflow;
договор - необязательный блок внутри.

Обзор взаимодействия показывает три независимых вещи (пункт 33 перечня
исправлений): статус взаимодействия, текущий этап со следующим действием
и срок (SLA) текущего этапа. Цвет срока относится только к сроку.
"""

import uuid
from datetime import datetime
from enum import StrEnum

from pydantic import BaseModel, Field, model_validator

from app.enums import (
    ClosureReason,
    InteractionOutcome,
    InteractionSource,
    InteractionStatus,
    ProductTransferStatus,
    ProgramImplementationStatus,
)
from app.schemas.catalog import ItProductRead, ItProgramRead
from app.schemas.common import ORMModel
from app.schemas.contract import ContractBrief, ContractRead
from app.schemas.license import LicenseRead
from app.schemas.university import UniversityBrief, UniversityContactRead
from app.schemas.user import UserBrief


class SlaState(StrEnum):
    """Срок этапа: в норме, использовано не меньше 75 % или превышен."""

    OK = "ok"
    WARNING = "warning"
    OVERDUE = "overdue"


class StageSla(BaseModel):
    """Срок текущего этапа: фактические и нормативные дни."""

    days_on_stage: int
    sla_days: int
    days_left: int  # отрицательное - просрочено на столько дней
    used_percent: int
    state: SlaState


class StageSummary(BaseModel):
    """Текущий этап и что с ним делать дальше."""

    stage_id: uuid.UUID
    stage_name: str
    # Названия разрешённых переходов вперёд: «следующее действие».
    next_actions: list[str] = []
    sla: StageSla | None = None


class InteractionListItem(BaseModel):
    """Строка реестра: вуз, статус, этап, ответственный, результат; договор -
    необязательные поля (до подписания его может не быть)."""

    id: uuid.UUID
    title: str | None
    university: UniversityBrief
    manager: UserBrief | None
    status: InteractionStatus
    outcome: InteractionOutcome | None
    closure_reason: ClosureReason | None
    source: InteractionSource
    stage: StageSummary | None
    blocked_reason: str | None = None
    contract: ContractBrief | None = None
    programs: list[str] = []
    template_name: str = ""
    created_at: datetime
    updated_at: datetime
    started_at: datetime | None
    closed_at: datetime | None


class ProgramProductLinkRead(BaseModel):
    program_link_id: uuid.UUID
    product_link_id: uuid.UUID
    is_exception: bool
    exception_comment: str | None = None


class InteractionProgramRead(ORMModel):
    id: uuid.UUID
    program_id: uuid.UUID
    implementation_status: ProgramImplementationStatus
    program: ItProgramRead | None = None


class InteractionProductRead(ORMModel):
    id: uuid.UUID
    product_id: uuid.UUID
    transfer_status: ProductTransferStatus
    product: ItProductRead | None = None
    licenses: list[LicenseRead] = []


class InteractionContactRead(ORMModel):
    """Ответственный от вуза по этому взаимодействию."""

    contact_id: uuid.UUID
    role: str | None
    is_primary: bool
    contact: UniversityContactRead


class InteractionDetail(InteractionListItem):
    comment: str | None = None
    template_id: uuid.UUID
    workflow_version_id: uuid.UUID
    version_number: int
    blocked_at: datetime | None = None
    closure_comment: str | None = None
    closed_by: UserBrief | None = None
    created_by: UserBrief | None = None
    contract_detail: ContractRead | None = None
    program_links: list[InteractionProgramRead] = []
    product_links: list[InteractionProductRead] = []
    links: list[ProgramProductLinkRead] = []
    contacts: list[InteractionContactRead] = []
    # Типы обязательных документов текущего этапа, которых ещё нет.
    missing_documents: list[str] = []
    # Что может сделать текущий пользователь - чтобы не показывать лишних кнопок.
    can_edit: bool = False
    can_assign: bool = False
    can_cancel: bool = False
    can_delete: bool = False


class InteractionCreate(BaseModel):
    university_id: uuid.UUID
    title: str | None = Field(default=None, max_length=500)
    comment: str | None = None
    # Ответственный: менеджер - всегда он сам; руководитель назначает менеджера.
    manager_id: uuid.UUID | None = None
    # Шаблон процесса; не задан - основной. Версию выбирает система.
    template_id: uuid.UUID | None = None
    program_ids: list[uuid.UUID] = []
    # Сразу запустить процесс, а не оставить черновиком.
    start: bool = False


class InteractionUpdate(BaseModel):
    title: str | None = Field(default=None, max_length=500)
    comment: str | None = None
    manager_id: uuid.UUID | None = None


class CancelRequest(BaseModel):
    reason: ClosureReason
    comment: str | None = Field(default=None, max_length=2000)

    @model_validator(mode="after")
    def _other_needs_comment(self) -> "CancelRequest":
        if self.reason is ClosureReason.OTHER and not (self.comment or "").strip():
            raise ValueError("Для причины «Иное» нужен комментарий")
        return self


class ProgramAdd(BaseModel):
    program_id: uuid.UUID
    implementation_status: ProgramImplementationStatus = (
        ProgramImplementationStatus.NOT_STARTED
    )


class ProgramStatusUpdate(BaseModel):
    implementation_status: ProgramImplementationStatus
    # Ручное изменение статуса в обход этапа - с комментарием, он уходит в историю.
    comment: str | None = Field(default=None, max_length=2000)


class ProductAdd(BaseModel):
    """Продукт добавляется сразу с программами взаимодействия, где он нужен."""

    product_id: uuid.UUID
    program_link_ids: list[uuid.UUID] = Field(min_length=1)
    transfer_status: ProductTransferStatus = ProductTransferStatus.NOT_STARTED
    # Для программ, с которыми продукт не связан в справочнике, - обязательно.
    exception_comment: str | None = Field(default=None, max_length=2000)


class ProductStatusUpdate(BaseModel):
    transfer_status: ProductTransferStatus
    comment: str | None = Field(default=None, max_length=2000)


class ProgramProductLinkWrite(BaseModel):
    program_link_id: uuid.UUID
    product_link_id: uuid.UUID
    exception_comment: str | None = Field(default=None, max_length=2000)


class InteractionContactWrite(BaseModel):
    contact_id: uuid.UUID
    role: str | None = Field(default=None, max_length=255)
    is_primary: bool = False
