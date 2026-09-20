"""Главная страница и контроль проблемных процессов.

Часть правил зависит от времени - например, «этап не менялся 30 дней».
Такие ситуации создаются сдвигом даты прямо в базе: ждать месяц в тесте
нечем, а правило проверить надо.
"""

from datetime import date, timedelta

from httpx import AsyncClient
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine

from tests.conftest import ADMIN, HEAD, MANAGER, OTHER_MANAGER, make_contract


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


async def test_dashboard_counts_and_role(client: AsyncClient, university: dict) -> None:
    await make_contract(client, university["id"], MANAGER, status="active")
    await make_contract(client, university["id"], MANAGER, status="draft")
    await make_contract(client, university["id"], OTHER_MANAGER, status="active")

    mine = (await client.get("/api/v1/dashboard", headers=MANAGER)).json()
    assert mine["role"] == "manager"
    assert mine["counters"]["contracts"] == 2
    assert mine["counters"]["my_contracts"] == 2
    assert mine["counters"]["contracts_active"] == 1
    assert mine["manager_load"] == []  # менеджеру сводка по команде не нужна

    for_head = (await client.get("/api/v1/dashboard", headers=HEAD)).json()
    assert for_head["role"] == "head"
    assert for_head["counters"]["contracts"] == 3
    assert for_head["counters"]["my_contracts"] == 0
    assert {item["contracts"] for item in for_head["manager_load"]} == {1, 2}


async def test_contract_without_process_and_documents(
    client: AsyncClient, university: dict
) -> None:
    await make_contract(client, university["id"], MANAGER, status="active")

    alerts = (await client.get("/api/v1/dashboard/alerts", headers=MANAGER)).json()
    assert {"process_not_started", "no_documents"} <= _kinds(alerts)


async def test_stale_stage_is_reported_with_days(
    client: AsyncClient, university: dict, workflow_version: dict, engine: AsyncEngine
) -> None:
    contract = await make_contract(client, university["id"], MANAGER)
    await client.post(
        f"/api/v1/contracts/{contract['id']}/workflow",
        json={"template_id": workflow_version["template_id"]},
        headers=MANAGER,
    )
    # У этапа «Контакт» норма 7 дней, сдвигаем начало на 30.
    await _age_current_stage(engine, 30)

    alerts = (
        await client.get("/api/v1/dashboard/alerts?kind=stage_stale", headers=MANAGER)
    ).json()
    assert len(alerts) == 1
    assert alerts[0]["days"] == 30
    assert alerts[0]["severity"] == "critical"  # просрочка больше двойной нормы
    assert "7 дн." in alerts[0]["message"]


async def test_blocked_process_is_critical(
    client: AsyncClient, university: dict, workflow_version: dict
) -> None:
    contract = await make_contract(client, university["id"], MANAGER)
    view = (
        await client.post(
            f"/api/v1/contracts/{contract['id']}/workflow",
            json={"template_id": workflow_version["template_id"]},
            headers=MANAGER,
        )
    ).json()
    await client.post(
        f"/api/v1/workflow/instances/{view['id']}/block",
        json={"reason": "Вуз взял паузу"},
        headers=MANAGER,
    )

    alerts = (await client.get("/api/v1/dashboard/alerts", headers=MANAGER)).json()
    blocked = next(a for a in alerts if a["kind"] == "process_blocked")
    assert blocked["severity"] == "critical"
    assert blocked["contract_number"] == contract["number"]


async def test_expiring_contract_and_license(
    client: AsyncClient, university: dict
) -> None:
    product = (
        await client.post(
            "/api/v1/catalog/products", json={"name": "Платформа"}, headers=ADMIN
        )
    ).json()
    contract = await make_contract(
        client,
        university["id"],
        MANAGER,
        status="active",
        valid_to=str(date.today() + timedelta(days=10)),
        product_ids=[product["id"]],
    )
    detail = (
        await client.get(f"/api/v1/contracts/{contract['id']}", headers=MANAGER)
    ).json()
    await client.post(
        f"/api/v1/contracts/{contract['id']}/products/{detail['products'][0]['id']}/licenses",
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


async def test_alerts_respect_record_level_rights(
    client: AsyncClient, university: dict
) -> None:
    await make_contract(client, university["id"], OTHER_MANAGER, status="active")

    mine = (await client.get("/api/v1/dashboard/alerts", headers=MANAGER)).json()
    all_alerts = (await client.get("/api/v1/dashboard/alerts", headers=HEAD)).json()

    assert mine == []
    assert all_alerts
