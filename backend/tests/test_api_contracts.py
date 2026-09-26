"""Договоры: реестр, карточка и права на уровне записей."""

from httpx import AsyncClient

from tests.conftest import ADMIN, HEAD, MANAGER, OTHER_MANAGER, make_contract


async def test_manager_sees_only_own_contracts(client: AsyncClient, university: dict) -> None:
    mine = await make_contract(client, university["id"], MANAGER)
    await make_contract(client, university["id"], OTHER_MANAGER)

    listing = (await client.get("/api/v1/contracts", headers=MANAGER)).json()
    assert [item["id"] for item in listing["items"]] == [mine["id"]]
    assert listing["total"] == 1

    # Руководитель видит оба договора.
    for_head = (await client.get("/api/v1/contracts", headers=HEAD)).json()
    assert for_head["total"] == 2


async def test_foreign_contract_is_forbidden(client: AsyncClient, university: dict) -> None:
    foreign = await make_contract(client, university["id"], OTHER_MANAGER)

    response = await client.get(f"/api/v1/contracts/{foreign['id']}", headers=MANAGER)
    assert response.status_code == 403
    assert response.json()["code"] == "forbidden"


async def test_unknown_contract_returns_error_code(client: AsyncClient) -> None:
    response = await client.get(
        "/api/v1/contracts/00000000-0000-0000-0000-000000000000", headers=MANAGER
    )
    assert response.status_code == 404
    body = response.json()
    assert body["code"] == "not_found"
    assert body["message"]


async def test_manager_cannot_reassign_responsible(
    client: AsyncClient, university: dict
) -> None:
    contract = await make_contract(client, university["id"], MANAGER)

    response = await client.patch(
        f"/api/v1/contracts/{contract['id']}",
        json={"manager_id": None},
        headers=MANAGER,
    )
    assert response.status_code == 403

    allowed = await client.patch(
        f"/api/v1/contracts/{contract['id']}",
        json={"comment": "Уточнили состав"},
        headers=MANAGER,
    )
    assert allowed.status_code == 200
    assert allowed.json()["comment"] == "Уточнили состав"


async def test_changes_get_into_audit_log(client: AsyncClient, university: dict) -> None:
    contract = await make_contract(client, university["id"], ADMIN)

    entries = (
        await client.get(
            "/api/v1/audit",
            params={"entity_type": "contracts", "entity_id": contract["id"]},
            headers=ADMIN,
        )
    ).json()
    assert entries["total"] >= 1
    entry = entries["items"][0]
    assert entry["action"] == "create"
    assert entry["after_data"]["number"] == contract["number"]


async def test_audit_names_author_even_when_role_check_is_enough(
    client: AsyncClient, university: dict
) -> None:
    # Назначение ответственного проверяет только роль из токена - автор
    # изменения всё равно должен попасть в журнал.
    manager = (await client.get("/api/v1/me", headers=MANAGER)).json()
    response = await client.patch(
        f"/api/v1/universities/{university['id']}",
        json={"manager_id": manager["id"]},
        headers=HEAD,
    )
    assert response.status_code == 200, response.text

    entries = (
        await client.get(
            "/api/v1/audit",
            params={"entity_type": "universities", "entity_id": university["id"]},
            headers=ADMIN,
        )
    ).json()
    update = next(item for item in entries["items"] if item["action"] == "update")
    head = (await client.get("/api/v1/me", headers=HEAD)).json()
    assert update["user_id"] == head["id"]
    assert update["user_name"] == head["full_name"]


async def test_audit_is_closed_for_manager(client: AsyncClient) -> None:
    response = await client.get("/api/v1/audit", headers=MANAGER)
    assert response.status_code == 403
