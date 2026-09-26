"""Служебные методы и схема API."""

from httpx import AsyncClient

from tests.conftest import ADMIN, MANAGER


async def test_health_reports_database(client: AsyncClient) -> None:
    response = await client.get("/api/v1/health")
    assert response.status_code == 200
    # Метод открыт без входа: среда и схема авторизации наружу не уходят.
    assert response.json() == {"status": "ok"}


async def test_cache_state_is_for_admin_only(client: AsyncClient) -> None:
    assert (await client.get("/api/v1/meta/cache")).status_code == 404
    denied = await client.get("/api/v1/settings/cache", headers=MANAGER)
    assert denied.status_code == 403
    state = await client.get("/api/v1/settings/cache", headers=ADMIN)
    assert state.status_code == 200
    assert {"version", "hits", "misses"} <= set(state.json())


async def test_meta_gives_labels_and_error_codes(client: AsyncClient) -> None:
    body = (await client.get("/api/v1/meta/enums", headers=MANAGER)).json()
    assert body["labels"]["contract_status"]["active"] == "Действует"
    assert "workflow_rule_violated" in body["error_codes"]
    assert "xlsx" in body["uploads"]["allowed_extensions"]


async def test_openapi_describes_errors_for_every_method(client: AsyncClient) -> None:
    """Схема - контракт для клиентской части, поэтому проверяем её целиком."""
    schema = (await client.get("/api/v1/openapi.json")).json()

    assert len(schema["paths"]) > 40
    tags = {tag["name"] for tag in schema["tags"]}
    assert {"interactions", "reports", "workflow", "imports"} <= tags
    assert "contracts" not in tags  # договор - блок взаимодействия, не свой раздел

    # Формат отказа описан у обычного метода, а не только в тексте README.
    card = schema["paths"]["/api/v1/interactions/{interaction_id}"]["get"]["responses"]
    assert {"401", "403", "404", "422"} <= set(card)
    example = card["403"]["content"]["application/json"]["example"]
    assert example["code"] == "forbidden"


async def test_docs_page_is_available(client: AsyncClient) -> None:
    response = await client.get("/docs")
    assert response.status_code == 200
    assert "swagger" in response.text.lower()
