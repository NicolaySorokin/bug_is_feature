"""Обмен с LMS и сайтом на тестовых ответах адаптеров."""

import logging
import re
from pathlib import Path

import httpx
import pytest
from httpx import AsyncClient

from app.core.errors import AppError, ErrorCode
from app.services.integrations import base
from tests.conftest import ADMIN, HEAD, MANAGER


@pytest.fixture(autouse=True)
def stable_fixtures(monkeypatch: pytest.MonkeyPatch) -> None:
    """Свои ответы LMS и сайта: демонстрационные растут вместе с демоданными."""
    monkeypatch.setattr(base, "FIXTURES", Path(__file__).parent / "fixtures" / "integrations")


async def test_sources_are_registered_with_fixtures(client: AsyncClient) -> None:
    sources = (await client.get("/api/v1/integrations/sources", headers=ADMIN)).json()
    codes = {source["code"] for source in sources}
    assert codes == {"lms", "site"}
    # Адрес внешней системы не задан, работаем на тестовых данных.
    assert all(source["uses_fixture"] for source in sources)


async def test_integration_log_is_not_for_business_roles(client: AsyncClient) -> None:
    """Технический журнал обмена видят администратор и владельцы отдельного права."""
    for headers in (MANAGER, HEAD):
        response = await client.get("/api/v1/integrations/runs", headers=headers)
        assert response.status_code == 403


async def _interactions(client: AsyncClient) -> dict:
    return (await client.get("/api/v1/interactions", headers=HEAD)).json()


async def test_new_universities_wait_for_confirmation(
    client: AsyncClient, workflow_version: dict
) -> None:
    runs = (await client.post("/api/v1/integrations/sync", headers=ADMIN)).json()
    assert runs[0]["source_code"] == "lms"
    assert runs[0]["status"] == "success"
    assert runs[0]["records_created"] > 0

    programs = (await client.get("/api/v1/catalog/programs", headers=ADMIN)).json()
    assert "Инженер DevOps" in {program["name"] for program in programs}

    # Вузы с сайта идут на проверку, заявки по ним ждут подтверждения.
    pending = (
        await client.get("/api/v1/universities", params={"status": "pending"}, headers=HEAD)
    ).json()
    assert pending["total"] == 3
    assert all(item["origin"] == "site" for item in pending["items"])
    assert runs[1]["records_pending"] == 2
    assert (await _interactions(client))["total"] == 0

    for item in pending["items"]:
        confirmed = await client.post(
            f"/api/v1/universities/{item['id']}/confirm", headers=HEAD
        )
        assert confirmed.status_code == 200

    # Заявки вузов стали взаимодействиями-черновиками: процесс запускает
    # ответственный, договор интеграция не создаёт.
    await client.post("/api/v1/integrations/sources/site/sync", headers=ADMIN)
    interactions = await _interactions(client)
    assert interactions["total"] == 2
    for item in interactions["items"]:
        assert item["source"] == "site"
        assert item["status"] == "draft"
        assert item["contract"] is None
    assert {tuple(sorted(item["programs"])) for item in interactions["items"]} == {
        ("Python-разработчик", "Инженер DevOps"),
        ("Специалист по информационной безопасности",),
    }


async def test_repeated_sync_does_not_duplicate(
    client: AsyncClient, workflow_version: dict
) -> None:
    await client.post("/api/v1/integrations/sync", headers=ADMIN)
    pending = (
        await client.get("/api/v1/universities", params={"status": "pending"}, headers=HEAD)
    ).json()
    for item in pending["items"]:
        await client.post(f"/api/v1/universities/{item['id']}/confirm", headers=HEAD)
    await client.post("/api/v1/integrations/sync", headers=ADMIN)
    runs = (await client.post("/api/v1/integrations/sync", headers=ADMIN)).json()

    assert all(run["records_created"] == 0 for run in runs)
    assert all(run["records_updated"] > 0 for run in runs)
    assert (await _interactions(client))["total"] == 2


async def test_same_name_goes_to_mapping_queue(
    client: AsyncClient, workflow_version: dict
) -> None:
    """Запись без связи по одному названию не сопоставляется, решает администратор."""
    existing = await client.post(
        "/api/v1/universities",
        json={"name": "Новосибирский государственный технический университет"},
        headers=HEAD,
    )
    assert existing.status_code == 201
    await client.post("/api/v1/integrations/sources/site/sync", headers=ADMIN)

    queue = (await client.get("/api/v1/integrations/mappings", headers=ADMIN)).json()
    mapping = next(item for item in queue if item["entity_type"] == "university")
    assert mapping["status"] == "pending"
    assert mapping["suggested_entity_id"] == existing.json()["id"]

    denied = await client.post(
        f"/api/v1/integrations/mappings/{mapping['id']}/resolve",
        json={"entity_id": existing.json()["id"]},
        headers=HEAD,
    )
    assert denied.status_code == 403
    resolved = await client.post(
        f"/api/v1/integrations/mappings/{mapping['id']}/resolve",
        json={"entity_id": existing.json()["id"]},
        headers=ADMIN,
    )
    assert resolved.status_code == 200, resolved.text
    assert resolved.json()["status"] == "resolved"

    # Следующий обмен находит вуз по созданной связи и не плодит дубль.
    await client.post("/api/v1/integrations/sources/site/sync", headers=ADMIN)
    same = (
        await client.get(
            "/api/v1/universities",
            params={"search": "Новосибирский"},
            headers=HEAD,
        )
    ).json()
    assert same["total"] == 1


async def test_runs_are_written_to_journal(
    client: AsyncClient, workflow_version: dict
) -> None:
    await client.post("/api/v1/integrations/sources/lms/sync", headers=ADMIN)

    journal = (
        await client.get("/api/v1/integrations/runs", params={"source": "lms"}, headers=ADMIN)
    ).json()
    assert len(journal) == 1
    assert journal[0]["status"] == "success"
    assert journal[0]["finished_at"] is not None
    assert journal[0]["trigger"] == "manual"

    run = (
        await client.get(f"/api/v1/integrations/runs/{journal[0]['id']}", headers=ADMIN)
    ).json()
    assert run["errors"] == []


async def test_sync_permission_is_granted_separately(client: AsyncClient) -> None:
    denied = await client.post("/api/v1/integrations/sync", headers=HEAD)
    assert denied.status_code == 403

    orlova = (await client.get("/api/v1/me", headers=HEAD)).json()
    await client.patch(
        f"/api/v1/users/{orlova['id']}",
        json={"permissions": ["sync_integrations"]},
        headers=ADMIN,
    )
    allowed = await client.post("/api/v1/integrations/sources/lms/sync", headers=HEAD)
    assert allowed.status_code == 200, allowed.text


async def test_disabled_source_is_not_synced(client: AsyncClient) -> None:
    await client.patch(
        "/api/v1/integrations/sources/lms",
        json={"is_enabled": False},
        headers=ADMIN,
    )
    response = await client.post("/api/v1/integrations/sources/lms/sync", headers=ADMIN)
    assert response.status_code == 400
    assert response.json()["code"] == "integration_failed"


async def test_manager_cannot_start_sync(client: AsyncClient) -> None:
    response = await client.post("/api/v1/integrations/sync", headers=MANAGER)
    assert response.status_code == 403


def _unreachable(request: httpx.Request) -> httpx.Response:
    raise httpx.ConnectError("Name or service not known", request=request)


@pytest.mark.parametrize(
    ("respond", "reason"),
    [
        (lambda _: httpx.Response(502), "ответ 502"),
        (lambda _: httpx.Response(401), "ответ 401"),
        (lambda _: httpx.Response(200, text="<html>не JSON</html>"), "не в формате JSON"),
        (lambda request: _unreachable(request), "нет связи"),
    ],
)
async def test_external_errors_are_readable(
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
    respond: object,
    reason: str,
) -> None:
    """Сотрудник видит одну понятную фразу без кодов ответа и адресов."""
    real_client = httpx.AsyncClient

    def client_with_mock(**kwargs: object) -> httpx.AsyncClient:
        return real_client(transport=httpx.MockTransport(respond), **kwargs)

    monkeypatch.setattr(base.httpx, "AsyncClient", client_with_mock)
    monkeypatch.setattr(base, "FETCH_BACKOFF_SECONDS", (0.0,))
    caplog.set_level(logging.WARNING, logger=base.__name__)
    with pytest.raises(AppError) as error:
        await base.fetch_json("https://lms.internal.example/api/v1/programs", "token")

    assert error.value.message == base.UNAVAILABLE_MESSAGE
    assert not re.search(r"\d", error.value.message)
    assert error.value.code == ErrorCode.INTEGRATION_FAILED
    assert reason in caplog.text
    assert "lms.internal.example" in caplog.text


async def test_sync_all_skips_disabled_source(client: AsyncClient) -> None:
    """«Синхронизировать всё» обменивается с включёнными источниками, а не падает."""
    await client.patch(
        "/api/v1/integrations/sources/lms", json={"is_enabled": False}, headers=ADMIN
    )
    response = await client.post("/api/v1/integrations/sync", headers=ADMIN)
    assert response.status_code == 200, response.text
    assert [run["source_code"] for run in response.json()] == ["site"]
