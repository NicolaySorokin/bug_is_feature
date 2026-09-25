"""Демоданные статистики обучения: заявки с сайта и обучающиеся из LMS.

Форма данных повторяет выгрузки, переданные кейсодержателем: у заявки
номер вида ORD-<дата и время>-<код>, курс, ФИО, телефон, почта и номер
потока; у обучающегося - анкета LMS. Люди вымышленные: почта - на
зарезервированных доменах example.com / example.ru, телефоны - из
несуществующего диапазона. Настоящие файлы кейсодержателя с живыми
персональными данными в репозиторий не кладутся.

За год набирается около четырёхсот заявок. Популярные программы набирают
больше потоков: поток закрывается, когда в нём 20 человек или прошло
три месяца, - так появляются параллельные потоки, по которым ТЗ предлагает
судить о востребованности. Около 60% заявителей доходят до обучения
и появляются в LMS. Часть заявок пришла от студентов вузов-партнёров -
они привязаны к договору вуза с этой программой.

Загружается отдельно от основных демоданных и только в пустые таблицы:
python -m scripts.seed вызывает загрузку при каждом запуске.
"""

from __future__ import annotations

import random
import string
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.enums import ContractStatus
from app.models.catalog import ItDirection, ItProgram
from app.models.contract import Contract, ContractProgram
from app.models.integration import IntegrationSource
from app.models.learning import Learner, LearningApplication
from app.models.university import University
from app.services.integrations import sync
from scripts.demo.catalog import AI, DATA, DEV, PROGRAMS, QA
from scripts.demo.people import _FEMALE_NAMES, _MALE_NAMES, _PATRONYMICS, _SURNAMES, translit

SEED = 20260925

PROJECTS = "Управление ИТ-проектами"

# Курсы из выгрузки сайта кейсодержателя - с направлениями, к которым они
# относятся. Сайт их присылает названиями, в каталоге их может не быть.
CASE_COURSES: tuple[tuple[str, str], ...] = (
    ("Анализ данных без программирования", DATA),
    ("Инженер-тестировщик", QA),
    ("Управление ИТ-проектами на базе программного продукта ПАО «Ростелеком»", PROJECTS),
    ("Промпт-инжиниринг", AI),
    ("Python-разработчик с использованием инструментов ИИ", DEV),
)

# Относительный спрос: во сколько раз чаще программа собирает заявки.
_DEMAND = {
    "Python-разработчик": 9,
    "Python-разработчик с использованием инструментов ИИ": 8,
    "Аналитик данных": 7,
    "Анализ данных без программирования": 6,
    "Инженер по тестированию": 6,
    "Инженер-тестировщик": 5,
    "Промпт-инжиниринг": 5,
    "Frontend-разработчик": 4,
    "Специалист по защите информации": 4,
    "Инженер DevOps": 4,
    "Java-разработчик": 3,
    "Инженер машинного обучения": 3,
    "Автоматизация тестирования": 3,
    "Администратор Linux": 2,
    "Управление ИТ-проектами на базе программного продукта ПАО «Ростелеком»": 2,
    "Инженер данных": 2,
    "Сетевой инженер": 2,
    "Анализ защищённости приложений": 1,
    "Администратор баз данных PostgreSQL": 1,
    "Инженер облачной инфраструктуры": 1,
    "Инженер сетей связи": 1,
}

# Справочник уровней образования из анкеты LMS (лист 2 шаблона).
EDUCATION = (
    ("Среднее общее образование - 11 классов", 2),
    ("Среднее профессиональное образование", 3),
    ("Высшее образование – бакалавриат", 6),
    ("Высшее образование – специалитет, магистратура", 4),
    ("Высшее образование – подготовка кадров высшей квалификации", 1),
)

REGIONS = (
    "Москва", "Санкт-Петербург", "Московская область", "Республика Татарстан",
    "Новосибирская область", "Свердловская область", "Краснодарский край",
    "Нижегородская область", "Самарская область", "Томская область",
)  # fmt: skip

STREAM_CAPACITY = 20
STREAM_DAYS = 90
TOTAL = 420
ENROLLED_SHARE = 0.6
WITH_UNIVERSITY_SHARE = 0.35


@dataclass(slots=True)
class Person:
    last_name: str
    first_name: str
    middle_name: str
    female: bool
    email: str
    phone: str


def person(rng: random.Random, index: int) -> Person:
    female = rng.random() < 0.5
    male_surname, female_surname = rng.choice(_SURNAMES)
    surname = female_surname if female else male_surname
    name = rng.choice(_FEMALE_NAMES if female else _MALE_NAMES)
    patronymic = rng.choice(_PATRONYMICS)[1 if female else 0]
    domain = rng.choice(("example.com", "example.ru"))
    login = f"{translit(surname)}.{translit(name[0])}{index}"
    # 900-000-... - несуществующий диапазон, как у контактов вузов в демоданных.
    phone = f"7 (900) 0{rng.randint(10, 99)}-{rng.randint(10, 99)}-{rng.randint(10, 99)}"
    return Person(surname, name, patronymic, female, f"{login}@{domain}", phone)


def order_number(rng: random.Random, moment: datetime) -> str:
    code = "".join(rng.choices(string.ascii_uppercase + string.digits, k=6))
    return f"ORD-{moment:%Y%m%d%H%M%S}-{code}"


def application_json(item: LearningApplication) -> dict[str, object]:
    """Заявка в формате сайта - для фикстур и тестовых файлов."""
    return {
        "Номер заявки": item.external_id,
        "Курс": item.course_name,
        "Фамилия": item.last_name,
        "Имя": item.first_name,
        "Отчество": item.middle_name,
        "Телефон": item.phone,
        "Email": item.email,
        "Номер потока": item.stream_number,
    }


async def _programs(session: AsyncSession) -> dict[str, ItProgram]:
    """Программы для заявок: демонстрационные и курсы кейсодержателя."""
    names = [program.name for program in PROGRAMS] + [name for name, _ in CASE_COURSES]
    found = {
        program.name: program
        for program in (
            await session.execute(select(ItProgram).where(ItProgram.name.in_(names)))
        ).scalars()
    }
    for name, direction_name in CASE_COURSES:
        if name in found:
            continue
        direction = await session.scalar(
            select(ItDirection).where(ItDirection.name == direction_name)
        )
        if direction is None:
            direction = ItDirection(
                name=direction_name,
                description="Проектное управление и продукты Ростелеком",
            )
            session.add(direction)
            await session.flush()
        program = ItProgram(
            name=name,
            direction_id=direction.id,
            description="Курс из каталога сайта ИТ Школы",
        )
        session.add(program)
        await session.flush()
        found[name] = program
    return found


async def _contracts_by_program(session: AsyncSession) -> dict[str, list[Contract]]:
    """Действующие договоры с каждой программой: к ним привязываются заявки студентов."""
    result = await session.execute(
        select(ItProgram.name, Contract)
        .join(ContractProgram, ContractProgram.program_id == ItProgram.id)
        .join(Contract, Contract.id == ContractProgram.contract_id)
        .where(Contract.status == ContractStatus.ACTIVE)
    )
    by_program: dict[str, list[Contract]] = {}
    for name, contract in result.all():
        by_program.setdefault(name, []).append(contract)
    return by_program


async def is_empty(session: AsyncSession) -> bool:
    count = await session.scalar(select(func.count()).select_from(LearningApplication))
    return not count


async def load(session: AsyncSession, total: int = TOTAL) -> tuple[int, int]:
    """Заявки за последний год и анкеты тех, кто дошёл до обучения."""
    rng = random.Random(SEED)
    now = datetime.now(UTC)
    sources = {source.code: source for source in await sync.ensure_sources(session)}
    site: IntegrationSource = sources["site"]
    lms: IntegrationSource = sources["lms"]

    programs = await _programs(session)
    contracts = await _contracts_by_program(session)
    universities = {
        university.id: university
        for university in (await session.execute(select(University))).scalars()
    }

    names = [name for name in programs if name in _DEMAND]
    weights = [_DEMAND[name] for name in names]
    moments = sorted(
        now - timedelta(days=rng.uniform(0, 365), minutes=rng.randint(0, 1440))
        for _ in range(total)
    )

    # Поток программы: открывается первой заявкой, закрывается по размеру
    # или по сроку набора. Номер потока сквозной по программе.
    streams: dict[str, tuple[int, datetime, int]] = {}
    applications = learners = 0
    for index, moment in enumerate(moments, start=1):
        name = rng.choices(names, weights)[0]
        number, opened, size = streams.get(name, (0, moment, STREAM_CAPACITY))
        if size >= STREAM_CAPACITY or (moment - opened).days > STREAM_DAYS:
            number, opened, size = number + 1, moment, 0
        streams[name] = (number, opened, size + 1)

        who = person(rng, index)
        application = LearningApplication(
            source_id=site.id,
            external_id=order_number(rng, moment),
            program_id=programs[name].id,
            course_name=name,
            stream_number=number,
            last_name=who.last_name,
            first_name=who.first_name,
            middle_name=who.middle_name,
            phone="".join(char for char in who.phone if char.isdigit()),
            email=who.email,
            submitted_at=moment,
        )
        candidates = contracts.get(name)
        if candidates and rng.random() < WITH_UNIVERSITY_SHARE:
            contract = rng.choice(candidates)
            application.contract_id = contract.id
            application.university_id = contract.university_id
        session.add(application)
        applications += 1

        if rng.random() < ENROLLED_SHARE:
            university = universities.get(application.university_id)
            city = university.city if university else None
            region = city or rng.choice(REGIONS)
            session.add(
                Learner(
                    source_id=lms.id,
                    last_name=who.last_name,
                    first_name=who.first_name,
                    middle_name=who.middle_name,
                    email=who.email,
                    phone=application.phone,
                    gender="Ж" if who.female else "М",
                    education=rng.choices(
                        [level for level, _ in EDUCATION], [weight for _, weight in EDUCATION]
                    )[0],
                    region=region,
                )
            )
            learners += 1
        if index % 100 == 0:
            await session.flush()
    await session.flush()
    return applications, learners
