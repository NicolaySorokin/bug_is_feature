"""Схемы главной страницы: у каждой роли свой набор блоков.

Блокировки, просрочки и «без ответственного» не повторяются в «Требует
внимания», если взаимодействие уже есть в шагах или очереди. Сколько таких,
показывает alerts_in_steps, всего поводов в counters.alerts.
"""

import uuid
from datetime import datetime

from pydantic import BaseModel, Field

from app.enums import (
    AlertKind,
    AlertSeverity,
    DataScope,
    ImportRunStatus,
    ImportType,
    IntegrationRunStatus,
    InteractionStatus,
    WorkflowEventType,
)
from app.schemas.contract import ContractBrief
from app.schemas.interaction import StageSla
from app.schemas.report import ChartData
from app.schemas.university import UniversityBrief
from app.schemas.user import UserBrief


class AlertRead(BaseModel):
    kind: AlertKind
    kind_label: str
    severity: AlertSeverity
    severity_label: str
    message: str
    interaction_id: uuid.UUID | None = None
    interaction_title: str = ""
    contract_number: str = ""
    # Краткое название основное, полное для подсказки.
    university_name: str = ""
    university_full_name: str = ""
    manager_id: uuid.UUID | None = None
    manager_name: str = ""
    # Сколько дней ситуация не меняется. Отрицательное число: срок уже прошёл.
    days: int | None = None
    # Куда вести технические уведомления (очередь сопоставления, вузы на проверке).
    link: str | None = None
    # Ключ проблемы, по нему уведомление отмечается прочитанным.
    key: str
    # Прочитано ли уведомление. Если проблема стала серьёзнее, оно снова новое.
    is_read: bool = False


class AlertsReadRequest(BaseModel):
    """Ключи уведомлений, которые нужно отметить прочитанными."""

    keys: list[str] = Field(min_length=1, max_length=500)


class DashboardCounters(BaseModel):
    """Показатели по области данных сотрудника."""

    open: int = 0  # черновики, в работе и заблокированные
    drafts: int = 0
    in_progress: int = 0
    blocked: int = 0
    overdue: int = 0
    near_deadline: int = 0
    unassigned: int = 0
    completed: int = 0
    cancelled: int = 0
    successful: int = 0
    partial: int = 0
    unsuccessful: int = 0
    universities: int = 0
    # Свои открытые взаимодействия (у руководителя, который ведёт их сам).
    mine_open: int = 0
    alerts: int = 0


class NextStep(BaseModel):
    """Взаимодействие, где ждут действий: статус, этап и срок этапа."""

    interaction_id: uuid.UUID
    title: str | None = None
    university: UniversityBrief
    manager: UserBrief | None = None
    status: InteractionStatus
    blocked_reason: str | None = None
    stage_name: str = ""
    next_actions: list[str] = Field(default_factory=list)
    # Цвет только у срока этапа.
    sla: StageSla | None = None
    contract: ContractBrief | None = None


class ControlItem(NextStep):
    """Строка очереди контроля руководителя: что требует его решения."""

    reason: str  # unassigned / blocked / overdue / stale
    reason_label: str


class RecentChange(BaseModel):
    """Строка ленты «последние изменения»."""

    interaction_id: uuid.UUID
    title: str | None = None
    university: UniversityBrief
    event_type: WorkflowEventType
    event_type_label: str
    stage: str
    user_name: str
    comment: str | None = None
    created_at: datetime


class ManagerLoad(BaseModel):
    """Нагрузка менеджера: по активным взаимодействиям и проблемам."""

    manager_id: uuid.UUID | None
    manager_name: str
    open: int = 0
    in_progress: int = 0
    blocked: int = 0
    overdue: int = 0
    problems: int = 0


class IntegrationStatus(BaseModel):
    code: str
    name: str
    is_enabled: bool
    uses_fixture: bool
    last_status: IntegrationRunStatus | None = None
    last_started_at: datetime | None = None
    last_error: str | None = None


class ImportSummary(BaseModel):
    id: uuid.UUID
    filename: str
    import_type: ImportType
    status: ImportRunStatus
    rows_created: int
    rows_updated: int
    rows_failed: int
    created_at: datetime


class AdminSummary(BaseModel):
    """Главная администратора: интеграции, импорты, пользователи, настройки."""

    users_total: int
    users_active: int
    users_seen_recently: int
    users_by_role: dict[str, int] = Field(default_factory=dict)
    integrations: list[IntegrationStatus] = Field(default_factory=list)
    imports: list[ImportSummary] = Field(default_factory=list)
    settings: dict[str, int] = Field(default_factory=dict)
    mappings_pending: int = 0
    universities_pending: int = 0
    temporary_access: int = 0


class DashboardResponse(BaseModel):
    role: str
    scope: DataScope
    scope_label: str
    generated_at: datetime
    counters: DashboardCounters
    alerts_summary: dict[str, int] = Field(default_factory=dict)
    # Поводы вмешаться, которых нет в шагах и очереди контроля.
    alerts: list[AlertRead] = Field(default_factory=list)
    # Сколько поводов не повторено в alerts, потому что они уже в шагах или очереди.
    alerts_in_steps: int = 0
    recent: list[RecentChange] = Field(default_factory=list)
    charts: list[ChartData] = Field(default_factory=list)
    # Свои взаимодействия, где ждут действий.
    next_steps: list[NextStep] = Field(default_factory=list)
    # Только руководителю: очередь решений и нагрузка команды.
    control_queue: list[ControlItem] = Field(default_factory=list)
    team_load: list[ManagerLoad] = Field(default_factory=list)
    # Только администратору.
    admin: AdminSummary | None = None
