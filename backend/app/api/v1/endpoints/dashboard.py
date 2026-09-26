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
        "Состав ответа зависит от роли: менеджеру - следующие шаги по его "
        "взаимодействиям; руководителю - очередь контроля и нагрузка команды "
        "(и личные шаги, если он сам ведёт взаимодействия); администратору - "
        "технические сводки. Показатели - по области данных сотрудника."
    ),
)
async def read_dashboard(
    session: SessionDep, user: CurrentUserDep, principal: PrincipalDep
) -> DashboardResponse:
    return await dashboard_service.build(session, principal, user)


@router.get(
    "/alerts",
    response_model=list[AlertRead],
    summary="Взаимодействия, по которым требуется действие",
    description=(
        "Правила раздела 7 концепции: этап дольше нормы, взаимодействие "
        "заблокировано, заканчивается срок договора или лицензии, не назначен "
        "ответственный, не загружен обязательный документ, не начато внедрение, "
        "продукт без программы; для тех, кто может их разобрать, - ошибки "
        "обмена, записи на сопоставлении и вузы на проверке."
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
