"""Главная страница и контроль проблемных взаимодействий.

Часть правил зависит от времени - например, «этап не менялся 30 дней».
Такие ситуации создаются сдвигом даты прямо в базе: ждать месяц в тесте
нечем, а правило проверить надо.
"""

from datetime import date, timedelta

from httpx import AsyncClient
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine

from tests.conftest import (
    ADMIN,
    HEAD,
    MANAGER,
    OTHER_MANAGER,
    contract_payload,
    make_contract,
    make_interaction,
)


async def _age_current_stage(engine: AsyncEngine, days: int) -> None:
    """Сдвигает начало текущего этапа в прошлое."""
    async with engine.begin() as connection:
        await connection.execute(
            text(
                "UPDATE workflow_instances "
                "SET current_stage_started_at = now() - make_interval(days => :days)"
            ),
            {"days": days},
        )


def _kinds(alerts: list[dict]) -> set[str]:
    return {alert["kind"] for alert in alerts}


async def test_dashboard_counts_by_scope_and_role(
    client: AsyncClient, university: dict
) -> None:
    await make_interaction(client, university["id"], MANAGER)
    await make_interaction(client, university["id"], MANAGER, start=False)
    await make_interaction(client, university["id"], OTHER_MANAGER)

    mine = (await client.get("/api/v1/dashboard", headers=MANAGER)).json()
    assert mine["role"] == "manager"
    assert mine["scope"] == "own"
    assert mine["counters"]["open"] == 2
    assert mine["counters"]["drafts"] == 1
    assert mine["counters"]["in_progress"] == 1
    assert mine["team_load"] == []  # менеджеру сводка по команде не нужна
    assert mine["admin"] is None

    for_head = (await client.get("/api/v1/dashboard", headers=HEAD)).json()
    assert for_head["role"] == "head"
    assert for_head["scope"] == "team"
    assert for_head["counters"]["open"] == 3
    assert {item["open"] for item in for_head["team_load"]} == {1, 2}


async def test_next_steps_separate_status_stage_and_sla(
    client: AsyncClient, university: dict, engine: AsyncEngine
) -> None:
    await make_interaction(client, university["id"], MANAGER)
    await _age_current_stage(engine, 6)  # норма этапа - 7 дней

    steps = (await client.get("/api/v1/dashboard", headers=MANAGER)).json()["next_steps"]
    assert len(steps) == 1
    step = steps[0]
    assert step["status"] == "in_progress"
    assert step["stage_name"] == "Контакт"
    assert step["next_actions"]
    assert step["sla"]["days_on_stage"] == 6
    assert step["sla"]["state"] == "warning"  # использовано больше 75 % срока
    assert step["university"]["short_name"] is None or step["university"]["name"]


async def test_draft_without_process_is_reported(
    client: AsyncClient, university: dict
) -> None:
    await make_interaction(client, university["id"], MANAGER, start=False)

    alerts = (await client.get("/api/v1/dashboard/alerts", headers=MANAGER)).json()
    assert "process_not_started" in _kinds(alerts)


async def test_active_contract_without_scan_is_reported(
    client: AsyncClient, university: dict
) -> None:
    await make_contract(client, university["id"], MANAGER)
    alerts = (await client.get("/api/v1/dashboard/alerts", headers=MANAGER)).json()
    assert "no_documents" in _kinds(alerts)


async def test_stale_stage_is_reported_with_days(
    client: AsyncClient, university: dict, engine: AsyncEngine
) -> None:
    await make_interaction(client, university["id"], MANAGER)
    # У этапа «Контакт» норма 7 дней, сдвигаем начало на 30.
    await _age_current_stage(engine, 30)

    alerts = (
        await client.get("/api/v1/dashboard/alerts?kind=stage_stale", headers=MANAGER)
    ).json()
    assert len(alerts) == 1
    assert alerts[0]["days"] == 30
    assert alerts[0]["severity"] == "critical"  # просрочка больше двойной нормы
    assert "7 дн." in alerts[0]["message"]


async def test_blocked_process_is_critical(client: AsyncClient, university: dict) -> None:
    interaction = await make_interaction(client, university["id"], MANAGER)
    await client.post(
        f"/api/v1/interactions/{interaction['id']}/block",
        json={"reason": "Вуз взял паузу"},
        headers=MANAGER,
    )

    alerts = (await client.get("/api/v1/dashboard/alerts", headers=MANAGER)).json()
    blocked = next(a for a in alerts if a["kind"] == "process_blocked")
    assert blocked["severity"] == "critical"
    assert blocked["interaction_id"] == interaction["id"]
    assert "Вуз взял паузу" in blocked["message"]


async def test_head_control_queue_has_unassigned(
    client: AsyncClient, university: dict
) -> None:
    await make_interaction(client, university["id"], HEAD, manager_id=None)
    view = (await client.get("/api/v1/dashboard", headers=HEAD)).json()
    assert view["counters"]["unassigned"] == 1
    assert "unassigned" in {item["reason"] for item in view["control_queue"]}


async def test_expiring_contract_and_license(client: AsyncClient, university: dict) -> None:
    program = (
        await client.post("/api/v1/catalog/programs", json={"name": "Курс"}, headers=ADMIN)
    ).json()
    product = (
        await client.post(
            "/api/v1/catalog/products", json={"name": "Платформа"}, headers=ADMIN
        )
    ).json()
    await client.put(
        f"/api/v1/catalog/programs/{program['id']}/products",
        json={"product_ids": [product["id"]]},
        headers=HEAD,
    )
    interaction = await make_interaction(
        client, university["id"], MANAGER, program_ids=[program["id"]]
    )
    detail = (
        await client.get(f"/api/v1/interactions/{interaction['id']}", headers=MANAGER)
    ).json()
    link = (
        await client.post(
            f"/api/v1/interactions/{interaction['id']}/products",
            json={
                "product_id": product["id"],
                "program_link_ids": [detail["program_links"][0]["id"]],
            },
            headers=MANAGER,
        )
    ).json()
    await client.put(
        f"/api/v1/interactions/{interaction['id']}/contract",
        json=contract_payload(
            signed_at=str(date.today() - timedelta(days=300)),
            valid_from=str(date.today() - timedelta(days=300)),
            valid_to=str(date.today() + timedelta(days=10)),
        ),
        headers=MANAGER,
    )
    await client.post(
        f"/api/v1/interactions/{interaction['id']}/products/{link['id']}/licenses",
        json={"valid_to": str(date.today() - timedelta(days=5))},
        headers=MANAGER,
    )

    alerts = (await client.get("/api/v1/dashboard/alerts", headers=MANAGER)).json()
    by_kind = {alert["kind"]: alert for alert in alerts}

    assert by_kind["contract_expiring"]["days"] == 10
    assert by_kind["contract_expiring"]["severity"] == "warning"
    # Срок уже прошёл - это критично.
    assert by_kind["license_expiring"]["days"] == -5
    assert by_kind["license_expiring"]["severity"] == "critical"
    assert "истекла 5 дн. назад" in by_kind["license_expiring"]["message"]


async def test_alerts_respect_data_scope(client: AsyncClient, university: dict) -> None:
    await make_interaction(client, university["id"], OTHER_MANAGER, start=False)

    mine = (await client.get("/api/v1/dashboard/alerts", headers=MANAGER)).json()
    team = (await client.get("/api/v1/dashboard/alerts", headers=HEAD)).json()

    assert mine == []
    assert "process_not_started" in _kinds(team)


async def test_admin_home_is_technical(client: AsyncClient, university: dict) -> None:
    await make_interaction(client, university["id"], MANAGER)
    view = (await client.get("/api/v1/dashboard", headers=ADMIN)).json()
    assert view["role"] == "admin"
    assert view["scope"] == "none"
    assert view["admin"] is not None
    assert view["next_steps"] == []
    # Бизнес-данных администратор без области не видит.
    assert view["counters"]["open"] == 0
