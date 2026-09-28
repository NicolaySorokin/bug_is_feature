"""Схемы главной страницы.

Раздел 2.1 концепции и пункты 32-35 перечня исправлений: у каждой роли своя
главная.

* Менеджер - «Следующие шаги» по своим взаимодействиям: отдельно статус
  взаимодействия, текущий этап со следующим действием и срок этапа;
  сначала заблокированные, затем просроченные, приближающиеся к сроку
  и остальные.
* Руководитель - состояние команды и очередь решений: взаимодействия без
  ответственного, заблокированные, просроченные; нагрузка менеджеров по
  активным взаимодействиям, просрочкам, блокировкам и проблемам. Если он
  сам ведёт взаимодействия - личные шаги отдельным блоком.
* Администратор - технические сводки: обмен, загрузки, пользователи,
  очереди проверки.

Показатели не дублируют друг друга: заблокированные видны в очереди
контроля и в показателе, но не повторяются ещё и в «Требует внимания».
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
    # Краткое название - основное; полное - для подсказки.
    university_name: str = ""
    university_full_name: str = ""
    manager_id: uuid.UUID | None = None
    manager_name: str = ""
    # Сколько дней ситуация не меняется; отрицательное - срок уже прошёл.
    days: int | None = None
    # Куда вести технические уведомления (очередь сопоставления, вузы на проверке).
    link: str | None = None
    # Устойчивый ключ проблемы - по нему уведомление отмечается прочитанным.
    key: str
    # Прочитал ли сотрудник уведомление (колокольчик); ухудшение - снова новое.
    is_read: bool = False


class AlertsReadRequest(BaseModel):
    """Какие уведомления отметить прочитанными - ключи из списка уведомлений."""

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
    """Взаимодействие, где ждут действий: три независимых блока."""

    interaction_id: uuid.UUID
    title: str | None = None
    university: UniversityBrief
    manager: UserBrief | None = None
    # 1. Статус взаимодействия (и причина блокировки).
    status: InteractionStatus
    blocked_reason: str | None = None
    # 2. Текущий этап и следующее действие.
    stage_name: str = ""
    next_actions: list[str] = Field(default_factory=list)
    # 3. Срок текущего этапа - цвет только у него.
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
    # «по вашим взаимодействиям», «по данным команды», «по всем взаимодействиям».
    scope_label: str
    generated_at: datetime
    counters: DashboardCounters
    alerts_summary: dict[str, int] = Field(default_factory=dict)
    # Поводы вмешаться, которых нет в шагах и очереди контроля.
    alerts: list[AlertRead] = Field(default_factory=list)
    recent: list[RecentChange] = Field(default_factory=list)
    charts: list[ChartData] = Field(default_factory=list)
    # Свои взаимодействия, где ждут действий (менеджер; руководитель-менеджер).
    next_steps: list[NextStep] = Field(default_factory=list)
    # Только руководителю: очередь решений и нагрузка команды.
    control_queue: list[ControlItem] = Field(default_factory=list)
    team_load: list[ManagerLoad] = Field(default_factory=list)
    # Только администратору.
    admin: AdminSummary | None = None
