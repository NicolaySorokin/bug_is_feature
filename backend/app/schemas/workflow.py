"""Схемы рабочего процесса: шаблон, схема, история, переходы."""

import uuid
from datetime import datetime

from pydantic import BaseModel, Field

from app.enums import StageState, WorkflowEventType, WorkflowInstanceStatus
from app.schemas.common import ORMModel


class StageRead(ORMModel):
    id: uuid.UUID
    code: str
    name: str
    description: str | None
    sort_order: int
    is_optional: bool
    is_final: bool
    sla_days: int | None
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
    is_active: bool


class VersionRead(ORMModel):
    id: uuid.UUID
    template_id: uuid.UUID
    version_number: int
    published_at: datetime | None


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
    event_type: WorkflowEventType
    comment: str | None
    created_at: datetime


class InstanceRead(ORMModel):
    id: uuid.UUID
    contract_id: uuid.UUID
    workflow_version_id: uuid.UUID
    current_stage_id: uuid.UUID | None
    status: WorkflowInstanceStatus
    current_stage_started_at: datetime | None
    started_at: datetime | None
    completed_at: datetime | None


class InstanceView(InstanceRead):
    """Полное представление процесса для карточки договора.

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


class SkipRequest(BaseModel):
    """Пропуск необязательного этапа обязательно требует причину."""

    to_stage_id: uuid.UUID
    reason: str = Field(min_length=1)


class BlockRequest(BaseModel):
    reason: str = Field(min_length=1)


class StartRequest(BaseModel):
    template_id: uuid.UUID
    version_id: uuid.UUID | None = None


# --- Редактирование шаблонов --------------------------------------------------
# Этапы и переходы правятся только в черновике версии. Опубликованную версию
# менять нельзя: по ней идут запущенные процессы (раздел 3.1 концепции).


class StageWrite(BaseModel):
    """Этап схемы. Опознаётся по коду - он же связывает этап с переходами."""

    code: str = Field(min_length=1, max_length=64, pattern=r"^[a-zA-Z0-9_-]+$")
    name: str = Field(min_length=1, max_length=255)
    description: str | None = None
    sort_order: int | None = None
    is_optional: bool = False
    is_final: bool = False
    sla_days: int | None = Field(default=None, ge=1)
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


class StageLayout(BaseModel):
    stage_id: uuid.UUID
    layout_x: int
    layout_y: int


class LayoutWrite(BaseModel):
    """Координаты узлов. На бизнес-логику не влияют (раздел 3.2)."""

    stages: list[StageLayout] = Field(min_length=1)
