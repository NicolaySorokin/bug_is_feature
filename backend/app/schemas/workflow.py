"""Схемы рабочего процесса: шаблон, схема, история, переходы."""

import uuid
from datetime import datetime

from pydantic import BaseModel, Field

from app.enums import (
    ClosureReason,
    DocumentType,
    InteractionOutcome,
    InteractionStatus,
    ProductTransferStatus,
    ProgramImplementationStatus,
    StageState,
    WorkflowEventType,
    WorkflowVersionStatus,
)
from app.schemas.common import ORMModel
from app.schemas.user import UserBrief


class StageRead(ORMModel):
    id: uuid.UUID
    code: str
    name: str
    description: str | None
    sort_order: int
    is_initial: bool
    is_optional: bool
    is_final: bool
    # Результат, который даёт финальный этап.
    outcome: InteractionOutcome | None = None
    sla_days: int | None
    # Без этих документов с этапа нельзя уйти вперёд.
    required_documents: list[DocumentType] = []
    # Какие статусы этап ставит программам и продуктам при входе.
    program_status_on_enter: ProgramImplementationStatus | None = None
    product_status_on_enter: ProductTransferStatus | None = None
    layout_x: int | None
    layout_y: int | None


class TransitionRead(ORMModel):
    id: uuid.UUID
    from_stage_id: uuid.UUID
    to_stage_id: uuid.UUID
    name: str | None
    is_backward: bool
    requires_comment: bool


class TemplateRead(ORMModel):
    id: uuid.UUID
    name: str
    description: str | None
    # Активен (enabled) или отключён (disabled): по отключённому новые
    # взаимодействия не заводятся.
    is_active: bool
    active_version_id: uuid.UUID | None = None
    active_version_number: int | None = None


class VersionRead(ORMModel):
    id: uuid.UUID
    template_id: uuid.UUID
    version_number: int
    status: WorkflowVersionStatus
    published_at: datetime | None
    deprecated_at: datetime | None = None
    retired_at: datetime | None = None
    created_at: datetime | None = None
    # Сколько взаимодействий идёт по версии и сколько из них ещё открыты.
    instances_count: int = 0
    open_instances_count: int = 0


class VersionGraph(VersionRead):
    """Версия шаблона целиком: узлы и связи для режима просмотра схемы."""

    stages: list[StageRead] = []
    transitions: list[TransitionRead] = []


class StageInstanceState(BaseModel):
    """Состояние этапа внутри конкретного экземпляра процесса."""

    stage_id: uuid.UUID
    state: StageState


class EventRead(ORMModel):
    id: uuid.UUID
    from_stage_id: uuid.UUID | None
    to_stage_id: uuid.UUID | None
    user_id: uuid.UUID | None
    user: UserBrief | None = None
    event_type: WorkflowEventType
    comment: str | None
    created_at: datetime


class InstanceRead(ORMModel):
    id: uuid.UUID
    university_id: uuid.UUID
    manager_id: uuid.UUID | None
    workflow_version_id: uuid.UUID
    current_stage_id: uuid.UUID | None
    status: InteractionStatus
    outcome: InteractionOutcome | None = None
    closure_reason: ClosureReason | None = None
    blocked_reason: str | None = None
    current_stage_started_at: datetime | None
    started_at: datetime | None
    closed_at: datetime | None


class InstanceView(InstanceRead):
    """Полное представление процесса для вкладки «Процесс» взаимодействия.

    Схема берётся из зафиксированной версии шаблона, состояния этапов
    вычисляются из истории переходов.
    """

    version: VersionGraph
    stage_states: list[StageInstanceState] = []
    available_transitions: list[TransitionRead] = []
    events: list[EventRead] = []


class TransitionRequest(BaseModel):
    """Переход на разрешённый этап."""

    to_stage_id: uuid.UUID
    comment: str | None = None
    # Если переход ведёт на финальный этап без успеха (например, «Отказ»).
    closure_reason: ClosureReason | None = None


class SkipRequest(BaseModel):
    """Пропуск этапа обязательно требует причину. Обязательный этап
    пропускает только руководитель - как исключение с записью в истории."""

    to_stage_id: uuid.UUID
    reason: str = Field(min_length=1)


class BlockRequest(BaseModel):
    reason: str = Field(min_length=1)


# --- Редактирование шаблонов --------------------------------------------------
# Этапы и переходы правятся только в черновике версии. Опубликованную версию
# менять нельзя: по ней идут запущенные процессы (раздел 3.1 концепции).


class StageWrite(BaseModel):
    """Этап схемы. Опознаётся по коду - он же связывает этап с переходами."""

    code: str = Field(min_length=1, max_length=64, pattern=r"^[a-zA-Z0-9_-]+$")
    name: str = Field(min_length=1, max_length=255)
    description: str | None = None
    sort_order: int | None = None
    is_initial: bool = False
    is_optional: bool = False
    is_final: bool = False
    outcome: InteractionOutcome | None = None
    sla_days: int | None = Field(default=None, ge=1)
    required_documents: list[DocumentType] = Field(default_factory=list)
    program_status_on_enter: ProgramImplementationStatus | None = None
    product_status_on_enter: ProductTransferStatus | None = None
    layout_x: int | None = None
    layout_y: int | None = None


class TransitionWrite(BaseModel):
    from_code: str = Field(min_length=1, max_length=64)
    to_code: str = Field(min_length=1, max_length=64)
    name: str | None = Field(default=None, max_length=255)
    is_backward: bool = False
    requires_comment: bool = False


class GraphWrite(BaseModel):
    """Схема целиком: так её сохраняет визуальный редактор."""

    stages: list[StageWrite] = Field(min_length=1)
    transitions: list[TransitionWrite] = Field(default_factory=list)


class TemplateCreate(BaseModel):
    name: str = Field(min_length=1, max_length=255)
    description: str | None = None
    # Можно сразу задать схему, иначе создаётся пустой черновик версии.
    graph: GraphWrite | None = None


class TemplateUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=255)
    description: str | None = None
    is_active: bool | None = None


class VersionCreate(BaseModel):
    """Новая версия шаблона. По умолчанию копирует последнюю существующую."""

    from_version_id: uuid.UUID | None = None
    copy_graph: bool = True


class StageRename(BaseModel):
    """Корректировка названия статуса (этапа).

    Название и описание на ход процесса не влияют, поэтому их можно
    поправить и в опубликованной версии - изменение сразу видно во всех
    взаимодействиях этой версии и в их истории.
    """

    name: str | None = Field(default=None, min_length=1, max_length=255)
    description: str | None = None


class StageLayout(BaseModel):
    stage_id: uuid.UUID
    layout_x: int
    layout_y: int


class LayoutWrite(BaseModel):
    """Координаты узлов. На бизнес-логику не влияют (раздел 3.2)."""

    stages: list[StageLayout] = Field(min_length=1)
