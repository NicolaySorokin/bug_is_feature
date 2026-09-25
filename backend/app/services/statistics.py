"""Статистика обучения: востребованность ИТ-программ.

ТЗ, раздел «Актуальность»: программы ранжируются по востребованности,
которая видна по статистике - заявкам на обучение, числу обучающихся
и параллельных потоков. Источники - заявки с сайта и анкеты LMS
(app.services.integrations).

Заявитель считается обучающимся, если его анкета нашлась в LMS по почте
или телефону. Таблица рейтинга и диаграммы считаются по одной выборке
заявок - как и в отчётах по договорам, цифры в них совпадают.
"""

from __future__ import annotations

import uuid
from collections import Counter, defaultdict
from dataclasses import dataclass
from datetime import UTC, datetime

from sqlalchemy import Date, and_, case, cast, distinct, exists, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.enums import ContractStatus
from app.models.catalog import ItDirection, ItProgram
from app.models.contract import Contract, ContractProgram
from app.models.learning import Learner, LearningApplication
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


def enrolled_condition():
    """Заявитель нашёлся среди обучающихся LMS - по почте или телефону."""
    application = LearningApplication
    return exists().where(
        or_(
            and_(application.email.is_not(None), Learner.email == application.email),
            and_(application.phone.is_not(None), Learner.phone == application.phone),
        )
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
    program_id: uuid.UUID | None
    program: str
    direction: str
    stream: int | None
    submitted_at: datetime
    enrolled: bool
    email: str | None
    phone: str | None


async def _rows(session: AsyncSession, filters: StatisticsFilters) -> list[_Row]:
    application = LearningApplication
    statement = (
        select(
            application.program_id,
            func.coalesce(ItProgram.name, application.course_name),
            ItDirection.name,
            application.stream_number,
            application.submitted_at,
            case((enrolled_condition(), True), else_=False),
            application.email,
            application.phone,
        )
        .outerjoin(ItProgram, ItProgram.id == application.program_id)
        .outerjoin(ItDirection, ItDirection.id == ItProgram.direction_id)
    )
    result = await session.execute(apply_filters(statement, filters))
    return [
        _Row(
            program_id=program_id,
            program=program,
            direction=direction or NO_DIRECTION,
            stream=stream,
            submitted_at=submitted_at,
            enrolled=bool(enrolled),
            email=email,
            phone=phone,
        )
        for program_id, program, direction, stream, submitted_at, enrolled, email, phone in (
            result.all()
        )
    ]


async def _contract_coverage(session: AsyncSession) -> dict[uuid.UUID, tuple[int, int]]:
    """Сколько действующих договоров и вузов с каждой программой."""
    result = await session.execute(
        select(
            ContractProgram.program_id,
            func.count(distinct(Contract.id)),
            func.count(distinct(Contract.university_id)),
        )
        .join(Contract, Contract.id == ContractProgram.contract_id)
        .where(Contract.status == ContractStatus.ACTIVE)
        .group_by(ContractProgram.program_id)
    )
    return {
        program_id: (contracts, universities) for program_id, contracts, universities in result
    }


async def _education_counts(session: AsyncSession, rows: list[_Row]) -> Counter[str]:
    """Обучающиеся из выборки по уровню образования (из анкет LMS)."""
    emails = {row.email for row in rows if row.enrolled and row.email}
    phones = {row.phone for row in rows if row.enrolled and row.phone}
    if not emails and not phones:
        return Counter()
    result = await session.execute(
        select(Learner.education).where(
            or_(Learner.email.in_(emails or {""}), Learner.phone.in_(phones or {""}))
        )
    )
    return Counter(education or "Не указано" for education in result.scalars())


def _month_label(moment: datetime) -> str:
    return f"{MONTHS[moment.month - 1]} {moment.year}"


async def _build(session: AsyncSession, filters: StatisticsFilters) -> StatisticsResponse:
    rows = await _rows(session, filters)
    coverage = await _contract_coverage(session)

    groups: dict[tuple[uuid.UUID | None, str], list[_Row]] = defaultdict(list)
    for row in rows:
        groups[(row.program_id, row.program)].append(row)

    stats: list[ProgramStatistics] = []
    for (program_id, program), items in groups.items():
        applications = len(items)
        learners = sum(1 for item in items if item.enrolled)
        contracts, universities = coverage.get(program_id, (0, 0)) if program_id else (0, 0)
        stats.append(
            ProgramStatistics(
                rank=0,
                program_id=program_id,
                program=program,
                direction=items[0].direction,
                applications=applications,
                learners=learners,
                streams=len({item.stream for item in items if item.stream is not None}),
                conversion=round(100 * learners / applications, 1) if applications else 0.0,
                contracts=contracts,
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
    education = await _education_counts(session, rows)

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
            learners=sum(item.learners for item in stats),
            streams=sum(item.streams for item in stats),
            programs=len(stats),
            directions=len(by_direction),
        ),
        rows=stats,
        charts=charts,
    )


async def build(session: AsyncSession, filters: StatisticsFilters) -> StatisticsResponse:
    key = cache.make_key("statistics", filters.model_dump(mode="json"))
    return await cache.cached(session, key, lambda: _build(session, filters))
