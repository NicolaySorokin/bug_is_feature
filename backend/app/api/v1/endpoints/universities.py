"""Вузы и их контактные лица.

Новый вуз от менеджера, из Excel или с сайта ждёт проверки, руководитель
или администратор подтверждает его или объединяет с существующим.
Взаимодействие заводится только с подтверждённым вузом. Контакты вуза видны
только в области данных сотрудника.
"""

import re
import uuid
from datetime import UTC, datetime

from fastapi import APIRouter, Query, status
from sqlalchemy import case, func, or_, select, update
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.api.deps import CurrentUserDep, PaginationDep, PrincipalDep, SessionDep
from app.core.errors import ConflictError, ForbiddenError, NotFoundError
from app.core.security import Principal
from app.db.session import mark_changed
from app.enums import OPEN_INTERACTION_STATUSES, Role, UniversityStatus
from app.models.access import UserUniversityAccess
from app.models.integration import ExternalLink, IntegrationMapping
from app.models.interaction import InteractionContact
from app.models.learning import LearningApplication
from app.models.university import University, UniversityContact
from app.models.user import User
from app.models.workflow import WorkflowInstance
from app.schemas.common import Page
from app.schemas.university import (
    DuplicateCandidate,
    UniversityBrief,
    UniversityContactCreate,
    UniversityContactRead,
    UniversityContactUpdate,
    UniversityCreate,
    UniversityDetail,
    UniversityListItem,
    UniversityMerge,
    UniversityUpdate,
)
from app.schemas.user import UserBrief
from app.services import access
from app.services.access import Action

router = APIRouter(prefix="/universities", tags=["universities"])


def normalize_name(name: str) -> str:
    """Название без регистра, кавычек, знаков и лишних пробелов для поиска дублей."""
    value = re.sub(r"[«»\"'`.,()]", " ", name.lower().replace("ё", "е"))
    return re.sub(r"\s+", " ", value).strip()


def _interaction_counts():
    """Подзапрос: сколько у вуза взаимодействий всего и сколько открытых."""
    return (
        select(
            WorkflowInstance.university_id.label("university_id"),
            func.count().label("total"),
            func.count(
                case((WorkflowInstance.status.in_(OPEN_INTERACTION_STATUSES), 1))
            ).label("open"),
        )
        .group_by(WorkflowInstance.university_id)
        .subquery()
    )


async def _get_university(session: AsyncSession, university_id: uuid.UUID) -> University:
    statement = (
        select(University)
        .where(University.id == university_id)
        .options(selectinload(University.contacts), selectinload(University.manager))
        .execution_options(populate_existing=True)
    )
    university = (await session.execute(statement)).scalar_one_or_none()
    if university is None:
        raise NotFoundError("Вуз не найден")
    return university


def _item(university: University, cls: type, **extra) -> UniversityListItem:  # noqa: ANN001
    item = cls.model_validate(university)
    item.display_name = university.short_name or university.name
    item.manager = UserBrief.model_validate(university.manager) if university.manager else None
    for key, value in extra.items():
        setattr(item, key, value)
    return item


async def _detail(
    session: AsyncSession, university: University, principal: Principal, user: User
) -> UniversityDetail:
    counts = (
        await session.execute(
            select(
                func.count(),
                func.count(case((WorkflowInstance.status.in_(OPEN_INTERACTION_STATUSES), 1))),
            ).where(WorkflowInstance.university_id == university.id)
        )
    ).one()
    in_scope = await access.can_see_university(session, university.id, principal, user)
    business = access.has_business_role(principal)
    detail = _item(
        university,
        UniversityDetail,
        interactions_count=counts[0],
        active_interactions_count=counts[1],
        in_scope=in_scope,
    )
    # Контакты это персональные данные: только в области данных и при бизнес-роли.
    detail.contacts = (
        [UniversityContactRead.model_validate(row) for row in university.contacts]
        if in_scope and business
        else []
    )
    return detail


async def _check_manager(session: AsyncSession, manager_id: uuid.UUID | None) -> None:
    if manager_id is None:
        return
    manager = await session.get(User, manager_id)
    if manager is None:
        raise NotFoundError("Сотрудник для назначения не найден")
    if Role.MANAGER not in (manager.roles or []):
        raise ConflictError("Менеджером по умолчанию назначается сотрудник с ролью «Менеджер»")


async def _find_duplicate(
    session: AsyncSession, name: str, inn: str | None, exclude: uuid.UUID | None = None
) -> University | None:
    conditions = [func.lower(University.name) == name.lower()]
    if inn:
        conditions.append(University.inn == inn)
    statement = select(University).where(
        or_(*conditions), University.status != UniversityStatus.ARCHIVED
    )
    if exclude is not None:
        statement = statement.where(University.id != exclude)
    return await session.scalar(statement.limit(1))


@router.get("", response_model=Page[UniversityListItem], summary="Реестр вузов")
async def list_universities(
    session: SessionDep,
    pagination: PaginationDep,
    user: CurrentUserDep,
    principal: PrincipalDep,
    search: str | None = Query(default=None, description="Название, сокращение, город, ИНН"),
    manager_id: uuid.UUID | None = None,
    unassigned: bool = Query(default=False, description="Только без менеджера по умолчанию"),
    university_status: list[UniversityStatus] = Query(
        default=[], alias="status", description="По умолчанию - все, кроме архива"
    ),
) -> Page[UniversityListItem]:
    conditions = []
    if search:
        pattern = f"%{search}%"
        conditions.append(
            or_(
                University.name.ilike(pattern),
                University.short_name.ilike(pattern),
                University.city.ilike(pattern),
                University.inn.ilike(pattern),
            )
        )
    if manager_id is not None:
        conditions.append(University.manager_id == manager_id)
    if unassigned:
        conditions.append(University.manager_id.is_(None))
    if university_status:
        conditions.append(University.status.in_(university_status))
    else:
        conditions.append(University.status != UniversityStatus.ARCHIVED)
    # Справочник целиком видят те, кто его ведёт, менеджер только свои вузы.
    if not access.can(principal, user, Action.MANAGE_UNIVERSITIES):
        scope = access.university_scope(principal, user)
        if scope is not None:
            conditions.append(scope)

    total = (
        await session.scalar(select(func.count()).select_from(University).where(*conditions))
        or 0
    )
    counts = _interaction_counts()
    result = await session.execute(
        select(University, counts.c.total, counts.c.open)
        .outerjoin(counts, counts.c.university_id == University.id)
        .where(*conditions)
        .options(selectinload(University.manager))
        .order_by(func.coalesce(University.short_name, University.name))
        .limit(pagination.limit)
        .offset(pagination.offset)
    )
    scope_ids = await access.scope_university_ids(session, principal, user)
    items = [
        _item(
            university,
            UniversityListItem,
            interactions_count=total_ or 0,
            active_interactions_count=open_ or 0,
            in_scope=scope_ids is None or university.id in scope_ids,
        )
        for university, total_, open_ in result.all()
    ]
    return Page(items=items, total=total, limit=pagination.limit, offset=pagination.offset)


@router.get(
    "/duplicates",
    response_model=list[DuplicateCandidate],
    summary="Возможные дубли вузов",
    description="Одинаковый ИНН, полное или краткое название без учёта регистра и кавычек.",
)
async def list_duplicates(
    session: SessionDep, user: CurrentUserDep, principal: PrincipalDep
) -> list[DuplicateCandidate]:
    access.ensure(
        principal, user, Action.MANAGE_UNIVERSITIES, "Справочник вузов ведёт руководитель"
    )
    universities = list(
        (
            await session.execute(
                select(University).where(University.status != UniversityStatus.ARCHIVED)
            )
        ).scalars()
    )
    found: list[DuplicateCandidate] = []
    seen: set[tuple[uuid.UUID, uuid.UUID]] = set()
    keys: dict[tuple[str, str], University] = {}
    for university in sorted(universities, key=lambda item: item.created_at):
        candidates = [
            ("ИНН совпадает", ("inn", university.inn or "")),
            ("Совпадает название", ("name", normalize_name(university.name))),
            ("Совпадает сокращение", ("short", normalize_name(university.short_name or ""))),
        ]
        for reason, key in candidates:
            if not key[1]:
                continue
            other = keys.get(key)
            if other is None:
                keys[key] = university
                continue
            pair = (other.id, university.id)
            if pair in seen:
                continue
            seen.add(pair)
            found.append(
                DuplicateCandidate(
                    first=UniversityBrief.of(other),
                    second=UniversityBrief.of(university),
                    reason=reason,
                )
            )
    return found


@router.post(
    "",
    response_model=UniversityDetail,
    status_code=status.HTTP_201_CREATED,
    summary="Добавить вуз",
    description=(
        "Руководитель и администратор заводят подтверждённый вуз. Менеджер - "
        "предлагает: вуз попадает на проверку и до подтверждения недоступен "
        "для новых взаимодействий."
    ),
)
async def create_university(
    payload: UniversityCreate,
    session: SessionDep,
    user: CurrentUserDep,
    principal: PrincipalDep,
) -> UniversityDetail:
    manages = access.can(principal, user, Action.MANAGE_UNIVERSITIES)
    if not manages:
        access.ensure(principal, user, Action.PROPOSE_UNIVERSITY, "Недостаточно прав")
        if payload.manager_id not in (None, user.id):
            raise ForbiddenError("Менеджера по умолчанию назначает руководитель")
    await _check_manager(session, payload.manager_id)
    duplicate = await _find_duplicate(session, payload.name, payload.inn)
    if duplicate is not None:
        raise ConflictError(
            f"Вуз «{duplicate.name}» уже есть в справочнике",
            details={"university_id": str(duplicate.id)},
        )
    now = datetime.now(UTC)
    university = University(
        **payload.model_dump(),
        status=UniversityStatus.CONFIRMED if manages else UniversityStatus.PENDING,
        origin="manual",
        confirmed_by_id=user.id if manages else None,
        confirmed_at=now if manages else None,
    )
    session.add(university)
    await session.flush()
    return await _detail(
        session, await _get_university(session, university.id), principal, user
    )


@router.get("/{university_id}", response_model=UniversityDetail, summary="Карточка вуза")
async def read_university(
    university_id: uuid.UUID,
    session: SessionDep,
    user: CurrentUserDep,
    principal: PrincipalDep,
) -> UniversityDetail:
    university = await _get_university(session, university_id)
    if not access.can(principal, user, Action.MANAGE_UNIVERSITIES) and not (
        await access.can_see_university(session, university.id, principal, user)
    ):
        raise ForbiddenError("Вуз не входит в вашу область данных")
    return await _detail(session, university, principal, user)


@router.patch(
    "/{university_id}",
    response_model=UniversityDetail,
    summary="Изменить вуз и менеджера по умолчанию",
    description=(
        "Менеджера по умолчанию (manager_id) назначает, меняет и снимает "
        "руководитель: передайте id сотрудника или null. Он становится "
        "ответственным за новые взаимодействия этого вуза."
    ),
)
async def update_university(
    university_id: uuid.UUID,
    payload: UniversityUpdate,
    session: SessionDep,
    user: CurrentUserDep,
    principal: PrincipalDep,
) -> UniversityDetail:
    access.ensure(
        principal, user, Action.MANAGE_UNIVERSITIES, "Справочник вузов ведёт руководитель"
    )
    university = await _get_university(session, university_id)
    data = payload.model_dump(exclude_unset=True)
    if "manager_id" in data:
        await _check_manager(session, data["manager_id"])
    if data.get("name") or data.get("inn"):
        duplicate = await _find_duplicate(
            session, data.get("name") or university.name, data.get("inn"), university.id
        )
        if duplicate is not None:
            raise ConflictError(
                f"Такой вуз уже есть: «{duplicate.name}» - объедините записи",
                details={"university_id": str(duplicate.id)},
            )
    for field, value in data.items():
        setattr(university, field, value)
    await session.flush()
    return await _detail(
        session, await _get_university(session, university.id), principal, user
    )


async def _set_status(
    session: AsyncSession,
    university_id: uuid.UUID,
    principal: Principal,
    user: User,
    new_status: UniversityStatus,
) -> UniversityDetail:
    access.ensure(
        principal, user, Action.MANAGE_UNIVERSITIES, "Справочник вузов ведёт руководитель"
    )
    university = await _get_university(session, university_id)
    if university.merged_into_id is not None:
        raise ConflictError("Запись объединена с другим вузом - работайте с итоговой")
    university.status = new_status
    if new_status == UniversityStatus.CONFIRMED:
        university.confirmed_by_id = user.id
        university.confirmed_at = datetime.now(UTC)
    await session.flush()
    return await _detail(
        session, await _get_university(session, university.id), principal, user
    )


@router.post(
    "/{university_id}/confirm", response_model=UniversityDetail, summary="Подтвердить вуз"
)
async def confirm_university(
    university_id: uuid.UUID,
    session: SessionDep,
    user: CurrentUserDep,
    principal: PrincipalDep,
) -> UniversityDetail:
    return await _set_status(
        session, university_id, principal, user, UniversityStatus.CONFIRMED
    )


@router.post(
    "/{university_id}/archive",
    response_model=UniversityDetail,
    summary="Перевести вуз в архив",
    description="Начатые взаимодействия продолжаются, новые с вузом не заводятся.",
)
async def archive_university(
    university_id: uuid.UUID,
    session: SessionDep,
    user: CurrentUserDep,
    principal: PrincipalDep,
) -> UniversityDetail:
    return await _set_status(
        session, university_id, principal, user, UniversityStatus.ARCHIVED
    )


@router.post(
    "/{university_id}/merge",
    response_model=UniversityDetail,
    summary="Объединить дубль с итоговой записью",
    description=(
        "Взаимодействия, контакты (одноимённые сливаются), доступы, заявки "
        "и связи с внешними системами переносятся на итоговую запись; дубль "
        "остаётся в архиве со ссылкой на неё."
    ),
)
async def merge_university(
    university_id: uuid.UUID,
    payload: UniversityMerge,
    session: SessionDep,
    user: CurrentUserDep,
    principal: PrincipalDep,
) -> UniversityDetail:
    access.ensure(
        principal, user, Action.MANAGE_UNIVERSITIES, "Справочник вузов ведёт руководитель"
    )
    if payload.target_id == university_id:
        raise ConflictError("Вуз нельзя объединить сам с собой")
    source = await _get_university(session, university_id)
    target = await _get_university(session, payload.target_id)
    if target.status == UniversityStatus.ARCHIVED:
        raise ConflictError("Итоговая запись в архиве - выберите действующую")

    await session.execute(
        update(WorkflowInstance)
        .where(WorkflowInstance.university_id == source.id)
        .values(university_id=target.id)
    )
    await session.execute(
        update(LearningApplication)
        .where(LearningApplication.university_id == source.id)
        .values(university_id=target.id)
    )
    await session.execute(
        update(ExternalLink)
        .where(ExternalLink.entity_type == "university", ExternalLink.entity_id == source.id)
        .values(entity_id=target.id)
    )
    await session.execute(
        update(IntegrationMapping)
        .where(
            IntegrationMapping.entity_type == "university",
            IntegrationMapping.entity_id == source.id,
        )
        .values(entity_id=target.id)
    )
    # Одноимённые контакты у итоговой записи считаем одним человеком.
    by_name = {contact.full_name.lower(): contact for contact in target.contacts}
    for contact in list(source.contacts):
        twin = by_name.get(contact.full_name.lower())
        if twin is None:
            contact.university_id = target.id
            continue
        links = (
            await session.execute(
                select(InteractionContact).where(InteractionContact.contact_id == contact.id)
            )
        ).scalars()
        for link in links:
            exists = await session.get(
                InteractionContact, (link.workflow_instance_id, twin.id)
            )
            if exists is None:
                session.add(
                    InteractionContact(
                        workflow_instance_id=link.workflow_instance_id,
                        contact_id=twin.id,
                        role=link.role,
                        is_primary=link.is_primary,
                    )
                )
        twin.phone = twin.phone or contact.phone
        twin.email = twin.email or contact.email
        twin.position = twin.position or contact.position
        await session.flush()
        await session.delete(contact)
    # Доступы к дублю становятся доступами к итоговой записи.
    grants = (
        await session.execute(
            select(UserUniversityAccess).where(UserUniversityAccess.university_id == source.id)
        )
    ).scalars()
    for grant in grants:
        exists = await session.get(UserUniversityAccess, (grant.user_id, target.id))
        if exists is None:
            session.add(
                UserUniversityAccess(
                    user_id=grant.user_id,
                    university_id=target.id,
                    reason=grant.reason,
                    granted_by_id=grant.granted_by_id,
                    expires_at=grant.expires_at,
                    revoked_at=grant.revoked_at,
                    revoked_by_id=grant.revoked_by_id,
                )
            )
        await session.delete(grant)
    for field in ("short_name", "inn", "city", "website", "description", "manager_id"):
        if getattr(target, field) is None and getattr(source, field) is not None:
            value = getattr(source, field)
            if field == "inn":
                source.inn = None
                await session.flush()
            setattr(target, field, value)
    source.status = UniversityStatus.ARCHIVED
    source.merged_into_id = target.id
    mark_changed(session)
    await session.flush()
    return await _detail(session, await _get_university(session, target.id), principal, user)


@router.delete(
    "/{university_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Удалить ошибочную запись",
    description=(
        "Удаляется только запись без взаимодействий и заявок. Остальные "
        "переводят в архив или объединяют с итоговой."
    ),
)
async def delete_university(
    university_id: uuid.UUID,
    session: SessionDep,
    user: CurrentUserDep,
    principal: PrincipalDep,
) -> None:
    access.ensure(
        principal, user, Action.MANAGE_UNIVERSITIES, "Справочник вузов ведёт руководитель"
    )
    university = await _get_university(session, university_id)
    used = await session.scalar(
        select(func.count())
        .select_from(WorkflowInstance)
        .where(WorkflowInstance.university_id == university.id)
    )
    applications = await session.scalar(
        select(func.count())
        .select_from(LearningApplication)
        .where(LearningApplication.university_id == university.id)
    )
    if used or applications:
        raise ConflictError(
            "У вуза есть взаимодействия или заявки: удалить нельзя - переведите "
            "в архив или объедините с итоговой записью"
        )
    await session.delete(university)


# Контактные лица


async def _contacts_university(
    session: AsyncSession, university_id: uuid.UUID, principal: Principal, user: User
) -> University:
    university = await _get_university(session, university_id)
    access.ensure(
        principal,
        user,
        Action.EDIT_UNIVERSITY_CONTACTS,
        "Контакты вуза правит менеджер или руководитель",
    )
    if not await access.can_see_university(session, university.id, principal, user):
        raise ForbiddenError("Вуз не входит в вашу область данных")
    return university


async def _get_contact(
    session: AsyncSession, university: University, contact_id: uuid.UUID
) -> UniversityContact:
    contact = await session.get(UniversityContact, contact_id)
    if contact is None or contact.university_id != university.id:
        raise NotFoundError("Контактное лицо не найдено у этого вуза")
    return contact


@router.post(
    "/{university_id}/contacts",
    response_model=UniversityContactRead,
    status_code=status.HTTP_201_CREATED,
    summary="Добавить контактное лицо вуза",
)
async def create_contact(
    university_id: uuid.UUID,
    payload: UniversityContactCreate,
    session: SessionDep,
    principal: PrincipalDep,
    user: CurrentUserDep,
) -> UniversityContactRead:
    await _contacts_university(session, university_id, principal, user)
    contact = UniversityContact(university_id=university_id, **payload.model_dump())
    session.add(contact)
    await session.flush()
    return UniversityContactRead.model_validate(contact)


@router.patch(
    "/{university_id}/contacts/{contact_id}",
    response_model=UniversityContactRead,
    summary="Изменить контактное лицо вуза",
)
async def update_contact(
    university_id: uuid.UUID,
    contact_id: uuid.UUID,
    payload: UniversityContactUpdate,
    session: SessionDep,
    principal: PrincipalDep,
    user: CurrentUserDep,
) -> UniversityContactRead:
    university = await _contacts_university(session, university_id, principal, user)
    contact = await _get_contact(session, university, contact_id)
    for field, value in payload.model_dump(exclude_unset=True).items():
        setattr(contact, field, value)
    await session.flush()
    return UniversityContactRead.model_validate(contact)


@router.delete(
    "/{university_id}/contacts/{contact_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Удалить контактное лицо вуза",
    description=(
        "Контакт, назначенный во взаимодействиях, не удаляется - его переводят "
        "в архив (is_active = false): история взаимодействий должна оставаться "
        "читаемой."
    ),
)
async def delete_contact(
    university_id: uuid.UUID,
    contact_id: uuid.UUID,
    session: SessionDep,
    principal: PrincipalDep,
    user: CurrentUserDep,
) -> None:
    university = await _contacts_university(session, university_id, principal, user)
    contact = await _get_contact(session, university, contact_id)
    used = await session.scalar(
        select(func.count())
        .select_from(InteractionContact)
        .where(InteractionContact.contact_id == contact.id)
    )
    if used:
        raise ConflictError(
            "Контакт назначен во взаимодействиях: переведите его в архив вместо удаления"
        )
    await session.delete(contact)
