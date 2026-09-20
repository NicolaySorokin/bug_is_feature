"""Наполнение базы демонстрационными данными.

Запуск:  python -m scripts.seed
Повторный запуск ничего не портит: если шаблон процесса уже есть,
скрипт просто завершается.

Данные подобраны так, чтобы сразу было что показать: договоры на разных
этапах, разные ответственные, истекающие сроки, заблокированный процесс
и завершённая работа. На такой выборке видно и отчёты, и диаграммы,
и контроль проблемных процессов.

Идентификаторы пользователей совпадают с тем, что подставляет dev-заглушка
авторизации: войдя с заголовком ``X-Dev-User: petrov``, вы попадёте на
договоры Петрова, а не на чужие.
"""

import asyncio
from datetime import UTC, date, datetime, timedelta

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.security import Principal
from app.db.session import SessionFactory, engine
from app.enums import ContractStatus, ImplementationStatus, LicenseStatus, Role
from app.models.catalog import ItDirection, ItProduct, ItProgram, Vendor
from app.models.content import Comment
from app.models.contract import Contract, ContractProduct, ContractProgram, License
from app.models.university import University, UniversityContact
from app.models.user import User
from app.models.workflow import (
    WorkflowInstance,
    WorkflowStage,
    WorkflowTemplate,
    WorkflowTransition,
    WorkflowVersion,
)
from app.services import workflow as workflow_service
from app.services.integrations import sync

TEMPLATE_NAME = "Стандартный процесс по договору"
TODAY = date.today()

# Контакт -> Встреча -> Документы -> Согласование -> Подписание
#                                         `-> Доработка -> Согласование
# code, название, порядок, необязательный, финальный, срок в днях
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

# username, ФИО, роль в системе
MANAGERS = [
    ("petrov", "Петров Пётр Алексеевич", Role.MANAGER),
    ("ivanova", "Иванова Мария Сергеевна", Role.MANAGER),
    ("orlova", "Орлова Ольга Дмитриевна", Role.HEAD),
]

DIRECTIONS = [
    ("Разработка", "Программирование и инженерия"),
    ("QA", "Тестирование программного обеспечения"),
    ("DevOps", "Сборка, развёртывание и эксплуатация"),
    ("Аналитика данных", "Работа с данными и отчётностью"),
    ("Информационная безопасность", "Защита информационных систем"),
]

# программа -> направление
PROGRAMS = [
    ("Python-разработчик", "Разработка"),
    ("Java-разработчик", "Разработка"),
    ("Инженер по тестированию", "QA"),
    ("Автоматизация тестирования", "QA"),
    ("Инженер DevOps", "DevOps"),
    ("Аналитик данных", "Аналитика данных"),
    ("Инженер данных", "Аналитика данных"),
    ("Специалист по защите информации", "Информационная безопасность"),
]

PRODUCTS = [
    ("Платформа онлайн-обучения", "Ростелеком"),
    ("Симулятор сетевой инфраструктуры", "Ростелеком"),
    ("Песочница DevOps", "Ростелеком"),
    ("Стенд киберполигона", "Ростелеком"),
]

# название, сокращение, город, индекс менеджера
UNIVERSITIES = [
    ("Московский технический университет связи и информатики", "МТУСИ", "Москва", 0),
    (
        "Санкт-Петербургский государственный университет телекоммуникаций",
        "СПбГУТ",
        "Санкт-Петербург",
        0,
    ),
    (
        "Казанский национальный исследовательский технический университет",
        "КНИТУ-КАИ",
        "Казань",
        1,
    ),
    ("Новосибирский государственный технический университет", "НГТУ", "Новосибирск", 1),
    ("Уральский федеральный университет", "УрФУ", "Екатеринбург", 2),
    ("Южный федеральный университет", "ЮФУ", "Ростов-на-Дону", 2),
]

CONTACTS = [
    (0, "Соколова Анна Викторовна", "Проректор по учебной работе", "sokolova@example.edu"),
    (0, "Мельников Игорь Олегович", "Заведующий кафедрой", "melnikov@example.edu"),
    (1, "Орехов Дмитрий Павлович", "Начальник учебного управления", "orehov@example.edu"),
    (2, "Гафуров Ильдар Рашидович", "Заведующий кафедрой информатики", "gafurov@example.edu"),
    (3, "Ковалёва Анна Петровна", "Начальник учебного управления", "kovaleva@example.edu"),
    (4, "Зырянов Сергей Иванович", "Директор института", "zyryanov@example.edu"),
]

# Договоры: вуз, менеджер, номер, название, статус, срок действия (дней от сегодня),
# программы, продукты, путь по процессу, дней на текущем этапе, блокировка
CONTRACTS = [
    {
        "university": 0,
        "manager": 0,
        "number": "ДГ-2025-001",
        "title": "Основной договор о сотрудничестве",
        "status": ContractStatus.ACTIVE,
        "signed_days_ago": 380,
        "valid_days_left": 40,  # скоро закончится - попадёт в проблемные
        "programs": [0, 2],
        "products": [0],
        "path": ["meeting", "documents", "approval", "signing"],
        "days_on_stage": 3,
        "license_days_left": 40,
        "implementation": ImplementationStatus.IMPLEMENTED,
    },
    {
        "university": 0,
        "manager": 0,
        "number": "ДГ-2026-014",
        "title": "Расширение состава программ",
        "status": ContractStatus.DRAFT,
        "signed_days_ago": None,
        "valid_days_left": None,
        "programs": [5, 6],
        "products": [],
        "path": ["meeting"],
        "days_on_stage": 21,  # этап давно не менялся
        "license_days_left": None,
        "implementation": ImplementationStatus.NOT_STARTED,
    },
    {
        "university": 1,
        "manager": 0,
        "number": "ДГ-2025-047",
        "title": "Подготовка инженеров по тестированию",
        "status": ContractStatus.ACTIVE,
        "signed_days_ago": 200,
        "valid_days_left": 165,
        "programs": [2, 3],
        "products": [0, 1],
        "path": ["meeting", "documents"],
        "days_on_stage": 4,
        "license_days_left": 165,
        "implementation": ImplementationStatus.IN_PROGRESS,
    },
    {
        "university": 2,
        "manager": 1,
        "number": "ДГ-2026-003",
        "title": "DevOps и облачная инфраструктура",
        "status": ContractStatus.ACTIVE,
        "signed_days_ago": 120,
        "valid_days_left": 245,
        "programs": [4],
        "products": [2],
        "path": ["meeting", "documents", "approval"],
        "days_on_stage": 19,  # согласование затянулось
        "license_days_left": 245,
        "implementation": ImplementationStatus.IN_PROGRESS,
    },
    {
        "university": 3,
        "manager": 1,
        "number": "ДГ-2026-009",
        "title": "Аналитика данных для инженерных специальностей",
        "status": ContractStatus.ACTIVE,
        "signed_days_ago": 90,
        "valid_days_left": 275,
        "programs": [5, 6],
        "products": [0],
        "path": ["meeting", "documents", "approval", "revision"],
        "days_on_stage": 6,
        "license_days_left": 275,
        "implementation": ImplementationStatus.IN_PROGRESS,
        "blocked": "Вуз просит изменить состав программ, ждём решения",
    },
    {
        "university": 4,
        "manager": 2,
        "number": "ДГ-2026-021",
        "title": "Киберполигон и защита информации",
        "status": ContractStatus.ACTIVE,
        "signed_days_ago": 45,
        "valid_days_left": 320,
        "programs": [7],
        "products": [3],
        "path": ["meeting", "documents"],
        "days_on_stage": 2,
        "license_days_left": -5,  # лицензия уже просрочена
        "implementation": ImplementationStatus.NOT_STARTED,
    },
    {
        "university": 5,
        "manager": 2,
        "number": "ДГ-2026-033",
        "title": "Разработка на Java для магистратуры",
        "status": ContractStatus.DRAFT,
        "signed_days_ago": None,
        "valid_days_left": None,
        "programs": [1],
        "products": [],
        "path": [],
        "days_on_stage": 9,
        "license_days_left": None,
        "implementation": ImplementationStatus.NOT_STARTED,
    },
    {
        "university": 5,
        "manager": None,  # ответственный не назначен - тоже повод для сигнала
        "number": "ДГ-2026-040",
        "title": "Пилот по инженерии данных",
        "status": ContractStatus.DRAFT,
        "signed_days_ago": None,
        "valid_days_left": None,
        "programs": [6],
        "products": [],
        "path": [],
        "days_on_stage": 1,
        "license_days_left": None,
        "implementation": ImplementationStatus.NOT_STARTED,
    },
]

COMMENTS = [
    (0, "Документы подписаны, лицензия передана в вуз."),
    (2, "Вуз попросил добавить второй поток по автоматизации тестирования."),
    (3, "Согласование затянулось: ждём правки от юристов вуза."),
]


def _days(value: int | None) -> date | None:
    return None if value is None else TODAY + timedelta(days=value)


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


async def seed_users(session: AsyncSession) -> tuple[User, list[User]]:
    """Пользователь по умолчанию и менеджеры по вузам."""
    default = User(
        keycloak_id=settings.dev_user_subject,
        username=settings.dev_user_username,
        full_name=settings.dev_user_full_name,
        email=settings.dev_user_email,
    )
    session.add(default)

    managers: list[User] = []
    for username, full_name, _role in MANAGERS:
        # Такой же идентификатор подставляет dev-заглушка для X-Dev-User.
        user = User(
            keycloak_id=f"dev:{username}",
            username=username,
            full_name=full_name,
            email=f"{username}@example.com",
        )
        session.add(user)
        managers.append(user)
    await session.flush()
    return default, managers


async def seed_catalog(session: AsyncSession) -> tuple[list[ItProgram], list[ItProduct]]:
    directions: dict[str, ItDirection] = {}
    for name, description in DIRECTIONS:
        direction = ItDirection(name=name, description=description)
        session.add(direction)
        directions[name] = direction

    vendor = Vendor(name="Ростелеком", description="Вендор ИТ-продуктов ИТ Школы")
    session.add(vendor)
    await session.flush()

    programs = []
    for name, direction_name in PROGRAMS:
        program = ItProgram(name=name, direction_id=directions[direction_name].id)
        session.add(program)
        programs.append(program)

    products = []
    for name, _vendor_name in PRODUCTS:
        product = ItProduct(name=name, vendor_id=vendor.id)
        session.add(product)
        products.append(product)
    await session.flush()
    return programs, products


async def seed_universities(
    session: AsyncSession, managers: list[User]
) -> list[University]:
    universities = []
    for name, short_name, city, manager_index in UNIVERSITIES:
        university = University(
            name=name,
            short_name=short_name,
            city=city,
            manager_id=managers[manager_index].id,
        )
        session.add(university)
        universities.append(university)
    await session.flush()

    for university_index, full_name, position, email in CONTACTS:
        session.add(
            UniversityContact(
                university_id=universities[university_index].id,
                full_name=full_name,
                position=position,
                email=email,
            )
        )
    await session.flush()
    return universities


def _principal(user: User) -> Principal:
    """Все права: сценарий демоданных проходит и обязательные этапы."""
    return Principal(
        subject=user.keycloak_id,
        username=user.username,
        full_name=user.full_name,
        roles=frozenset({Role.MANAGER, Role.HEAD, Role.ADMIN}),
    )


async def _walk_process(
    session: AsyncSession,
    contract: Contract,
    version: WorkflowVersion,
    actor: User,
    spec: dict,
) -> WorkflowInstance:
    """Проводит процесс по заданному пути, чтобы в истории были переходы."""
    instance = await workflow_service.start_instance(session, contract.id, version, actor)
    stage_by_code = {stage.code: stage for stage in version.stages}
    principal = _principal(actor)

    for code in spec["path"]:
        await workflow_service.move(
            session,
            instance,
            version,
            stage_by_code[code].id,
            actor,
            principal,
            comment=f"Переход на этап «{stage_by_code[code].name}»",
        )

    if spec.get("blocked"):
        await workflow_service.set_blocked(session, instance, actor, spec["blocked"], True)

    # Время на этапе задаём задним числом: без этого все процессы выглядят
    # свежими и контроль просроченных этапов нечего показывать.
    instance.current_stage_started_at = datetime.now(UTC) - timedelta(
        days=spec["days_on_stage"]
    )
    await session.flush()
    return instance


async def seed_contracts(
    session: AsyncSession,
    universities: list[University],
    programs: list[ItProgram],
    products: list[ItProduct],
    managers: list[User],
    default_user: User,
    version: WorkflowVersion,
) -> list[Contract]:
    created: list[Contract] = []

    for spec in CONTRACTS:
        manager = managers[spec["manager"]] if spec["manager"] is not None else None
        contract = Contract(
            university_id=universities[spec["university"]].id,
            manager_id=manager.id if manager else None,
            number=spec["number"],
            title=spec["title"],
            status=spec["status"],
            signed_at=(
                _days(-spec["signed_days_ago"]) if spec["signed_days_ago"] else None
            ),
            valid_from=(
                _days(-spec["signed_days_ago"]) if spec["signed_days_ago"] else None
            ),
            valid_to=_days(spec["valid_days_left"]),
        )
        session.add(contract)
        await session.flush()

        for program_index in spec["programs"]:
            session.add(
                ContractProgram(
                    contract_id=contract.id,
                    program_id=programs[program_index].id,
                    implementation_status=spec["implementation"],
                )
            )
        for product_index in spec["products"]:
            link = ContractProduct(
                contract_id=contract.id,
                product_id=products[product_index].id,
                transfer_status=spec["implementation"],
            )
            session.add(link)
            await session.flush()

            if spec["license_days_left"] is not None:
                valid_to = _days(spec["license_days_left"])
                session.add(
                    License(
                        contract_product_id=link.id,
                        number=f"ЛИЦ-{spec['number']}",
                        seats=100,
                        signed_at=_days(-spec["signed_days_ago"]),
                        valid_from=_days(-spec["signed_days_ago"]),
                        valid_to=valid_to,
                        status=(
                            LicenseStatus.EXPIRED
                            if valid_to and valid_to < TODAY
                            else LicenseStatus.ACTIVE
                        ),
                    )
                )
        await session.flush()

        if spec["path"] or spec.get("blocked"):
            await _walk_process(session, contract, version, manager or default_user, spec)

        created.append(contract)

    for contract_index, text in COMMENTS:
        session.add(
            Comment(
                contract_id=created[contract_index].id,
                author_id=(created[contract_index].manager_id or default_user.id),
                text=text,
            )
        )
    await session.flush()
    return created


async def main() -> None:
    async with SessionFactory() as session:
        existing = await session.scalar(
            select(WorkflowTemplate).where(WorkflowTemplate.name == TEMPLATE_NAME)
        )
        if existing is not None:
            print("Демоданные уже загружены, ничего не меняю.")
            return

        version = await seed_workflow(session)
        default_user, managers = await seed_users(session)
        programs, products = await seed_catalog(session)
        universities = await seed_universities(session, managers)
        contracts = await seed_contracts(
            session, universities, programs, products, managers, default_user, version
        )
        # Источники обмена заводим сразу: раздел «Интеграции» не должен быть пустым.
        await sync.ensure_sources(session)

        await session.commit()
        print(
            f"Демоданные загружены: вузов {len(universities)}, "
            f"договоров {len(contracts)}, программ {len(programs)}."
        )

    await engine.dispose()


if __name__ == "__main__":
    asyncio.run(main())
