"""Схемы статистики обучения: заявки, обучающиеся, потоки по программам."""

import uuid
from datetime import date, datetime

from pydantic import BaseModel, Field, model_validator

from app.schemas.report import ChartData


class StatisticsFilters(BaseModel):
    """Период считается по дате подачи заявки."""

    date_from: date | None = None
    date_to: date | None = None
    direction_ids: list[uuid.UUID] = Field(default_factory=list)
    program_ids: list[uuid.UUID] = Field(default_factory=list)
    university_ids: list[uuid.UUID] = Field(default_factory=list)

    @model_validator(mode="after")
    def _check_period(self) -> "StatisticsFilters":
        if self.date_from and self.date_to and self.date_from > self.date_to:
            raise ValueError("Начало периода позже его окончания")
        return self


class ProgramStatistics(BaseModel):
    """Строка рейтинга: насколько востребована программа."""

    rank: int
    program_id: uuid.UUID | None
    program: str
    direction: str
    applications: int
    # Сколько обучающихся зачислено на программу по заявкам выборки.
    learners: int
    # Сколько разных потоков набрано по программе.
    streams: int
    # Доля заявок, дошедших до обучения, %.
    conversion: float
    # Взаимодействия с вузами по программе (в работе и завершённые) и их вузы.
    interactions: int
    universities: int
    first_application: datetime | None = None
    last_application: datetime | None = None


class StatisticsTotals(BaseModel):
    applications: int
    # Разные люди: один обучающийся на двух программах - один человек...
    learners: int
    # ...но два зачисления.
    enrollments: int = 0
    streams: int
    programs: int
    directions: int


class StatisticsResponse(BaseModel):
    title: str
    generated_at: datetime
    filters: StatisticsFilters
    totals: StatisticsTotals
    rows: list[ProgramStatistics]
    charts: list[ChartData]


class ApplicationRead(BaseModel):
    id: uuid.UUID
    external_id: str
    source_code: str | None = None
    course_name: str
    program_id: uuid.UUID | None
    stream_number: int | None
    stream_period: str | None = None
    full_name: str
    phone: str | None
    email: str | None
    university_id: uuid.UUID | None
    university_name: str | None = None
    submitted_at: datetime
    # Зачислен ли заявитель на программу этой заявки.
    enrolled: bool = False
