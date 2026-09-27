"""Системные настройки, кэш выборок, сводка на главной, коды ошибок."""

from datetime import date, timedelta

from httpx import AsyncClient

from app.core.config import settings
from app.services import cache
from tests.conftest import ADMIN, HEAD, MANAGER, make_contract, make_interaction


async def test_settings_change_alert_norms(client: AsyncClient, university: dict) -> None:
    await make_contract(
        client, university["id"], MANAGER, valid_to=str(date.today() + timedelta(days=90))
    )

    def expiring(alerts: list[dict]) -> bool:
        return any(alert["kind"] == "contract_expiring" for alert in alerts)

    assert not expiring((await client.get("/api/v1/dashboard/alerts", headers=MANAGER)).json())

    denied = await client.put(
        "/api/v1/settings", json={"values": {"alert_expiring_days": 120}}, headers=HEAD
    )
    assert denied.status_code == 403
    saved = await client.put(
        "/api/v1/settings", json={"values": {"alert_expiring_days": 120}}, headers=ADMIN
    )
    assert saved.status_code == 200
    values = {item["key"]: item["value"] for item in saved.json()}
    assert values["alert_expiring_days"] == 120

    # Договор, до конца которого 90 дней, теперь требует действия.
    assert expiring((await client.get("/api/v1/dashboard/alerts", headers=MANAGER)).json())

    bad = await client.put(
        "/api/v1/settings", json={"values": {"alert_expiring_days": 0}}, headers=ADMIN
    )
    assert bad.status_code == 400


async def test_cache_is_invalidated_by_changes(client: AsyncClient, university: dict) -> None:
    settings.cache_ttl_seconds = 60
    try:
        await make_interaction(client, university["id"], MANAGER)
        first = (await client.get("/api/v1/dashboard", headers=MANAGER)).json()
        again = (await client.get("/api/v1/dashboard", headers=MANAGER)).json()
        # Второй ответ - из кэша: то же время построения.
        assert again["generated_at"] == first["generated_at"]
        assert cache.stats()["hits"] >= 1

        # Любое сохранение увеличивает версию данных - кэш больше не совпадает.
        await make_interaction(client, university["id"], MANAGER)
        fresh = (await client.get("/api/v1/dashboard", headers=MANAGER)).json()
        assert fresh["counters"]["open"] == 2
    finally:
        settings.cache_ttl_seconds = 0


async def test_alert_counter_is_not_capped(client: AsyncClient, university: dict) -> None:
    # 25 действующих договоров без скана - 25 тревог.
    for _ in range(25):
        await make_contract(client, university["id"], HEAD)
    dashboard = (await client.get("/api/v1/dashboard", headers=HEAD)).json()
    assert len(dashboard["alerts"]) == 20  # список на главной ограничен
    assert dashboard["counters"]["alerts"] == 25  # а счётчик - нет
    assert dashboard["alerts_summary"]["no_documents"] == 25


async def test_next_steps_for_manager(
    client: AsyncClient, university: dict, workflow_version: dict
) -> None:
    await make_interaction(
        client, university["id"], MANAGER, template_id=workflow_version["template_id"]
    )
    dashboard = (await client.get("/api/v1/dashboard", headers=MANAGER)).json()
    step = dashboard["next_steps"][0]
    assert step["stage_name"] == "Контакт"
    assert step["next_actions"] == ["Встреча"]  # у перехода нет названия - берётся этап
    assert dashboard["admin"] is None


async def test_admin_dashboard_has_system_block(client: AsyncClient) -> None:
    dashboard = (await client.get("/api/v1/dashboard", headers=ADMIN)).json()
    assert dashboard["admin"]["users_total"] >= 1
    assert dashboard["admin"]["settings"]["alert_default_sla_days"] == 14


async def test_meta_auth_in_dev_mode(client: AsyncClient) -> None:
    await client.get("/api/v1/me", headers=MANAGER)
    config = (await client.get("/api/v1/meta/auth")).json()
    assert config["mode"] == "dev"
    assert {"username": "petrov", "full_name": "petrov", "roles": ["manager"]} in config[
        "demo_accounts"
    ]


async def test_validation_errors_have_code(client: AsyncClient) -> None:
    response = await client.post("/api/v1/interactions", json={}, headers=MANAGER)
    assert response.status_code == 422
    body = response.json()
    assert body["code"] == "validation_error"
    # Нет обязательного поля - ошибка формата: общий текст, подробности по полям.
    assert body["message"] == "Запрос не прошёл проверку"
    assert body["details"]["errors"]
