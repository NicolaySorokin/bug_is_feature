"""Уведомления колокольчика: отметка «прочитано».

Уведомление - текущая проблема, а не запись. Прочитанное снимается со
счётчика, но возвращается, если проблема стала серьёзнее; отметки
о решённых проблемах забываются.
"""

from httpx import AsyncClient
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine

from app.enums import AlertSeverity
from app.services.alert_marks import still_read
from tests.conftest import HEAD, MANAGER, make_interaction

ALERTS = "/api/v1/dashboard/alerts"


async def _age_current_stage(engine: AsyncEngine, days: int) -> None:
    async with engine.begin() as connection:
        await connection.execute(
            text(
                "UPDATE workflow_instances "
                "SET current_stage_started_at = now() - make_interval(days => :days) "
                "WHERE status = 'in_progress'"
            ),
            {"days": days},
        )


async def _alerts(client: AsyncClient, headers: dict) -> dict[str, dict]:
    response = await client.get(ALERTS, headers=headers)
    assert response.status_code == 200, response.text
    return {alert["kind"]: alert for alert in response.json()}


async def _marks(engine: AsyncEngine) -> int:
    async with engine.connect() as connection:
        return (
            await connection.execute(text("SELECT count(*) FROM alert_marks"))
        ).scalar_one()


async def test_read_one_and_all(
    client: AsyncClient, university: dict, engine: AsyncEngine
) -> None:
    await make_interaction(client, university["id"], MANAGER, start=False)
    await make_interaction(client, university["id"], MANAGER)
    # У этапа «Контакт» норма 7 дней: 10 дней - просрочка, но ещё не критичная.
    await _age_current_stage(engine, 10)

    alerts = await _alerts(client, MANAGER)
    draft, stale = alerts["process_not_started"], alerts["stage_stale"]
    assert not draft["is_read"] and not stale["is_read"]
    assert draft["key"] and draft["key"] != stale["key"]

    response = await client.post(
        f"{ALERTS}/read", json={"keys": [draft["key"]]}, headers=MANAGER
    )
    assert response.status_code == 204, response.text
    alerts = await _alerts(client, MANAGER)
    assert alerts["process_not_started"]["is_read"]
    assert not alerts["stage_stale"]["is_read"]

    # Отметки у каждого сотрудника свои.
    assert not (await _alerts(client, HEAD))["process_not_started"]["is_read"]

    response = await client.post(f"{ALERTS}/read-all", headers=MANAGER)
    assert response.status_code == 204, response.text
    assert all(alert["is_read"] for alert in (await _alerts(client, MANAGER)).values())
    # И на главной видно, что уведомление прочитано, - сама проблема остаётся.
    dashboard = (await client.get("/api/v1/dashboard", headers=MANAGER)).json()
    assert dashboard["alerts"] and all(alert["is_read"] for alert in dashboard["alerts"])


async def test_worse_problem_is_new_again(
    client: AsyncClient, university: dict, engine: AsyncEngine
) -> None:
    await make_interaction(client, university["id"], MANAGER)
    await _age_current_stage(engine, 10)
    stale = (await _alerts(client, MANAGER))["stage_stale"]
    assert stale["severity"] == "warning"
    await client.post(f"{ALERTS}/read", json={"keys": [stale["key"]]}, headers=MANAGER)
    assert (await _alerts(client, MANAGER))["stage_stale"]["is_read"]

    # Просрочка больше двойной нормы - критично, и уведомление снова новое.
    await _age_current_stage(engine, 30)
    worse = (await _alerts(client, MANAGER))["stage_stale"]
    assert worse["key"] == stale["key"]
    assert worse["severity"] == "critical"
    assert not worse["is_read"]


async def test_solved_problem_is_forgotten(
    client: AsyncClient, university: dict, engine: AsyncEngine
) -> None:
    draft = await make_interaction(client, university["id"], MANAGER, start=False)
    key = (await _alerts(client, MANAGER))["process_not_started"]["key"]
    await client.post(f"{ALERTS}/read", json={"keys": [key]}, headers=MANAGER)
    assert await _marks(engine) == 1

    started = await client.post(f"/api/v1/interactions/{draft['id']}/start", headers=MANAGER)
    assert started.status_code == 200, started.text
    assert "process_not_started" not in await _alerts(client, MANAGER)
    assert await _marks(engine) == 0


async def test_unknown_keys_are_ignored(client: AsyncClient, engine: AsyncEngine) -> None:
    response = await client.post(
        f"{ALERTS}/read", json={"keys": ["stage_stale:нет-такого:"]}, headers=MANAGER
    )
    assert response.status_code == 204, response.text
    assert await _marks(engine) == 0
    empty = await client.post(f"{ALERTS}/read", json={"keys": []}, headers=MANAGER)
    assert empty.status_code == 422


def test_read_stays_read_until_worse() -> None:
    assert still_read("warning", AlertSeverity.WARNING)
    assert still_read("critical", AlertSeverity.WARNING)
    assert not still_read("warning", AlertSeverity.CRITICAL)
    assert not still_read("info", AlertSeverity.WARNING)
    assert not still_read("unknown", AlertSeverity.INFO)
