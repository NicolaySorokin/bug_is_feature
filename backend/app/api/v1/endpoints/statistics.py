"""Статистика обучения: востребованность ИТ-программ.

Сводные цифры без персональных данных видят менеджеры и руководители.
Список заявок с ФИО и контактами только по праву «Персональные данные студентов».
"""

import uuid
from datetime import date

from fastapi import APIRouter, Query, Response
from sqlalchemy import Date, cast, exists, func, or_, select
from sqlalchemy.orm import selectinload

from app.api.deps import CurrentUserDep, PaginationDep, SessionDep, require_action
from app.core.errors import AppError, ErrorCode
from app.models.catalog import ItProgram
from app.models.learning import Enrollment, LearningApplication, LearningStream
from app.models.university import University
from app.schemas.common import Page
from app.schemas.report import ChartKey, ExportFormat, ImageFormat
from app.schemas.statistics import ApplicationRead, StatisticsFilters, StatisticsResponse
from app.services import statistics
from app.services.access import Action
from app.services.export import charts as chart_export
from app.services.export import runner
from app.services.export import table as table_export

router = APIRouter(
    prefix="/statistics",
    tags=["statistics"],
    dependencies=[
        require_action(
            Action.VIEW_STATISTICS, "Статистика обучения - менеджеру и руководителю"
        )
    ],
)

CONTENT_TYPES = {
    ExportFormat.XLSX: (
        "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        "xlsx",
    ),
    ExportFormat.XLS: ("application/vnd.ms-excel", "xls"),
    ExportFormat.PDF: ("application/pdf", "pdf"),
    ExportFormat.JSON: ("application/json", "json"),
}
HEADERS = [
    "Место",
    "ИТ-программа",
    "ИТ-направление",
    "Заявки",
    "Обучающиеся",
    "Потоки",
    "Дошли до обучения, %",
    "Взаимодействия",
    "Вузы",
]


def _period(filters: StatisticsFilters) -> str:
    def fmt(value: date | None) -> str:
        return value.strftime("%d.%m.%Y") if value else "…"

    if filters.date_from is None and filters.date_to is None:
        return "за всё время"
    return f"с {fmt(filters.date_from)} по {fmt(filters.date_to)}"


def statistics_table(data: StatisticsResponse) -> table_export.Table:
    totals = data.totals
    return table_export.Table(
        title=data.title,
        meta=[
            f"Период подачи заявок: {_period(data.filters)}",
            f"Построено: {data.generated_at.strftime('%d.%m.%Y %H:%M')} · "
            f"заявок: {totals.applications} · обучающихся: {totals.learners} · "
            f"потоков: {totals.streams} · программ: {totals.programs}",
        ],
        headers=HEADERS,
        rows=[
            [
                row.rank,
                row.program,
                row.direction,
                row.applications,
                row.learners,
                row.streams,
                row.conversion,
                row.interactions,
                row.universities,
            ]
            for row in data.rows
        ],
        charts=data.charts,
    )


def _render(data: StatisticsResponse, export_format: ExportFormat) -> bytes:
    if export_format is ExportFormat.JSON:
        return data.model_dump_json(indent=2).encode("utf-8")
    table = statistics_table(data)
    if export_format is ExportFormat.PDF:
        return table_export.to_pdf(table, column_widths=[4, 22, 16, 7, 9, 7, 9, 7, 6])
    if export_format is ExportFormat.XLS:
        return table_export.to_xls(table)
    return table_export.to_xlsx(table)


@router.post(
    "/programs",
    response_model=StatisticsResponse,
    summary="Рейтинг ИТ-программ по востребованности",
    description=(
        "Заявки с сайта, обучающиеся из LMS и число потоков по каждой программе "
        "за период подачи заявок. Таблица и диаграммы - из одной выборки."
    ),
)
async def program_statistics(
    payload: StatisticsFilters, session: SessionDep, _: CurrentUserDep
) -> StatisticsResponse:
    return await statistics.build(session, payload)


@router.post(
    "/export",
    summary="Выгрузить статистику файлом",
    description="Форматы: xlsx, xls, pdf, json.",
    response_class=Response,
    responses={200: {"content": {"application/octet-stream": {}}}},
)
async def export_statistics(
    payload: StatisticsFilters,
    session: SessionDep,
    _: CurrentUserDep,
    export_format: ExportFormat = Query(default=ExportFormat.XLSX, alias="format"),
) -> Response:
    data = await statistics.build(session, payload)
    media_type, extension = CONTENT_TYPES[export_format]
    try:
        content = await runner.run(_render, data, export_format)
    except AppError:
        raise
    except Exception as exc:  # noqa: BLE001 (наружу уходит понятный код ошибки)
        raise AppError(
            f"Не удалось сформировать выгрузку: {exc}", code=ErrorCode.REPORT_FAILED
        ) from exc
    stamp = data.generated_at.strftime("%Y%m%d-%H%M")
    return Response(
        content=content,
        media_type=media_type,
        headers={
            "Content-Disposition": f'attachment; filename="statistics-{stamp}.{extension}"'
        },
    )


@router.post(
    "/chart",
    summary="Диаграмма статистики отдельным файлом",
    description="Форматы изображения: png и pdf.",
    response_class=Response,
    responses={200: {"content": {"image/png": {}, "application/pdf": {}}}},
)
async def statistics_chart(
    payload: StatisticsFilters,
    session: SessionDep,
    _: CurrentUserDep,
    key: ChartKey = Query(default=ChartKey.APPLICATIONS_BY_PROGRAM),
    image_format: ImageFormat = Query(default=ImageFormat.PNG, alias="format"),
) -> Response:
    data = await statistics.build(session, payload)
    chart = next((item for item in data.charts if item.key is key), None)
    if chart is None:
        raise AppError("Такой диаграммы в статистике нет", code=ErrorCode.REPORT_FAILED)
    render = chart_export.to_png if image_format is ImageFormat.PNG else chart_export.to_pdf
    content = await runner.run(render, chart)
    media_type = "image/png" if image_format is ImageFormat.PNG else "application/pdf"
    stamp = data.generated_at.strftime("%Y%m%d-%H%M")
    return Response(
        content=content,
        media_type=media_type,
        headers={
            "Content-Disposition": (
                f'attachment; filename="chart-{key.value}-{stamp}.{image_format.value}"'
            )
        },
    )


def _enrolled_condition():  # noqa: ANN202 (выражение SQLAlchemy)
    """Заявитель зачислен на программу этой заявки."""
    return exists().where(Enrollment.application_id == LearningApplication.id)


@router.get(
    "/applications",
    response_model=Page[ApplicationRead],
    dependencies=[
        require_action(
            Action.VIEW_PERSONAL_DATA,
            "Заявки с персональными данными - по праву «Персональные данные студентов»",
        )
    ],
    summary="Заявки на обучение",
    description=(
        "Заявки с персональными данными заявителей - только по отдельному праву. "
        "Заявка студента используется в статистике и взаимодействие с вузом не создаёт."
    ),
)
async def list_applications(
    session: SessionDep,
    pagination: PaginationDep,
    program_id: uuid.UUID | None = None,
    university_id: uuid.UUID | None = None,
    stream: int | None = Query(default=None, ge=0),
    enrolled: bool | None = Query(default=None, description="Зачислен на программу"),
    search: str | None = Query(default=None, description="Номер заявки, ФИО, почта, курс"),
    date_from: date | None = None,
    date_to: date | None = None,
) -> Page[ApplicationRead]:
    application = LearningApplication
    conditions = []
    if program_id is not None:
        conditions.append(application.program_id == program_id)
    if university_id is not None:
        conditions.append(application.university_id == university_id)
    if stream is not None:
        conditions.append(application.stream_number == stream)
    if enrolled is not None:
        condition = _enrolled_condition()
        conditions.append(condition if enrolled else ~condition)
    if date_from is not None:
        conditions.append(cast(application.submitted_at, Date) >= date_from)
    if date_to is not None:
        conditions.append(cast(application.submitted_at, Date) <= date_to)
    if search:
        pattern = f"%{search}%"
        conditions.append(
            or_(
                application.external_id.ilike(pattern),
                application.last_name.ilike(pattern),
                application.first_name.ilike(pattern),
                application.email.ilike(pattern),
                application.course_name.ilike(pattern),
            )
        )

    total = await session.scalar(
        select(func.count()).select_from(application).where(*conditions)
    )
    result = await session.execute(
        select(
            application,
            _enrolled_condition().label("enrolled"),
            func.coalesce(University.short_name, University.name),
            LearningStream.period,
        )
        .outerjoin(University, University.id == application.university_id)
        .outerjoin(LearningStream, LearningStream.id == application.stream_id)
        .where(*conditions)
        .options(selectinload(application.source), selectinload(application.program))
        .order_by(application.submitted_at.desc(), application.external_id)
        .limit(pagination.limit)
        .offset(pagination.offset)
    )
    items = [
        ApplicationRead(
            id=item.id,
            external_id=item.external_id,
            source_code=item.source.code if item.source else None,
            course_name=item.program.name if item.program else item.course_name,
            program_id=item.program_id,
            stream_number=item.stream_number,
            stream_period=period,
            full_name=" ".join(
                part for part in (item.last_name, item.first_name, item.middle_name) if part
            ),
            phone=item.phone,
            email=item.email,
            university_id=item.university_id,
            university_name=university_name,
            submitted_at=item.submitted_at,
            enrolled=bool(is_enrolled),
        )
        for item, is_enrolled, university_name, period in result.all()
    ]
    return Page(
        items=items, total=total or 0, limit=pagination.limit, offset=pagination.offset
    )


@router.get(
    "/programs/{program_id}/streams",
    summary="Потоки программы: заявки и зачисленные по каждому",
)
async def program_streams(
    program_id: uuid.UUID, session: SessionDep, _: CurrentUserDep
) -> list[dict[str, int | str | None]]:
    if await session.get(ItProgram, program_id) is None:
        raise AppError("Программа не найдена", code=ErrorCode.NOT_FOUND, status_code=404)
    application = LearningApplication
    learners = (
        select(func.count(func.distinct(Enrollment.learner_id)))
        .where(Enrollment.stream_id == LearningStream.id)
        .scalar_subquery()
    )
    result = await session.execute(
        select(
            LearningStream.number,
            LearningStream.period,
            func.count(application.id),
            learners,
        )
        .join(application, application.stream_id == LearningStream.id)
        .where(LearningStream.program_id == program_id)
        .group_by(LearningStream.id)
        .order_by(LearningStream.period, LearningStream.number.nullslast())
    )
    return [
        {
            "stream": number,
            "period": period,
            "applications": count,
            "learners": int(enrolled or 0),
        }
        for number, period, count, enrolled in result.all()
    ]
