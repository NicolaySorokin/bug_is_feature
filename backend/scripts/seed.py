"""Наполнение базы демонстрационными данными.

Запуск:  python -m scripts.seed
Повторный запуск ничего не портит: если шаблон процесса уже есть,
скрипт просто завершается.
"""

import asyncio
from datetime import UTC, date, datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.security import Principal
from app.db.session import SessionFactory, engine
from app.enums import ContractStatus, ImplementationStatus, Role
from app.models.catalog import ItDirection, ItProduct, ItProgram, Vendor
from app.models.contract import Contract, ContractProduct, ContractProgram
from app.models.university import University, UniversityContact
from app.models.user import User
from app.models.workflow import (
    WorkflowStage,
    WorkflowTemplate,
    WorkflowTransition,
    WorkflowVersion,
)
from app.services import workflow as workflow_service

TEMPLATE_NAME = "Стандартный процесс по договору"

# Контакт -> Встреча -> Документы -> Согласование -> Подписание
#                                         `-> Доработка -> Согласование
STAGES = [
    ("contact", "Контакт", 10, False, False, 7),
    ("meeting", "Встреча", 20, False, False, 14),
    ("documents", "Документы", 30, False, False, 10),
    ("approval", "Согласование", 40, False, False, 14),
    ("revision", "Доработка", 50, True, False, 7),
    ("signing", "Подписание", 60, False, True, None),
]

TRANSITIONS = [
    ("contact", "meeting", "Назначена встреча", False, False),
    ("meeting", "contact", "Вернуть к контакту", True, True),
    ("meeting", "documents", "Собрать документы", False, False),
    ("documents", "meeting", "Вернуть к встрече", True, True),
    ("documents", "approval", "Отправить на согласование", False, False),
    ("approval", "signing", "Согласовано, на подписание", False, False),
    ("approval", "revision", "Отправить на доработку", True, True),
    ("revision", "approval", "Вернуть на согласование", False, False),
]


async def seed_workflow(session: AsyncSession) -> WorkflowVersion:
    template = WorkflowTemplate(
        name=TEMPLATE_NAME,
        description="Базовый маршрут работы с вузом от первого контакта до подписания.",
    )
    session.add(template)
    await session.flush()

    version = WorkflowVersion(
        template_id=template.id,
        version_number=1,
        published_at=datetime.now(UTC),
    )
    session.add(version)
    await session.flush()

    stages: dict[str, WorkflowStage] = {}
    for index, (code, name, order, optional, final, sla) in enumerate(STAGES):
        stage = WorkflowStage(
            workflow_version_id=version.id,
            code=code,
            name=name,
            sort_order=order,
            is_optional=optional,
            is_final=final,
            sla_days=sla,
            layout_x=index * 220,
            layout_y=0 if code != "revision" else 160,
        )
        session.add(stage)
        stages[code] = stage
    await session.flush()

    for src, dst, name, backward, needs_comment in TRANSITIONS:
        session.add(
            WorkflowTransition(
                workflow_version_id=version.id,
                from_stage_id=stages[src].id,
                to_stage_id=stages[dst].id,
                name=name,
                is_backward=backward,
                requires_comment=needs_comment,
            )
        )
    await session.flush()

    await session.refresh(version, ["stages", "transitions"])
    return version


async def seed_catalog(session: AsyncSession) -> dict[str, list]:
    direction = ItDirection(name="Разработка", description="Программирование и инженерия")
    analytics = ItDirection(name="Аналитика данных")
    session.add_all([direction, analytics])
    await session.flush()

    programs = [
        ItProgram(direction_id=direction.id, name="Python-разработчик"),
        ItProgram(direction_id=direction.id, name="Инженер по тестированию"),
        ItProgram(direction_id=analytics.id, name="Аналитик данных"),
        ItProgram(direction_id=analytics.id, name="Инженер данных"),
    ]
    session.add_all(programs)

    vendor = Vendor(name="Ростелеком")
    session.add(vendor)
    await session.flush()

    products = [
        ItProduct(vendor_id=vendor.id, name="Платформа онлайн-обучения"),
        ItProduct(vendor_id=vendor.id, name="Симулятор сетевой инфраструктуры"),
    ]
    session.add_all(products)
    await session.flush()

    return {"programs": programs, "products": products}


async def seed_contracts(
    session: AsyncSession,
    catalog: dict[str, list],
    manager: User,
    version: WorkflowVersion,
) -> None:
    university = University(
        name="Московский технический университет связи и информатики",
        short_name="МТУСИ",
        city="Москва",
        manager_id=manager.id,
    )
    second = University(
        name="Санкт-Петербургский государственный университет телекоммуникаций",
        short_name="СПбГУТ",
        city="Санкт-Петербург",
        manager_id=manager.id,
    )
    session.add_all([university, second])
    await session.flush()

    session.add(
        UniversityContact(
            university_id=university.id,
            full_name="Иванова Мария Сергеевна",
            position="Проректор по учебной работе",
            email="ivanova@example.edu",
        )
    )

    # Пример из раздела 1: у одного вуза два договора с разным составом программ.
    first_contract = Contract(
        university_id=university.id,
        manager_id=manager.id,
        number="ДГ-2025-001",
        title="Основной договор о сотрудничестве",
        signed_at=date(2025, 9, 1),
        valid_from=date(2025, 9, 1),
        valid_to=date(2026, 8, 31),
        status=ContractStatus.ACTIVE,
    )
    second_contract = Contract(
        university_id=university.id,
        manager_id=manager.id,
        number="ДГ-2026-014",
        title="Расширение состава программ",
        signed_at=date(2026, 2, 10),
        valid_from=date(2026, 2, 10),
        valid_to=date(2027, 2, 9),
        status=ContractStatus.DRAFT,
    )
    session.add_all([first_contract, second_contract])
    await session.flush()

    programs = catalog["programs"]
    products = catalog["products"]
    for program in programs[:2]:
        session.add(
            ContractProgram(
                contract_id=first_contract.id,
                program_id=program.id,
                implementation_status=ImplementationStatus.IN_PROGRESS,
            )
        )
    for program in programs[2:]:
        session.add(ContractProgram(contract_id=second_contract.id, program_id=program.id))
    session.add(
        ContractProduct(contract_id=first_contract.id, product_id=products[0].id)
    )
    await session.flush()

    # По первому договору запускаем процесс и делаем пару шагов вперёд.
    instance = await workflow_service.start_instance(
        session, first_contract.id, version, manager
    )
    stage_by_code = {stage.code: stage for stage in version.stages}
    principal = Principal(
        subject=manager.keycloak_id,
        username=manager.username,
        full_name=manager.full_name,
        roles=frozenset({Role.MANAGER, Role.HEAD, Role.ADMIN}),
    )
    await workflow_service.move(
        session,
        instance,
        version,
        stage_by_code["meeting"].id,
        manager,
        principal,
        comment="Договорились о встрече на площадке вуза",
    )
    await workflow_service.move(
        session,
        instance,
        version,
        stage_by_code["documents"].id,
        manager,
        principal,
        comment="Встреча прошла, собираем пакет документов",
    )


async def main() -> None:
    async with SessionFactory() as session:
        existing = await session.scalar(
            select(WorkflowTemplate).where(WorkflowTemplate.name == TEMPLATE_NAME)
        )
        if existing is not None:
            print("Демоданные уже загружены, ничего не меняю.")
            return

        manager = await session.scalar(
            select(User).where(User.keycloak_id == settings.dev_user_subject)
        )
        if manager is None:
            manager = User(
                keycloak_id=settings.dev_user_subject,
                username=settings.dev_user_username,
                full_name=settings.dev_user_full_name,
                email=settings.dev_user_email,
            )
            session.add(manager)
            await session.flush()

        version = await seed_workflow(session)
        catalog = await seed_catalog(session)
        await seed_contracts(session, catalog, manager, version)
        await session.commit()
        print("Демоданные загружены.")

    await engine.dispose()


if __name__ == "__main__":
    asyncio.run(main())
