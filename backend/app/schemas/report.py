"""Схемы отчётов.

Требование ТЗ: отчёт за выбранный период по выбранным вузам,
ИТ-направлениям, ИТ-продуктам и ответственным, с выбором колонок
и выгрузкой в XLSX или PDF. Диаграммы строятся из той же выборки,
что и табличная часть (раздел 6.1 концепции), поэтому и строки,
и агрегаты приезжают одним ответом.
"""

import uuid
from datetime import date, datetime
from enum import StrEnum

from pydantic import BaseModel, Field, model_validator

from app.enums import ContractStatus, ImplementationStatus


class ReportColumn(StrEnum):
    """Колонки отчёта. Первые пять - те, что перечислены в ТЗ."""

    UNIVERSITY = "university"
    DIRECTION = "direction"
    PROGRAM = "program"
    PRODUCT = "product"
    CONTRACT_STATUS = "contract_status"
    MANAGER = "manager"
    CONTRACT_NUMBER = "contract_number"
    STAGE = "stage"
    DAYS_ON_STAGE = "days_on_stage"
    IMPLEMENTATION_STATUS = "implementation_status"
    SIGNED_AT = "signed_at"
    VALID_TO = "valid_to"
    COMMENT = "comment"


COLUMN_TITLES: dict[ReportColumn, str] = {
    ReportColumn.UNIVERSITY: "Вуз",
    ReportColumn.DIRECTION: "ИТ-направление",
    ReportColumn.PROGRAM: "ИТ-программа",
    ReportColumn.PRODUCT: "ИТ-продукт",
    ReportColumn.CONTRACT_STATUS: "Статус работы с вузом",
    ReportColumn.MANAGER: "Ответственный",
    ReportColumn.CONTRACT_NUMBER: "Номер договора",
    ReportColumn.STAGE: "Этап процесса",
    ReportColumn.DAYS_ON_STAGE: "Дней на этапе",
    ReportColumn.IMPLEMENTATION_STATUS: "Статус внедрения",
    ReportColumn.SIGNED_AT: "Подписан",
    ReportColumn.VALID_TO: "Действует до",
    ReportColumn.COMMENT: "Комментарий",
}

DEFAULT_COLUMNS: list[ReportColumn] = [
    ReportColumn.UNIVERSITY,
    ReportColumn.DIRECTION,
    ReportColumn.PROGRAM,
    ReportColumn.PRODUCT,
    ReportColumn.CONTRACT_NUMBER,
    ReportColumn.CONTRACT_STATUS,
    ReportColumn.STAGE,
    ReportColumn.MANAGER,
]


class PeriodBasis(StrEnum):
    """По какой дате считается «за выбранный период»."""

    SIGNED = "signed"  # дата подписания, а если её нет - дата заведения
    CREATED = "created"  # дата появления договора в системе
    ACTIVITY = "activity"  # были движения по процессу внутри периода


class ChartKey(StrEnum):
    BY_STATUS = "by_status"
    BY_STAGE = "by_stage"
    BY_DIRECTION = "by_direction"
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
    # xls - двоичный формат Excel 97 (xlwt): ТЗ называет его отдельно.
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
    period_basis: PeriodBasis = PeriodBasis.SIGNED
    university_ids: list[uuid.UUID] = Field(default_factory=list)
    direction_ids: list[uuid.UUID] = Field(default_factory=list)
    program_ids: list[uuid.UUID] = Field(default_factory=list)
    product_ids: list[uuid.UUID] = Field(default_factory=list)
    manager_ids: list[uuid.UUID] = Field(default_factory=list)
    stage_ids: list[uuid.UUID] = Field(default_factory=list)
    statuses: list[ContractStatus] = Field(default_factory=list)

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
    """Строка отчёта: договор в разрезе одной ИТ-программы.

    Продукты договора собраны в одну ячейку: если размножить строки ещё
    и по продуктам, договор посчитается несколько раз и диаграммы соврут.
    """

    contract_id: uuid.UUID
    university_id: uuid.UUID
    university: str
    direction: str = ""
    program: str = ""
    product: str = ""
    contract_number: str = ""
    contract_status: ContractStatus
    contract_status_label: str = ""
    stage: str = ""
    days_on_stage: int | None = None
    manager: str = ""
    implementation_status: ImplementationStatus | None = None
    implementation_status_label: str = ""
    signed_at: date | None = None
    valid_to: date | None = None
    comment: str = ""


class ChartItem(BaseModel):
    label: str
    value: int


class ChartData(BaseModel):
    key: ChartKey
    title: str
    # Что считаем: договоры или строки состава. Подписываем явно, чтобы
    # по диаграмме было видно, из чего она построена.
    measure: str
    items: list[ChartItem] = Field(default_factory=list)


class ReportTotals(BaseModel):
    rows: int
    contracts: int
    universities: int
    programs: int
    products: int


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
