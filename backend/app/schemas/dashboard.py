"""Схемы главной страницы: сводка, проблемные процессы, последние изменения."""

import uuid
from datetime import datetime

from pydantic import BaseModel, Field

from app.enums import (
    AlertKind,
    AlertSeverity,
    ImportRunStatus,
    ImportType,
    IntegrationRunStatus,
    WorkflowEventType,
    WorkflowInstanceStatus,
)
from app.schemas.report import ChartData


class AlertRead(BaseModel):
    kind: AlertKind
    kind_label: str
    severity: AlertSeverity
    severity_label: str
    message: str
    contract_id: uuid.UUID | None = None
    contract_number: str = ""
    university_name: str = ""
    manager_id: uuid.UUID | None = None
    manager_name: str = ""
    # Сколько дней ситуация не меняется; отрицательное - срок уже прошёл.
    days: int | None = None


class DashboardCounters(BaseModel):
    contracts: int
    contracts_active: int
    contracts_draft: int
    universities: int
    my_contracts: int
    processes_in_progress: int
    processes_blocked: int
    processes_completed: int
    alerts: int


class RecentChange(BaseModel):
    """Строка ленты «последние изменения»."""

    contract_id: uuid.UUID
    contract_number: str
    university_name: str
    event_type: WorkflowEventType
    event_type_label: str
    stage: str
    user_name: str
    comment: str | None = None
    created_at: datetime


class ManagerLoad(BaseModel):
    manager_id: uuid.UUID | None
    manager_name: str
    contracts: int
    problems: int
    active: int = 0
    blocked: int = 0


class NextAction(BaseModel):
    """Ближайшее действие менеджера: договор, где пора двигать процесс."""

    contract_id: uuid.UUID
    contract_number: str
    university_name: str
    stage_name: str
    process_status: WorkflowInstanceStatus
    days_on_stage: int | None = None
    sla_days: int | None = None
    overdue: bool = False
    # Куда процесс можно перевести с текущего этапа.
    actions: list[str] = Field(default_factory=list)


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


class DashboardResponse(BaseModel):
    role: str
    generated_at: datetime
    counters: DashboardCounters
    alerts_summary: dict[str, int] = Field(default_factory=dict)
    alerts: list[AlertRead] = Field(default_factory=list)
    recent: list[RecentChange] = Field(default_factory=list)
    charts: list[ChartData] = Field(default_factory=list)
    # Свои договоры, где пора двигать процесс.
    next_actions: list[NextAction] = Field(default_factory=list)
    # Только для руководителя и администратора.
    manager_load: list[ManagerLoad] = Field(default_factory=list)
    # Только для администратора.
    admin: AdminSummary | None = None
