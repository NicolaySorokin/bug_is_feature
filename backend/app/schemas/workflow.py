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
