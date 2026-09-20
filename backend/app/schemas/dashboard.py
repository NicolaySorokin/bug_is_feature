"""Схемы главной страницы: сводка, проблемные процессы, последние изменения."""

import uuid
from datetime import datetime

from pydantic import BaseModel, Field

from app.enums import AlertKind, AlertSeverity, WorkflowEventType
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


class DashboardResponse(BaseModel):
    role: str
    generated_at: datetime
    counters: DashboardCounters
    alerts_summary: dict[str, int] = Field(default_factory=dict)
    alerts: list[AlertRead] = Field(default_factory=list)
    recent: list[RecentChange] = Field(default_factory=list)
    charts: list[ChartData] = Field(default_factory=list)
    # Только для руководителя и администратора.
    manager_load: list[ManagerLoad] = Field(default_factory=list)
