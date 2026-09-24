"""Демонстрационные данные: согласованность и то, что увидят на показе.

Первые проверки базы не требуют: реалм Keycloak, ответы LMS и сайта и
сюжеты договоров должны сходиться со справочниками и шаблонами процессов.
Последние загружают демоданные в тестовую базу и смотрят на результат
глазами менеджера и руководителя. Загрузка занимает секунды, поэтому
проверки базы собраны в два теста, а не разложены по одной.
"""

from __future__ import annotations

import json
import random
from pathlib import Path

import pytest
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker
from sqlalchemy.orm import selectinload

from app.core.config import settings
from app.core.security import Principal
from app.enums import AlertKind, ContractStatus, StageState, WorkflowEventType
from app.models.content import Attachment
from app.models.contract import Contract
from app.models.user import User
from app.models.workflow import WorkflowInstance
from app.schemas.report import ChartKey, ReportRequest
from app.services import alerts, dashboard, reports, storage
from app.services import workflow as workflow_service
from app.services.integrations.base import FIXTURES
from scripts.demo.catalog import DIRECTIONS, PRODUCTS, PROGRAMS, UNIVERSITIES
from scripts.demo.loader import GENERATED, DemoLoader, Summary
from scripts.demo.people import EMPLOYEES
from scripts.demo.plans import STORIES, Move, generate
from scripts.demo.processes import TEMPLATE_BY_KEY

REALM = Path(__file__).resolve().parents[2] / "deploy" / "keycloak" / "realm-export.json"

# Чего в демоданных нет намеренно: это заводит сама синхронизация.
NEW_IN_LMS = {"Разработчик на Go", "Основы кибергигиены", "Тренажёр SQL"}
NEW_ON_SITE = {
    "Кубанский государственный технологический университет",
    "Алтайский государственный технический университет им. И. И. Ползунова",
}


def test_realm_matches_demo_users() -> None:
    """Вход через Keycloak попадает на пользователя, которому сид отдал договоры."""
    if not REALM.is_file():
        pytest.skip("Реалм лежит вне каталога backend - в контейнере его нет")
    users = {user["username"]: user for user in json.loads(REALM.read_text("utf-8"))["users"]}

    for employee in EMPLOYEES:
        user = users.get(employee.username)
        assert user is not None, f"В реалме нет пользователя {employee.username}"
        assert user["id"] == employee.keycloak_id, (
            f"{employee.username}: id в реалме должен быть {employee.keycloak_id} - "
            "выгрузите пользователей заново: python -m scripts.demo.people"
        )
        assert sorted(user["realmRoles"]) == sorted(employee.roles)


def test_integration_fixtures_match_catalog() -> None:
    """Синхронизация обновляет демоданные, а не заводит их дубли."""
    lms = json.loads((FIXTURES / "lms.json").read_text("utf-8"))
    site = json.loads((FIXTURES / "site.json").read_text("utf-8"))

    programs = {program.name for program in PROGRAMS}
    for item in lms["programs"]:
        assert item["name"] in programs | NEW_IN_LMS, item["name"]
        assert item["direction"] in DIRECTIONS, item["direction"]
    products = {product.name for product in PRODUCTS}
    for item in lms["products"]:
        assert item["name"] in products | NEW_IN_LMS, item["name"]

    universities = {university.name for university in UNIVERSITIES}
    for item in site["universities"]:
        assert item["name"] in universities | NEW_ON_SITE, item["name"]

    # Разобранные заявки из сюжетов есть на сайте - повторный обмен их пропустит.
    requests = {item["id"] for item in site["requests"]}
    assert {plan.request for plan in STORIES if plan.request} <= requests


@pytest.mark.parametrize(
    "plans",
    [STORIES, generate(300, random.Random(7))],
    ids=["сюжеты", "сгенерированные"],
)
def test_routes_follow_templates(plans) -> None:  # noqa: ANN001 - параметр pytest
    """Каждый шаг истории разрешён схемой во всех версиях шаблона."""
    for plan in plans:
        if plan.template is None:
            continue
        for version in TEMPLATE_BY_KEY[plan.template].versions:
            allowed = {(item.source, item.target) for item in version.transitions}
            current = version.stages[0].code
            for step in plan.route:
                target = step.stage if isinstance(step, Move) else step
                assert (current, target) in allowed, f"{plan.number}: {current} -> {target}"
                current = target


# --- Демоданные в базе --------------------------------------------------------


@pytest.fixture
async def demo(engine: AsyncEngine, tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    """Тестовая база с демоданными. Файлы пишутся во временный каталог."""
    monkeypatch.setattr(settings, "storage_dir", tmp_path / "storage")
    factory = async_sessionmaker(engine, expire_on_commit=False)
    async with factory() as session:
        loader = DemoLoader(session)
        assert await loader.is_empty()
        summary = await loader.load()
        await session.commit()
        yield session, summary


async def _as(session: AsyncSession, username: str, *roles: str) -> tuple[Principal, User]:
    user = await session.scalar(select(User).where(User.username == username))
    principal = Principal(
        subject=user.keycloak_id,
        username=username,
        full_name=user.full_name,
        roles=frozenset(roles),
    )
    return principal, user


async def test_demo_database(demo: tuple[AsyncSession, Summary]) -> None:
    session, summary = demo

    # Объём: сюжеты плюс сгенерированные договоры, все вузы и сотрудники.
    assert summary.contracts == len(STORIES) + GENERATED
    assert summary.universities == len(UNIVERSITIES)
    assert summary.users == len(EMPLOYEES)

    # Файлы всех форматов из ТЗ, кроме xls, действительно лежат на диске.
    attachments = (await session.execute(select(Attachment))).scalars().all()
    assert len(attachments) == summary.attachments > 100
    formats = {item.storage_path.rsplit(".", 1)[1] for item in attachments}
    assert formats >= {"pdf", "png", "jpeg", "docx", "doc", "xlsx", "zip", "gz", "rar"}
    assert all(storage.absolute_path(item.storage_path).is_file() for item in attachments)

    # Руководитель видит по тревоге каждого вида, и все они помещаются на главной.
    head, head_user = await _as(session, "orlova", "manager", "head")
    found = await alerts.collect(session, head, head_user)
    assert {alert.kind for alert in found} == set(AlertKind)
    assert len(found) <= dashboard.ALERTS_LIMIT, [alert.message for alert in found]

    # Главный герой показа: почти все сюжеты - у него.
    petrov, petrov_user = await _as(session, "petrov", "manager")
    kinds = {alert.kind for alert in await alerts.collect(session, petrov, petrov_user)}
    assert kinds >= {
        AlertKind.CONTRACT_EXPIRING,
        AlertKind.LICENSE_EXPIRING,
        AlertKind.STAGE_STALE,
        AlertKind.PROCESS_BLOCKED,
        AlertKind.NO_DOCUMENTS,
        AlertKind.INTEGRATION_FAILED,
    }
    view = await dashboard.build(session, petrov, petrov_user)
    assert view.counters.my_contracts >= sum(1 for p in STORIES if p.manager == "petrov")

    # Действующие договоры подписаны и со сроком.
    active = await session.execute(
        select(Contract).where(Contract.status == ContractStatus.ACTIVE)
    )
    for contract in active.scalars():
        assert contract.signed_at and contract.valid_to, contract.number
        assert contract.valid_from <= contract.valid_to, contract.number

    # История идёт по порядку, текущий этап - это последний переход.
    instances = await session.execute(
        select(WorkflowInstance).options(selectinload(WorkflowInstance.events))
    )
    states: set[StageState] = set()
    for instance in instances.scalars():
        events = sorted(instance.events, key=lambda event: event.created_at)
        assert events[0].event_type == WorkflowEventType.STARTED
        assert instance.started_at == events[0].created_at
        moves = [event for event in events if event.from_stage_id != event.to_stage_id]
        assert moves[-1].to_stage_id == instance.current_stage_id
        assert moves[-1].created_at == instance.current_stage_started_at

        version = await workflow_service.load_version(session, instance.workflow_version_id)
        states |= set(
            workflow_service.compute_stage_states(version, instance, events).values()
        )
    # На схемах встречаются все пять состояний этапа из раздела 3.4.
    assert states == set(StageState)

    # Отчёт строится по всему объёму, хвост нагрузки сворачивается в «Прочие».
    admin, admin_user = await _as(session, "admin", "manager", "head", "admin")
    report = await reports.build_report(session, ReportRequest(), admin, admin_user)
    assert report.totals.contracts == summary.contracts
    by_manager = next(chart for chart in report.charts if chart.key == ChartKey.BY_MANAGER)
    assert by_manager.items[-1].label == "Прочие"


async def test_load_mode(demo: tuple[AsyncSession, Summary]) -> None:
    """Добавка для нагрузки встаёт поверх демоданных, в том числе повторно."""
    session, summary = demo
    loader = DemoLoader(session)
    assert not await loader.is_empty()

    assert await loader.load_extra(30, batch=12) == 30
    await session.commit()
    assert await DemoLoader(session).load_extra(10) == 10
    await session.commit()

    total = await session.scalar(select(func.count()).select_from(Contract))
    assert total == summary.contracts + 40
