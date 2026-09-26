"""Статистика обучения: востребованность ИТ-программ.

ТЗ, раздел «Актуальность»: программы ранжируются по востребованности,
которая видна по статистике - заявкам на обучение, числу обучающихся
и параллельных потоков. Источники - заявки студентов с сайта и данные LMS
(app.services.integrations). Заявка студента - только статистика: она не
создаёт взаимодействие с вузом.

Пункты 14-15 перечня исправлений:

* обучающийся считается по явному зачислению (``enrollments``) на эту
  программу - один человек на двух программах учтётся в каждой, но не
  дважды в одной;
* поток - отдельная запись со стабильным ключом и периодом: одинаковые
  номера разных наборов не сливаются.

Таблица рейтинга и диаграммы считаются по одной выборке заявок - как
и в отчётах по взаимодействиям, цифры в них совпадают.
"""

from __future__ import annotations

import uuid
from collections import Counter, defaultdict
from dataclasses import dataclass
from datetime import UTC, datetime

from sqlalchemy import Date, cast, distinct, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.enums import InteractionStatus
from app.models.catalog import ItDirection, ItProgram
from app.models.interaction import InteractionProgram
from app.models.learning import Enrollment, Learner, LearningApplication
from app.models.workflow import WorkflowInstance
from app.schemas.report import ChartData, ChartItem, ChartKey
from app.schemas.statistics import (
    ProgramStatistics,
    StatisticsFilters,
    StatisticsResponse,
    StatisticsTotals,
)
from app.services import cache
from app.services.reports import top_items

NO_DIRECTION = "Направление не указано"
MONTHS = (
    "янв", "фев", "мар", "апр", "май", "июн", "июл", "авг", "сен", "окт", "ноя", "дек",
)  # fmt: skip

# Взаимодействие «работает» с программой: оно в работе или успешно закрыто.
WORKING = (
    InteractionStatus.IN_PROGRESS,
    InteractionStatus.BLOCKED,
    InteractionStatus.COMPLETED,
)


def apply_filters(statement, filters: StatisticsFilters):  # noqa: ANN001, ANN201
    application = LearningApplication
    if filters.date_from is not None:
        statement = statement.where(cast(application.submitted_at, Date) >= filters.date_from)
    if filters.date_to is not None:
        statement = statement.where(cast(application.submitted_at, Date) <= filters.date_to)
    if filters.program_ids:
        statement = statement.where(application.program_id.in_(filters.program_ids))
    if filters.direction_ids:
        statement = statement.where(ItProgram.direction_id.in_(filters.direction_ids))
    if filters.university_ids:
        statement = statement.where(application.university_id.in_(filters.university_ids))
    return statement


@dataclass(slots=True)
class _Row:
    id: uuid.UUID
    program_id: uuid.UUID | None
    program: str
    direction: str
    stream_id: uuid.UUID | None
    submitted_at: datetime


async def _rows(session: AsyncSession, filters: StatisticsFilters) -> list[_Row]:
    application = LearningApplication
    statement = (
        select(
            application.id,
            application.program_id,
            func.coalesce(ItProgram.name, application.course_name),
            ItDirection.name,
            application.stream_id,
            application.submitted_at,
        )
        .outerjoin(ItProgram, ItProgram.id == application.program_id)
        .outerjoin(ItDirection, ItDirection.id == ItProgram.direction_id)
    )
    result = await session.execute(apply_filters(statement, filters))
    return [
        _Row(
            id=row_id,
            program_id=program_id,
            program=program,
            direction=direction or NO_DIRECTION,
            stream_id=stream_id,
            submitted_at=submitted_at,
        )
        for row_id, program_id, program, direction, stream_id, submitted_at in result.all()
    ]


async def _enrolled(
    session: AsyncSession, application_ids: list[uuid.UUID]
) -> dict[uuid.UUID, set[uuid.UUID]]:
    """Программа -> обучающиеся, зачисленные по заявкам выборки."""
    if not application_ids:
        return {}
    result = await session.execute(
        select(Enrollment.program_id, Enrollment.learner_id).where(
            Enrollment.application_id.in_(application_ids)
        )
    )
    enrolled: dict[uuid.UUID, set[uuid.UUID]] = defaultdict(set)
    for program_id, learner_id in result.all():
        enrolled[program_id].add(learner_id)
    return enrolled


async def _coverage(session: AsyncSession) -> dict[uuid.UUID, tuple[int, int]]:
    """Сколько взаимодействий в работе (или успешно закрытых) и вузов с каждой программой."""
    result = await session.execute(
        select(
            InteractionProgram.program_id,
            func.count(distinct(WorkflowInstance.id)),
            func.count(distinct(WorkflowInstance.university_id)),
        )
        .join(WorkflowInstance, WorkflowInstance.id == InteractionProgram.workflow_instance_id)
        .where(WorkflowInstance.status.in_(WORKING))
        .group_by(InteractionProgram.program_id)
    )
    return {
        program_id: (interactions, universities)
        for program_id, interactions, universities in result
    }


async def _education_counts(
    session: AsyncSession, learner_ids: set[uuid.UUID]
) -> Counter[str]:
    """Обучающиеся из выборки по уровню образования (из анкет LMS)."""
    if not learner_ids:
        return Counter()
    result = await session.execute(
        select(Learner.education).where(Learner.id.in_(learner_ids))
    )
    return Counter(education or "Не указано" for education in result.scalars())


def _month_label(moment: datetime) -> str:
    return f"{MONTHS[moment.month - 1]} {moment.year}"


async def _build(session: AsyncSession, filters: StatisticsFilters) -> StatisticsResponse:
    rows = await _rows(session, filters)
    coverage = await _coverage(session)
    enrolled = await _enrolled(session, [row.id for row in rows])

    groups: dict[tuple[uuid.UUID | None, str], list[_Row]] = defaultdict(list)
    for row in rows:
        groups[(row.program_id, row.program)].append(row)

    stats: list[ProgramStatistics] = []
    all_learners: set[uuid.UUID] = set()
    for (program_id, program), items in groups.items():
        applications = len(items)
        learners = enrolled.get(program_id, set()) if program_id else set()
        all_learners |= learners
        interactions_count, universities = (
            coverage.get(program_id, (0, 0)) if program_id else (0, 0)
        )
        stats.append(
            ProgramStatistics(
                rank=0,
                program_id=program_id,
                program=program,
                direction=items[0].direction,
                applications=applications,
                learners=len(learners),
                streams=len({item.stream_id for item in items if item.stream_id is not None}),
                conversion=round(100 * len(learners) / applications, 1)
                if applications
                else 0.0,
                interactions=interactions_count,
                universities=universities,
                first_application=min(item.submitted_at for item in items),
                last_application=max(item.submitted_at for item in items),
            )
        )
    # Рейтинг востребованности: заявки, затем обучающиеся, затем потоки.
    stats.sort(
        key=lambda item: (-item.applications, -item.learners, -item.streams, item.program)
    )
    for index, item in enumerate(stats, start=1):
        item.rank = index

    by_direction = Counter(row.direction for row in rows)
    months: Counter[tuple[int, int]] = Counter(
        (row.submitted_at.year, row.submitted_at.month) for row in rows
    )
    education = await _education_counts(session, all_learners)

    charts = [
        ChartData(
            key=ChartKey.APPLICATIONS_BY_PROGRAM,
            title="Заявки по ИТ-программам",
            measure="заявок",
            items=top_items(Counter({item.program: item.applications for item in stats})),
        ),
        ChartData(
            key=ChartKey.APPLICATIONS_BY_DIRECTION,
            title="Заявки по ИТ-направлениям",
            measure="заявок",
            items=top_items(by_direction),
        ),
        ChartData(
            key=ChartKey.APPLICATIONS_BY_MONTH,
            title="Заявки по месяцам",
            measure="заявок",
            items=[
                ChartItem(label=_month_label(datetime(year, month, 1)), value=value)
                for (year, month), value in sorted(months.items())
            ],
        ),
        ChartData(
            key=ChartKey.STREAMS_BY_PROGRAM,
            title="Потоки по ИТ-программам",
            measure="потоков",
            items=top_items(
                Counter({item.program: item.streams for item in stats if item.streams})
            ),
        ),
        ChartData(
            key=ChartKey.LEARNERS_BY_EDUCATION,
            title="Обучающиеся по уровню образования",
            measure="обучающихся",
            items=top_items(education),
        ),
    ]

    return StatisticsResponse(
        title="Статистика обучения по ИТ-программам",
        generated_at=datetime.now(UTC),
        filters=filters,
        totals=StatisticsTotals(
            applications=len(rows),
            learners=len(all_learners),
            enrollments=sum(item.learners for item in stats),
            streams=len({row.stream_id for row in rows if row.stream_id is not None}),
            programs=len(stats),
            directions=len(by_direction),
        ),
        rows=stats,
        charts=charts,
    )


async def build(session: AsyncSession, filters: StatisticsFilters) -> StatisticsResponse:
    key = cache.make_key("statistics", filters.model_dump(mode="json"))
    return await cache.cached(session, key, lambda: _build(session, filters))
