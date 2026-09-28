"""Главная страница и контроль проблемных процессов."""

from fastapi import APIRouter, Query, status

from app.api.deps import CurrentUserDep, PrincipalDep, SessionDep
from app.enums import AlertKind
from app.schemas.dashboard import AlertRead, AlertsReadRequest, DashboardResponse
from app.services import alert_marks
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
        "обмена, записи на сопоставлении и вузы на проверке. is_read - "
        "сотрудник отметил уведомление прочитанным; стало серьёзнее - снова новое."
    ),
)
async def read_alerts(
    session: SessionDep,
    user: CurrentUserDep,
    principal: PrincipalDep,
    kind: list[AlertKind] | None = Query(default=None, description="Отбор по видам"),
    limit: int = Query(default=100, ge=1, le=500),
) -> list[AlertRead]:
    everything = await alerts_service.collect_all(session, principal, user)
    # Отметки сверяются с полным списком: отметки о решённых проблемах удаляются.
    read = await alert_marks.read_keys(session, user, everything, prune=True)
    found = [alert for alert in everything if not kind or alert.kind in kind][:limit]
    return [dashboard_service.to_alert_read(alert, read) for alert in found]


@router.post(
    "/alerts/read",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Отметить уведомления прочитанными",
    description=(
        "Ключи - поле key из списка уведомлений. Уведомление снимается со счётчика "
        "колокольчика, а проблема остаётся в «Требует внимания» на главной, пока "
        "её не решат."
    ),
)
async def mark_alerts_read(
    payload: AlertsReadRequest,
    session: SessionDep,
    user: CurrentUserDep,
    principal: PrincipalDep,
) -> None:
    everything = await alerts_service.collect_all(session, principal, user)
    await alert_marks.mark_read(session, user, everything, set(payload.keys))


@router.post(
    "/alerts/read-all",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Отметить прочитанными все уведомления",
)
async def mark_all_alerts_read(
    session: SessionDep, user: CurrentUserDep, principal: PrincipalDep
) -> None:
    everything = await alerts_service.collect_all(session, principal, user)
    await alert_marks.mark_read(session, user, everything)
