"""Схемы отчётов.

Отчёт строится по взаимодействиям за период с выбором колонок. Таблица
и диаграммы считаются из одной выборки и приезжают одним ответом.
"""

import uuid
from datetime import date, datetime
from enum import StrEnum

from pydantic import BaseModel, Field, model_validator

from app.enums import (
    ClosureReason,
    ContractStatus,
    InteractionOutcome,
    InteractionSource,
    InteractionStatus,
    ProgramImplementationStatus,
)


class ReportColumn(StrEnum):
    """Колонки отчёта. Первые пять названы в ТЗ."""

    UNIVERSITY = "university"
    DIRECTION = "direction"
    PROGRAM = "program"
    PRODUCT = "product"
    STATUS = "status"  # статус работы с вузом = статус взаимодействия
    MANAGER = "manager"
    INTERACTION = "interaction"
    STAGE = "stage"
    DAYS_ON_STAGE = "days_on_stage"
    OUTCOME = "outcome"
    CLOSURE_REASON = "closure_reason"
    SOURCE = "source"
    IMPLEMENTATION_STATUS = "implementation_status"
    CONTRACT_NUMBER = "contract_number"
    CONTRACT_STATUS = "contract_status"
    SIGNED_AT = "signed_at"
    VALID_TO = "valid_to"
    CREATED_AT = "created_at"
    CLOSED_AT = "closed_at"
    COMMENT = "comment"


COLUMN_TITLES: dict[ReportColumn, str] = {
    ReportColumn.UNIVERSITY: "Вуз",
    ReportColumn.DIRECTION: "ИТ-направление",
    ReportColumn.PROGRAM: "ИТ-программа",
    ReportColumn.PRODUCT: "ИТ-продукт",
    ReportColumn.STATUS: "Статус работы с вузом",
    ReportColumn.MANAGER: "Ответственный",
    ReportColumn.INTERACTION: "Взаимодействие",
    ReportColumn.STAGE: "Этап процесса",
    ReportColumn.DAYS_ON_STAGE: "Дней на этапе",
    ReportColumn.OUTCOME: "Результат",
    ReportColumn.CLOSURE_REASON: "Причина закрытия",
    ReportColumn.SOURCE: "Источник",
    ReportColumn.IMPLEMENTATION_STATUS: "Статус внедрения программы",
    ReportColumn.CONTRACT_NUMBER: "Номер договора",
    ReportColumn.CONTRACT_STATUS: "Статус договора",
    ReportColumn.SIGNED_AT: "Договор подписан",
    ReportColumn.VALID_TO: "Договор действует до",
    ReportColumn.CREATED_AT: "Взаимодействие начато",
    ReportColumn.CLOSED_AT: "Закрыто",
    ReportColumn.COMMENT: "Комментарий",
}

DEFAULT_COLUMNS: list[ReportColumn] = [
    ReportColumn.UNIVERSITY,
    ReportColumn.DIRECTION,
    ReportColumn.PROGRAM,
    ReportColumn.PRODUCT,
    ReportColumn.STATUS,
    ReportColumn.MANAGER,
    ReportColumn.STAGE,
    ReportColumn.CONTRACT_NUMBER,
]


class PeriodBasis(StrEnum):
    """По какой дате считается «за выбранный период»."""

    CREATED = "created"  # взаимодействие начато в периоде
    ACTIVITY = "activity"  # были движения по процессу внутри периода
    SIGNED = "signed"  # договор подписан в периоде, без подписания не входит
    CLOSED = "closed"  # взаимодействие закрыто в периоде


class ChartKey(StrEnum):
    BY_STATUS = "by_status"
    BY_OUTCOME = "by_outcome"
    BY_STAGE = "by_stage"
    BY_DIRECTION = "by_direction"
    BY_PROGRAM = "by_program"
    BY_UNIVERSITY = "by_university"
    BY_MANAGER = "by_manager"
    # Статистика обучения (заявки сайта и обучающиеся LMS).
    APPLICATIONS_BY_PROGRAM = "applications_by_program"
    APPLICATIONS_BY_DIRECTION = "applications_by_direction"
    APPLICATIONS_BY_MONTH = "applications_by_month"
    STREAMS_BY_PROGRAM = "streams_by_program"
    LEARNERS_BY_EDUCATION = "learners_by_education"


class ExportFormat(StrEnum):
    XLSX = "xlsx"
    # xls: двоичный Excel 97 (xlwt), ТЗ называет его отдельно.
    XLS = "xls"
    PDF = "pdf"
    JSON = "json"


class ImageFormat(StrEnum):
    PNG = "png"
    PDF = "pdf"


class ReportFilters(BaseModel):
    """Фильтры выборки. Пустой список означает «без ограничения»."""

    date_from: date | None = None
    date_to: date | None = None
    period_basis: PeriodBasis = PeriodBasis.CREATED
    university_ids: list[uuid.UUID] = Field(default_factory=list)
    direction_ids: list[uuid.UUID] = Field(default_factory=list)
    program_ids: list[uuid.UUID] = Field(default_factory=list)
    product_ids: list[uuid.UUID] = Field(default_factory=list)
    manager_ids: list[uuid.UUID] = Field(default_factory=list)
    stage_ids: list[uuid.UUID] = Field(default_factory=list)
    statuses: list[InteractionStatus] = Field(default_factory=list)
    outcomes: list[InteractionOutcome] = Field(default_factory=list)
    closure_reasons: list[ClosureReason] = Field(default_factory=list)
    sources: list[InteractionSource] = Field(default_factory=list)
    contract_statuses: list[ContractStatus] = Field(default_factory=list)

    @model_validator(mode="after")
    def _check_period(self) -> "ReportFilters":
        if self.date_from and self.date_to and self.date_from > self.date_to:
            raise ValueError("Начало периода позже его окончания")
        return self


class ReportRequest(BaseModel):
    filters: ReportFilters = Field(default_factory=ReportFilters)
    columns: list[ReportColumn] = Field(default_factory=lambda: list(DEFAULT_COLUMNS))
    title: str = "Отчёт по взаимодействию с вузами"

    @model_validator(mode="after")
    def _check_columns(self) -> "ReportRequest":
        if not self.columns:
            raise ValueError("Нужно выбрать хотя бы одну колонку")
        # Порядок сохраняем, дубли убираем.
        self.columns = list(dict.fromkeys(self.columns))
        return self


class ReportRow(BaseModel):
    """Строка отчёта: взаимодействие в разрезе одной ИТ-программы.

    В ячейке «ИТ-продукт» только продукты, связанные с этой программой.
    """

    interaction_id: uuid.UUID
    university_id: uuid.UUID
    university: str
    university_full: str = ""
    interaction: str = ""
    direction: str = ""
    program_id: uuid.UUID | None = None
    program: str = ""
    product_ids: list[uuid.UUID] = Field(default_factory=list)
    product: str = ""
    status: InteractionStatus
    status_label: str = ""
    stage: str = ""
    days_on_stage: int | None = None
    manager_id: uuid.UUID | None = None
    manager: str = ""
    outcome: InteractionOutcome | None = None
    outcome_label: str = ""
    closure_reason: ClosureReason | None = None
    closure_reason_label: str = ""
    source: InteractionSource
    source_label: str = ""
    implementation_status: ProgramImplementationStatus | None = None
    implementation_status_label: str = ""
    contract_number: str = ""
    contract_status: ContractStatus | None = None
    contract_status_label: str = ""
    signed_at: date | None = None
    valid_to: date | None = None
    created_at: date | None = None
    closed_at: date | None = None
    comment: str = ""


class ChartItem(BaseModel):
    label: str
    value: int


class ChartData(BaseModel):
    key: ChartKey
    title: str
    # Что считаем: взаимодействия или строки состава. Подпись нужна, чтобы было
    # видно, из чего построена диаграмма.
    measure: str
    items: list[ChartItem] = Field(default_factory=list)


class ReportTotals(BaseModel):
    rows: int
    interactions: int
    universities: int
    programs: int
    products: int
    contracts: int
    # Период по дате подписания: сколько взаимодействий не вошло, потому что
    # договор ещё не подписан.
    unsigned_excluded: int = 0


class ReportResponse(BaseModel):
    title: str
    generated_at: datetime
    filters: ReportFilters
    columns: list[ReportColumn]
    column_titles: dict[str, str]
    totals: ReportTotals
    rows: list[ReportRow]
    charts: list[ChartData]


class ColumnInfo(BaseModel):
    key: ReportColumn
    title: str
    default: bool
