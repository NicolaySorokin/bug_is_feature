"""Взаимодействие с вузом: реестр, карточка, состав и договор.

Правила состава (раздел 13 «Решений по бизнес-модели»):

* сначала во взаимодействие добавляется программа, затем для неё
  выбираются продукты; продукт без связи хотя бы с одной программой
  взаимодействия не существует;
* по умолчанию продукты берутся из справочного соответствия программ
  и продуктов; связь вне справочника - исключение руководителя
  с комментарием;
* один продукт в нескольких программах - одна строка продукта и несколько
  связей, без дублей;
* программу со связанными продуктами удалить нельзя, пока связи не
  перенесены или не удалены; продукт, у которого не осталось программ,
  удаляется из состава вместе со связью;
* выбирать можно только активные программы и продукты: архивные
  сохраняются в существующих взаимодействиях, но недоступны для нового
  выбора.
"""

from __future__ import annotations

import uuid
from datetime import UTC, date, datetime

from sqlalchemy import Select, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core.errors import AppError, ConflictError, ErrorCode, ForbiddenError, NotFoundError
from app.enums import InteractionStatus
from app.models.catalog import ItProduct, ItProgram, ProgramProduct
from app.models.content import Attachment, Comment
from app.models.contract import Contract, License
from app.models.interaction import (
    InteractionContact,
    InteractionProduct,
    InteractionProgram,
    InteractionProgramProduct,
)
from app.models.university import University
from app.models.user import User
from app.models.workflow import (
    WorkflowEvent,
    WorkflowInstance,
    WorkflowStage,
    WorkflowTransition,
    WorkflowVersion,
)
from app.schemas.contract import ContractBrief, ContractRead
from app.schemas.interaction import (
    InteractionContactRead,
    InteractionDetail,
    InteractionListItem,
    InteractionProductRead,
    InteractionProgramRead,
    ProgramProductLinkRead,
    SlaState,
    StageSla,
    StageSummary,
)
from app.schemas.university import UniversityBrief
from app.schemas.user import UserBrief

# Доля израсходованного срока, с которой срок этапа «на исходе».
SLA_WARNING_SHARE = 0.75


def stage_sla(
    started_at: datetime | None, sla_days: int | None, default_sla: int
) -> StageSla | None:
    """Срок этапа: сколько дней прошло, сколько положено и что с цветом."""
    if started_at is None:
        return None
    days = max((datetime.now(UTC) - started_at).days, 0)
    norm = sla_days or default_sla
    used = days / norm if norm else 0
    state = (
        SlaState.OVERDUE
        if days > norm
        else SlaState.WARNING
        if used >= SLA_WARNING_SHARE
        else SlaState.OK
    )
    return StageSla(
        days_on_stage=days,
        sla_days=norm,
        days_left=norm - days,
        used_percent=round(used * 100),
        state=state,
    )


def next_actions(
    transitions: list[WorkflowTransition], stage_names: dict[uuid.UUID, str]
) -> list[str]:
    """Разрешённые шаги вперёд с текущего этапа - «что делать дальше»."""
    return [
        transition.name or stage_names.get(transition.to_stage_id, "")
        for transition in transitions
        if not transition.is_backward
    ]


def contract_brief(contract: Contract | None) -> ContractBrief | None:
    if contract is None:
        return None
    return ContractBrief(
        id=contract.id,
        number=contract.number,
        status=contract.status,
        signed_at=contract.signed_at,
        valid_to=contract.valid_to,
        days_left=(contract.valid_to - date.today()).days if contract.valid_to else None,
    )


def _brief_user(user: User | None) -> UserBrief | None:
    return UserBrief.model_validate(user) if user is not None else None


def list_options() -> list:
    return [
        selectinload(WorkflowInstance.university),
        selectinload(WorkflowInstance.manager),
        selectinload(WorkflowInstance.current_stage),
        selectinload(WorkflowInstance.contract),
        selectinload(WorkflowInstance.version).selectinload(WorkflowVersion.template),
        selectinload(WorkflowInstance.programs).selectinload(InteractionProgram.program),
    ]


async def transitions_by_stage(
    session: AsyncSession, stage_ids: set[uuid.UUID]
) -> dict[uuid.UUID, list[str]]:
    """Следующие действия для набора текущих этапов - одним запросом."""
    if not stage_ids:
        return {}
    rows = await session.execute(
        select(WorkflowTransition)
        .where(WorkflowTransition.from_stage_id.in_(stage_ids))
        .options(selectinload(WorkflowTransition.to_stage))
    )
    result: dict[uuid.UUID, list[str]] = {}
    for transition in rows.scalars():
        if transition.is_backward:
            continue
        result.setdefault(transition.from_stage_id, []).append(
            transition.name or transition.to_stage.name
        )
    return result


def stage_summary(
    instance: WorkflowInstance, actions: dict[uuid.UUID, list[str]], default_sla: int
) -> StageSummary | None:
    stage = instance.current_stage
    if stage is None:
        return None
    open_ = instance.status in (InteractionStatus.IN_PROGRESS, InteractionStatus.BLOCKED)
    return StageSummary(
        stage_id=stage.id,
        stage_name=stage.name,
        next_actions=actions.get(stage.id, []) if open_ else [],
        sla=stage_sla(instance.current_stage_started_at, stage.sla_days, default_sla)
        if open_
        else None,
    )


def list_item(
    instance: WorkflowInstance, actions: dict[uuid.UUID, list[str]], default_sla: int
) -> InteractionListItem:
    version = instance.version
    return InteractionListItem(
        id=instance.id,
        title=instance.title,
        university=UniversityBrief.of(instance.university),
        manager=_brief_user(instance.manager),
        status=instance.status,
        outcome=instance.outcome,
        closure_reason=instance.closure_reason,
        source=instance.source,
        stage=stage_summary(instance, actions, default_sla),
        blocked_reason=instance.blocked_reason,
        contract=contract_brief(instance.contract),
        programs=sorted(link.program.name for link in instance.programs if link.program),
        template_name=version.template.name if version and version.template else "",
        created_at=instance.created_at,
        updated_at=instance.updated_at,
        started_at=instance.started_at,
        closed_at=instance.closed_at,
    )


def detail_options() -> list:
    return [
        *list_options(),
        selectinload(WorkflowInstance.created_by),
        selectinload(WorkflowInstance.closed_by),
        selectinload(WorkflowInstance.products).selectinload(InteractionProduct.product),
        selectinload(WorkflowInstance.products).selectinload(InteractionProduct.licenses),
        selectinload(WorkflowInstance.products).selectinload(InteractionProduct.program_links),
        selectinload(WorkflowInstance.contacts).selectinload(InteractionContact.contact),
    ]


async def load(session: AsyncSession, interaction_id: uuid.UUID) -> WorkflowInstance:
    statement = (
        select(WorkflowInstance)
        .where(WorkflowInstance.id == interaction_id)
        .options(*detail_options())
        # Состав мог измениться в этом же запросе: берём свежие данные.
        .execution_options(populate_existing=True)
    )
    instance = (await session.execute(statement)).scalar_one_or_none()
    if instance is None:
        raise NotFoundError("Взаимодействие не найдено")
    return instance


async def detail(
    session: AsyncSession,
    instance: WorkflowInstance,
    default_sla: int,
    missing: list[str],
    rights: dict[str, bool],
) -> InteractionDetail:
    actions = await transitions_by_stage(
        session, {instance.current_stage_id} if instance.current_stage_id else set()
    )
    item = list_item(instance, actions, default_sla)
    links = [
        ProgramProductLinkRead(
            program_link_id=link.interaction_program_id,
            product_link_id=link.interaction_product_id,
            is_exception=link.is_exception,
            exception_comment=link.exception_comment,
        )
        for product in instance.products
        for link in product.program_links
    ]
    contacts = [InteractionContactRead.model_validate(row) for row in instance.contacts]
    contacts.sort(key=lambda row: (not row.is_primary, row.contact.full_name))
    return InteractionDetail(
        **item.model_dump(),
        comment=instance.comment,
        template_id=instance.version.template_id,
        workflow_version_id=instance.workflow_version_id,
        version_number=instance.version.version_number,
        blocked_at=instance.blocked_at,
        closure_comment=instance.closure_comment,
        closed_by=_brief_user(instance.closed_by),
        created_by=_brief_user(instance.created_by),
        contract_detail=(
            ContractRead.model_validate(instance.contract) if instance.contract else None
        ),
        program_links=sorted(
            (InteractionProgramRead.model_validate(row) for row in instance.programs),
            key=lambda row: row.program.name if row.program else "",
        ),
        product_links=sorted(
            (InteractionProductRead.model_validate(row) for row in instance.products),
            key=lambda row: row.product.name if row.product else "",
        ),
        links=links,
        contacts=contacts,
        missing_documents=missing,
        **rights,
    )


# --- Фильтры реестра ------------------------------------------------------------


def apply_filters(
    statement: Select,
    *,
    university_id: uuid.UUID | None = None,
    manager_id: uuid.UUID | None = None,
    unassigned: bool = False,
    statuses: list[str] | None = None,
    outcome: str | None = None,
    source: str | None = None,
    direction_id: uuid.UUID | None = None,
    program_id: uuid.UUID | None = None,
    product_id: uuid.UUID | None = None,
    stage_name: str | None = None,
    contract_status: str | None = None,
    has_contract: bool | None = None,
    overdue_only: bool = False,
    default_sla: int = 14,
    search: str | None = None,
    contract_id: uuid.UUID | None = None,
) -> Select:
    if university_id is not None:
        statement = statement.where(WorkflowInstance.university_id == university_id)
    if manager_id is not None:
        statement = statement.where(WorkflowInstance.manager_id == manager_id)
    if unassigned:
        statement = statement.where(WorkflowInstance.manager_id.is_(None))
    if statuses:
        statement = statement.where(WorkflowInstance.status.in_(statuses))
    if outcome:
        statement = statement.where(WorkflowInstance.outcome == outcome)
    if source:
        statement = statement.where(WorkflowInstance.source == source)
    if program_id is not None:
        statement = statement.where(
            WorkflowInstance.id.in_(
                select(InteractionProgram.workflow_instance_id).where(
                    InteractionProgram.program_id == program_id
                )
            )
        )
    if direction_id is not None:
        statement = statement.where(
            WorkflowInstance.id.in_(
                select(InteractionProgram.workflow_instance_id)
                .join(ItProgram, ItProgram.id == InteractionProgram.program_id)
                .where(ItProgram.direction_id == direction_id)
            )
        )
    if product_id is not None:
        statement = statement.where(
            WorkflowInstance.id.in_(
                select(InteractionProduct.workflow_instance_id).where(
                    InteractionProduct.product_id == product_id
                )
            )
        )
    if stage_name:
        # Этапы разных версий шаблона - разные записи с одним названием,
        # поэтому фильтр «по этапу» ведётся по названию.
        statement = statement.where(
            WorkflowInstance.current_stage_id.in_(
                select(WorkflowStage.id).where(WorkflowStage.name == stage_name)
            ),
            WorkflowInstance.status.in_(
                [InteractionStatus.IN_PROGRESS, InteractionStatus.BLOCKED]
            ),
        )
    if contract_status:
        statement = statement.where(
            WorkflowInstance.id.in_(
                select(Contract.workflow_instance_id).where(Contract.status == contract_status)
            )
        )
    if has_contract is True:
        statement = statement.where(
            WorkflowInstance.id.in_(select(Contract.workflow_instance_id))
        )
    elif has_contract is False:
        statement = statement.where(
            WorkflowInstance.id.not_in(select(Contract.workflow_instance_id))
        )
    if contract_id is not None:
        statement = statement.where(
            WorkflowInstance.id.in_(
                select(Contract.workflow_instance_id).where(Contract.id == contract_id)
            )
        )
    if overdue_only:
        # Просрочка этапа: дней на этапе больше нормы - своей или по умолчанию.
        norm = func.coalesce(WorkflowStage.sla_days, default_sla)
        statement = statement.where(
            WorkflowInstance.status == InteractionStatus.IN_PROGRESS,
            WorkflowInstance.current_stage_id.in_(
                select(WorkflowStage.id).where(
                    WorkflowStage.id == WorkflowInstance.current_stage_id,
                    WorkflowInstance.current_stage_started_at
                    < func.now() - func.make_interval(0, 0, 0, norm + 1),
                )
            ),
        )
    if search:
        pattern = f"%{search}%"
        statement = statement.where(
            or_(
                WorkflowInstance.title.ilike(pattern),
                WorkflowInstance.university_id.in_(
                    select(University.id).where(
                        or_(
                            University.name.ilike(pattern),
                            University.short_name.ilike(pattern),
                        )
                    )
                ),
                # Номер договора - один из поисковых атрибутов взаимодействия.
                WorkflowInstance.id.in_(
                    select(Contract.workflow_instance_id).where(Contract.number.ilike(pattern))
                ),
            )
        )
    return statement


# --- Состав: программы, продукты, связи ---------------------------------------------


async def _active_program(session: AsyncSession, program_id: uuid.UUID) -> ItProgram:
    program = await session.get(ItProgram, program_id)
    if program is None:
        raise NotFoundError("Программа не найдена в справочнике")
    if not program.is_active:
        raise ConflictError(
            f"Программа «{program.name}» в архиве: для нового выбора недоступна"
        )
    return program


async def _active_product(session: AsyncSession, product_id: uuid.UUID) -> ItProduct:
    product = await session.get(ItProduct, product_id)
    if product is None:
        raise NotFoundError("Продукт не найден в справочнике")
    if not product.is_active:
        raise ConflictError(f"Продукт «{product.name}» в архиве: для нового выбора недоступен")
    return product


async def add_program(
    session: AsyncSession, instance: WorkflowInstance, program_id: uuid.UUID, status: str
) -> InteractionProgram:
    await _active_program(session, program_id)
    exists = await session.scalar(
        select(func.count())
        .select_from(InteractionProgram)
        .where(
            InteractionProgram.workflow_instance_id == instance.id,
            InteractionProgram.program_id == program_id,
        )
    )
    if exists:
        raise ConflictError("Эта программа уже есть во взаимодействии")
    link = InteractionProgram(
        id=uuid.uuid4(),
        workflow_instance_id=instance.id,
        program_id=program_id,
        implementation_status=status,
    )
    session.add(link)
    await session.flush()
    return link


async def _catalog_pairs(
    session: AsyncSession, program_ids: set[uuid.UUID], product_id: uuid.UUID
) -> set[uuid.UUID]:
    """Программы (из набора), с которыми продукт связан в справочнике."""
    if not program_ids:
        return set()
    return set(
        (
            await session.execute(
                select(ProgramProduct.program_id).where(
                    ProgramProduct.product_id == product_id,
                    ProgramProduct.program_id.in_(program_ids),
                )
            )
        ).scalars()
    )


async def _program_links(
    session: AsyncSession, instance: WorkflowInstance, link_ids: list[uuid.UUID]
) -> list[InteractionProgram]:
    links = list(
        (
            await session.execute(
                select(InteractionProgram).where(
                    InteractionProgram.id.in_(link_ids),
                    InteractionProgram.workflow_instance_id == instance.id,
                )
            )
        ).scalars()
    )
    if len(links) != len(set(link_ids)):
        raise NotFoundError("Программа не найдена в составе этого взаимодействия")
    return links


async def link_product(
    session: AsyncSession,
    instance: WorkflowInstance,
    product_link: InteractionProduct,
    program_links: list[InteractionProgram],
    *,
    exception_comment: str | None,
    may_make_exception: bool,
    user: User,
) -> None:
    """Связывает продукт с программами взаимодействия.

    Связь по справочному соответствию - обычная; вне справочника - только
    как исключение руководителя с комментарием.
    """
    in_catalog = await _catalog_pairs(
        session, {link.program_id for link in program_links}, product_link.product_id
    )
    existing = set(
        (
            await session.execute(
                select(InteractionProgramProduct.interaction_program_id).where(
                    InteractionProgramProduct.interaction_product_id == product_link.id
                )
            )
        ).scalars()
    )
    for program_link in program_links:
        if program_link.id in existing:
            continue
        exception = program_link.program_id not in in_catalog
        if exception:
            if not may_make_exception:
                raise ForbiddenError(
                    "Продукт не связан с этой программой в справочнике. Такую связь "
                    "добавляет руководитель как исключение с комментарием"
                )
            if not (exception_comment or "").strip():
                raise AppError(
                    "Связь вне справочника - исключение: укажите комментарий",
                    code=ErrorCode.VALIDATION_ERROR,
                )
        session.add(
            InteractionProgramProduct(
                interaction_program_id=program_link.id,
                interaction_product_id=product_link.id,
                is_exception=exception,
                exception_comment=exception_comment if exception else None,
                created_by_id=user.id,
            )
        )
    await session.flush()


async def add_product(
    session: AsyncSession,
    instance: WorkflowInstance,
    product_id: uuid.UUID,
    program_link_ids: list[uuid.UUID],
    transfer_status: str,
    *,
    exception_comment: str | None,
    may_make_exception: bool,
    user: User,
) -> InteractionProduct:
    """Продукт добавляется сразу вместе с программами, где он используется.

    Если продукт уже в составе - добавляются только новые связи: один
    продукт в нескольких программах не дублируется.
    """
    await _active_product(session, product_id)
    program_links = await _program_links(session, instance, program_link_ids)
    product_link = await session.scalar(
        select(InteractionProduct).where(
            InteractionProduct.workflow_instance_id == instance.id,
            InteractionProduct.product_id == product_id,
        )
    )
    if product_link is None:
        product_link = InteractionProduct(
            id=uuid.uuid4(),
            workflow_instance_id=instance.id,
            product_id=product_id,
            transfer_status=transfer_status,
        )
        session.add(product_link)
        await session.flush()
    await link_product(
        session,
        instance,
        product_link,
        program_links,
        exception_comment=exception_comment,
        may_make_exception=may_make_exception,
        user=user,
    )
    return product_link


async def unlink(
    session: AsyncSession,
    instance: WorkflowInstance,
    program_link_id: uuid.UUID,
    product_link_id: uuid.UUID,
) -> bool:
    """Убирает связь. Продукт без программ уходит из состава. True - продукт удалён."""
    link = await session.get(InteractionProgramProduct, (program_link_id, product_link_id))
    product_link = await session.get(InteractionProduct, product_link_id)
    if (
        link is None
        or product_link is None
        or product_link.workflow_instance_id != instance.id
    ):
        raise NotFoundError("Такой связи программы и продукта во взаимодействии нет")
    await session.delete(link)
    await session.flush()
    remaining = await session.scalar(
        select(func.count())
        .select_from(InteractionProgramProduct)
        .where(InteractionProgramProduct.interaction_product_id == product_link_id)
    )
    if not remaining:
        await _remove_product(session, product_link)
        return True
    return False


async def _remove_product(session: AsyncSession, product_link: InteractionProduct) -> None:
    licenses = await session.scalar(
        select(func.count())
        .select_from(License)
        .where(License.interaction_product_id == product_link.id)
    )
    if licenses:
        raise ConflictError(
            "По продукту оформлены лицензии: сначала удалите или перенесите их"
        )
    await session.delete(product_link)
    await session.flush()


async def remove_product(
    session: AsyncSession, instance: WorkflowInstance, product_link_id: uuid.UUID
) -> None:
    product_link = await session.get(InteractionProduct, product_link_id)
    if product_link is None or product_link.workflow_instance_id != instance.id:
        raise NotFoundError("Продукт не найден в составе взаимодействия")
    await _remove_product(session, product_link)


async def remove_program(
    session: AsyncSession, instance: WorkflowInstance, program_link_id: uuid.UUID
) -> None:
    link = await session.get(InteractionProgram, program_link_id)
    if link is None or link.workflow_instance_id != instance.id:
        raise NotFoundError("Программа не найдена в составе взаимодействия")
    linked = await session.scalar(
        select(func.count())
        .select_from(InteractionProgramProduct)
        .where(InteractionProgramProduct.interaction_program_id == link.id)
    )
    if linked:
        raise ConflictError(
            "С программой связаны продукты: сначала перенесите их на другую программу "
            "или уберите связи"
        )
    await session.delete(link)
    await session.flush()


async def unlinked_products(session: AsyncSession, instance_ids: list[uuid.UUID]) -> set:
    """Продукты без единой программы - данные, требующие правки."""
    if not instance_ids:
        return set()
    return set(
        (
            await session.execute(
                select(InteractionProduct.workflow_instance_id).where(
                    InteractionProduct.workflow_instance_id.in_(instance_ids),
                    ~InteractionProduct.program_links.any(),
                )
            )
        ).scalars()
    )


# --- Удаление ошибочного черновика --------------------------------------------------


async def deletable(session: AsyncSession, instance: WorkflowInstance) -> bool:
    """Физически удалить можно только ошибочно созданный черновик без
    зависимостей: без договора, файлов, комментариев и движения по процессу.
    Всё остальное отменяют с причиной."""
    if instance.status != InteractionStatus.DRAFT:
        return False
    for model, column in (
        (Contract, Contract.workflow_instance_id),
        (Attachment, Attachment.workflow_instance_id),
        (Comment, Comment.workflow_instance_id),
    ):
        if await session.scalar(
            select(func.count()).select_from(model).where(column == instance.id)
        ):
            return False
    moves = await session.scalar(
        select(func.count())
        .select_from(WorkflowEvent)
        .where(
            WorkflowEvent.workflow_instance_id == instance.id,
            WorkflowEvent.event_type != "created",
        )
    )
    return not moves
