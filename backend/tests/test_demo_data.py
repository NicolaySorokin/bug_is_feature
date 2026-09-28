"""Демонстрационные данные: согласованность и то, что увидят на показе.

Первые проверки идут без базы, последние загружают демоданные и смотрят
на них глазами менеджера и руководителя.
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
from app.enums import (
    AlertKind,
    ContractStatus,
    DocumentType,
    InteractionOutcome,
    InteractionStatus,
    StageState,
    WorkflowEventType,
    WorkflowVersionStatus,
)
from app.models.content import Attachment
from app.models.contract import Contract
from app.models.interaction import InteractionProduct
from app.models.user import User
from app.models.workflow import WorkflowInstance, WorkflowTemplate, WorkflowVersion
from app.schemas.report import ChartKey, ReportRequest
from app.services import alerts, dashboard, reports, storage
from app.services import workflow as workflow_service
from app.services.integrations.base import FIXTURES
from scripts.demo.catalog import DIRECTIONS, PRODUCTS, PROGRAMS, UNIVERSITIES
from scripts.demo.loader import GENERATED, DemoLoader, Summary
from scripts.demo.people import EMPLOYEE_BY_USERNAME, EMPLOYEES
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
    """Вход через Keycloak попадает на пользователя, которому сид отдал взаимодействия."""
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


def test_realm_keeps_no_secrets() -> None:
    """Репозиторий публичный: паролей и секретов клиентов в выгрузке нет.

    Вход по паролю в обход страницы Keycloak включён только у выключенного
    клиента нагрузочной проверки.
    """
    if not REALM.is_file():
        pytest.skip("Реалм лежит вне каталога backend - в контейнере его нет")
    realm = json.loads(REALM.read_text("utf-8"))

    assert all("credentials" not in user for user in realm["users"])
    assert "length(12)" in realm["passwordPolicy"]
    assert realm["sslRequired"] == "external"
    for client in realm["clients"]:
        assert "secret" not in client, client["clientId"]
        if client["directAccessGrantsEnabled"]:
            assert client["clientId"] == "edu-crm-loadtest"
            assert client["enabled"] is False


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

    # Разобранные заявки из сюжетов есть на сайте, повторный обмен их пропустит.
    requests = {item["id"] for item in site["requests"]}
    assert {plan.request for plan in STORIES if plan.request} <= requests


@pytest.mark.parametrize(
    "plans",
    [STORIES, generate(300, random.Random(7))],
    ids=["сюжеты", "сгенерированные"],
)
def test_routes_follow_templates(plans) -> None:  # noqa: ANN001 (параметр pytest)
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


# Демоданные в базе


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


async def _as(session: AsyncSession, username: str) -> tuple[Principal, User]:
    """Сотрудник из демоданных с ролями из реалма."""
    user = await session.scalar(select(User).where(User.username == username))
    principal = Principal(
        subject=user.keycloak_id,
        username=username,
        full_name=user.full_name,
        roles=frozenset(EMPLOYEE_BY_USERNAME[username].roles),
    )
    return principal, user


async def test_demo_database(demo: tuple[AsyncSession, Summary]) -> None:
    session, summary = demo

    # Объём: сюжеты плюс сгенерированные взаимодействия, все вузы (и один
    # на проверке) и сотрудники.
    assert summary.interactions == len(STORIES) + GENERATED
    assert summary.universities == len(UNIVERSITIES) + 1
    assert summary.users == len(EMPLOYEES)
    # Договор появляется в ходе взаимодействия: у ранних его ещё нет.
    contracts = await session.scalar(select(func.count()).select_from(Contract))
    assert contracts == summary.contracts
    assert 0 < summary.contracts < summary.interactions
    drafts_with_contract = await session.scalar(
        select(func.count())
        .select_from(Contract)
        .join(WorkflowInstance, WorkflowInstance.id == Contract.workflow_instance_id)
        .where(WorkflowInstance.status == InteractionStatus.DRAFT)
    )
    assert drafts_with_contract == 0

    # Файлы всех форматов из ТЗ, кроме xls, лежат на диске, у каждого есть тип.
    attachments = (await session.execute(select(Attachment))).scalars().all()
    assert len(attachments) == summary.attachments > 100
    formats = {item.storage_path.rsplit(".", 1)[1] for item in attachments}
    assert formats >= {"pdf", "png", "jpeg", "docx", "doc", "xlsx", "zip", "gz", "rar"}
    assert all(storage.absolute_path(item.storage_path).is_file() for item in attachments)
    types = {item.document_type for item in attachments}
    assert {DocumentType.CONTRACT, DocumentType.LICENSE, DocumentType.LETTER} <= types

    # У шаблона одна действующая версия; первая версия основного устарела.
    statuses = (
        await session.execute(
            select(
                WorkflowTemplate.name, WorkflowVersion.version_number, WorkflowVersion.status
            )
            .join(WorkflowVersion)
            .order_by(WorkflowTemplate.name, WorkflowVersion.version_number)
        )
    ).all()
    by_template: dict[str, list[str]] = {}
    for name, _, status in statuses:
        by_template.setdefault(name, []).append(status)
    for versions in by_template.values():
        assert versions.count(WorkflowVersionStatus.ACTIVE) == 1
        assert versions[-1] == WorkflowVersionStatus.ACTIVE
    main = by_template[TEMPLATE_BY_KEY["main"].name]
    assert main[0] in (WorkflowVersionStatus.DEPRECATED, WorkflowVersionStatus.RETIRED)

    # Продукт во взаимодействии связан с программой. Без связи только один
    # сюжетный продукт.
    unlinked = await session.scalar(
        select(func.count())
        .select_from(InteractionProduct)
        .where(
            ~InteractionProduct.program_links.any(),
        )
    )
    assert unlinked == sum(len(plan.unlinked) for plan in STORIES)

    # Руководители и администратор вместе видят тревогу каждого вида,
    # и у руководителя команды они помещаются на главной.
    head, head_user = await _as(session, "orlova")
    other_head, other_head_user = await _as(session, "fedorov")
    admin, admin_user = await _as(session, "admin")
    for_head = await alerts.collect(session, head, head_user)
    for_other = await alerts.collect(session, other_head, other_head_user)
    for_admin = await alerts.collect(session, admin, admin_user)
    assert {alert.kind for alert in [*for_head, *for_other, *for_admin]} == set(AlertKind)
    assert len(for_head) <= dashboard.ALERTS_LIMIT, [alert.message for alert in for_head]
    # Технические очереди видит администратор, бизнес-тревоги руководитель.
    assert {alert.kind for alert in for_admin} >= {
        AlertKind.MAPPING_PENDING,
        AlertKind.INTEGRATION_FAILED,
        AlertKind.UNIVERSITY_PENDING,
    }

    # Главный герой показа: почти все сюжеты у него.
    petrov, petrov_user = await _as(session, "petrov")
    kinds = {alert.kind for alert in await alerts.collect(session, petrov, petrov_user)}
    assert kinds >= {
        AlertKind.CONTRACT_EXPIRING,
        AlertKind.LICENSE_EXPIRING,
        AlertKind.STAGE_STALE,
        AlertKind.PROCESS_BLOCKED,
        AlertKind.NO_DOCUMENTS,
    }
    view = await dashboard.build(session, petrov, petrov_user)
    assert view.next_steps
    assert (
        view.counters.open
        >= sum(1 for plan in STORIES if plan.manager == "petrov" and plan.template is not None)
        - 2
    )  # у Петрова есть и закрытые сюжеты

    # Действующие договоры подписаны и со сроком.
    active = await session.execute(
        select(Contract).where(Contract.status == ContractStatus.ACTIVE)
    )
    for contract in active.scalars():
        assert contract.signed_at and contract.valid_to, contract.number
        assert contract.valid_from <= contract.valid_to, contract.number

    # История идёт по порядку, текущий этап совпадает с последним переходом.
    instances = await session.execute(
        select(WorkflowInstance).options(selectinload(WorkflowInstance.events))
    )
    states: set[StageState] = set()
    outcomes: set[str | None] = set()
    for instance in instances.scalars():
        events = sorted(instance.events, key=lambda event: event.created_at)
        assert events[0].event_type == WorkflowEventType.CREATED
        outcomes.add(instance.outcome)
        if instance.status == InteractionStatus.DRAFT:
            assert instance.current_stage_id is None
            continue
        started = next(e for e in events if e.event_type == WorkflowEventType.STARTED)
        assert instance.started_at == started.created_at
        moves = [event for event in events if event.from_stage_id != event.to_stage_id]
        assert moves[-1].to_stage_id == instance.current_stage_id
        assert moves[-1].created_at == instance.current_stage_started_at
        if instance.status in (InteractionStatus.COMPLETED, InteractionStatus.CANCELLED):
            assert instance.outcome is not None and instance.closed_at is not None
            if instance.outcome != InteractionOutcome.SUCCESSFUL:
                assert instance.closure_reason is not None

        version = await workflow_service.load_version(session, instance.workflow_version_id)
        states |= set(
            workflow_service.compute_stage_states(version, instance, events).values()
        )
    # На схемах встречаются все пять состояний этапа.
    assert states == set(StageState)
    assert {InteractionOutcome.SUCCESSFUL, InteractionOutcome.UNSUCCESSFUL} <= outcomes

    # Отчёт строится по всему объёму, хвост сворачивается в «Прочие».
    # Фёдорову по сюжету временно открыта вся организация.
    fedorov, fedorov_user = await _as(session, "fedorov")
    report = await reports.build_report(session, ReportRequest(), fedorov, fedorov_user)
    assert report.totals.interactions == summary.interactions
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

    total = await session.scalar(select(func.count()).select_from(WorkflowInstance))
    assert total == summary.interactions + 40
    # У действующей версии по-прежнему одна на шаблон.
    active = await session.scalar(
        select(func.count())
        .select_from(WorkflowVersion)
        .where(WorkflowVersion.status == WorkflowVersionStatus.ACTIVE)
    )
    assert active == len(TEMPLATE_BY_KEY)
