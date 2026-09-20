"""Главная страница и контроль проблемных процессов."""

from fastapi import APIRouter, Query

from app.api.deps import CurrentUserDep, PrincipalDep, SessionDep
from app.enums import AlertKind
from app.schemas.dashboard import AlertRead, DashboardResponse
from app.services import alerts as alerts_service
from app.services import dashboard as dashboard_service

router = APIRouter(prefix="/dashboard", tags=["dashboard"])


@router.get(
    "",
    response_model=DashboardResponse,
    summary="Сводка на главной",
    description=(
        "Состав ответа зависит от роли: менеджеру - его договоры и ближайшие "
        "действия, руководителю и администратору - вдобавок нагрузка команды."
    ),
)
async def read_dashboard(
    session: SessionDep, user: CurrentUserDep, principal: PrincipalDep
) -> DashboardResponse:
    return await dashboard_service.build(session, principal, user)


@router.get(
    "/alerts",
    response_model=list[AlertRead],
    summary="Договоры, по которым требуется действие",
    description=(
        "Правила раздела 7 концепции: этап долго не менялся, процесс заблокирован, "
        "заканчивается срок договора или лицензии, не назначен ответственный, "
        "не загружены документы, не начато внедрение, ошибка синхронизации."
    ),
)
async def read_alerts(
    session: SessionDep,
    user: CurrentUserDep,
    principal: PrincipalDep,
    kind: list[AlertKind] | None = Query(default=None, description="Отбор по видам"),
    limit: int = Query(default=100, ge=1, le=500),
) -> list[AlertRead]:
    found = await alerts_service.collect(
        session, principal, user, kinds=set(kind) if kind else None, limit=limit
    )
    return [dashboard_service.to_alert_read(alert) for alert in found]
