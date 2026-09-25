"""Ролевая модель ТЗ: права пользователей и доступ к данным.

* руководитель назначает, меняет и снимает ответственных за вузы;
* администратор управляет правами: отключает учётные записи, открывает
  менеджеру чужие вузы или все договоры;
* менеджер видит только свою зону ответственности.
"""

from httpx import AsyncClient

from tests.conftest import ADMIN, HEAD, MANAGER, OTHER_MANAGER, make_contract


async def _user_id(client: AsyncClient, headers: dict) -> str:
    return (await client.get("/api/v1/me", headers=headers)).json()["id"]


async def test_me_shows_roles_and_scope(client: AsyncClient) -> None:
    me = (await client.get("/api/v1/me", headers=MANAGER)).json()
    assert me["roles"] == ["manager"]
    assert me["sees_all_contracts"] is False

    head = (await client.get("/api/v1/me", headers=HEAD)).json()
    assert head["sees_all_contracts"] is True


async def test_users_list_filters_by_role(client: AsyncClient) -> None:
    for headers in (MANAGER, OTHER_MANAGER, HEAD):
        await client.get("/api/v1/me", headers=headers)

    heads = (
        await client.get("/api/v1/users", params={"role": "head"}, headers=MANAGER)
    ).json()
    assert [item["username"] for item in heads["items"]] == ["orlova"]
    managers = (
        await client.get("/api/v1/users", params={"role": "manager"}, headers=MANAGER)
    ).json()
    assert managers["total"] == 3  # у руководителя тоже есть роль manager


async def test_head_assigns_responsible_for_university(
    client: AsyncClient, university: dict
) -> None:
    petrov = await _user_id(client, MANAGER)

    # Менеджер сам себя за вуз не закрепит - это право руководителя.
    denied = await client.patch(
        f"/api/v1/universities/{university['id']}",
        json={"manager_id": petrov},
        headers=MANAGER,
    )
    assert denied.status_code == 403

    assigned = await client.patch(
        f"/api/v1/universities/{university['id']}", json={"manager_id": petrov}, headers=HEAD
    )
    assert assigned.status_code == 200
    assert assigned.json()["manager"]["username"] == "petrov"

    # Закрепление за вузом открывает менеджеру договоры вуза, даже чужие.
    foreign = await make_contract(client, university["id"], OTHER_MANAGER)
    visible = await client.get(f"/api/v1/contracts/{foreign['id']}", headers=MANAGER)
    assert visible.status_code == 200

    removed = await client.patch(
        f"/api/v1/universities/{university['id']}", json={"manager_id": None}, headers=HEAD
    )
    assert removed.json()["manager_id"] is None
    hidden = await client.get(f"/api/v1/contracts/{foreign['id']}", headers=MANAGER)
    assert hidden.status_code == 403


async def test_head_reassigns_contract(client: AsyncClient, university: dict) -> None:
    contract = await make_contract(client, university["id"], MANAGER)
    ivanova = await _user_id(client, OTHER_MANAGER)

    response = await client.patch(
        f"/api/v1/contracts/{contract['id']}", json={"manager_id": ivanova}, headers=HEAD
    )
    assert response.status_code == 200
    assert response.json()["manager"]["username"] == "ivanova"
    # Договор ушёл к другому менеджеру - прежний его больше не видит.
    gone = await client.get(f"/api/v1/contracts/{contract['id']}", headers=MANAGER)
    assert gone.status_code == 403


async def test_manager_creates_contract_only_for_himself(
    client: AsyncClient, university: dict
) -> None:
    ivanova = await _user_id(client, OTHER_MANAGER)
    response = await client.post(
        "/api/v1/contracts",
        json={"university_id": university["id"], "number": "ДГ-1", "manager_id": ivanova},
        headers=MANAGER,
    )
    assert response.status_code == 403


async def test_admin_grants_university_access(client: AsyncClient, university: dict) -> None:
    foreign = await make_contract(client, university["id"], OTHER_MANAGER)
    petrov = await _user_id(client, MANAGER)
    assert (
        await client.get(f"/api/v1/contracts/{foreign['id']}", headers=MANAGER)
    ).status_code == 403

    updated = await client.patch(
        f"/api/v1/users/{petrov}", json={"university_ids": [university["id"]]}, headers=ADMIN
    )
    assert updated.status_code == 200
    assert updated.json()["university_ids"] == [university["id"]]

    listing = (await client.get("/api/v1/contracts", headers=MANAGER)).json()
    assert [item["id"] for item in listing["items"]] == [foreign["id"]]


async def test_admin_opens_all_contracts(client: AsyncClient, university: dict) -> None:
    await make_contract(client, university["id"], OTHER_MANAGER)
    petrov = await _user_id(client, MANAGER)
    assert (await client.get("/api/v1/contracts", headers=MANAGER)).json()["total"] == 0

    await client.patch(f"/api/v1/users/{petrov}", json={"data_scope": "all"}, headers=ADMIN)
    assert (await client.get("/api/v1/contracts", headers=MANAGER)).json()["total"] == 1
    me = (await client.get("/api/v1/me", headers=MANAGER)).json()
    assert me["sees_all_contracts"] is True


async def test_disabled_user_is_locked_out(client: AsyncClient) -> None:
    petrov = await _user_id(client, MANAGER)
    await client.patch(f"/api/v1/users/{petrov}", json={"is_active": False}, headers=ADMIN)

    response = await client.get("/api/v1/contracts", headers=MANAGER)
    assert response.status_code == 403
    assert response.json()["code"] == "account_disabled"


async def test_admin_cannot_lock_himself_out(client: AsyncClient) -> None:
    admin = await _user_id(client, ADMIN)
    response = await client.patch(
        f"/api/v1/users/{admin}", json={"is_active": False}, headers=ADMIN
    )
    assert response.status_code == 409
    roles = await client.patch(
        f"/api/v1/users/{admin}", json={"roles": ["manager"]}, headers=ADMIN
    )
    assert roles.status_code == 409


async def test_user_management_is_admin_only(client: AsyncClient) -> None:
    petrov = await _user_id(client, MANAGER)
    for headers in (MANAGER, HEAD):
        response = await client.patch(
            f"/api/v1/users/{petrov}", json={"data_scope": "all"}, headers=headers
        )
        assert response.status_code == 403
    # Свою карточку видит каждый, чужую - только администратор.
    assert (await client.get(f"/api/v1/users/{petrov}", headers=MANAGER)).status_code == 200
    assert (await client.get(f"/api/v1/users/{petrov}", headers=HEAD)).status_code == 403


async def test_admin_creates_user_without_keycloak(client: AsyncClient) -> None:
    created = await client.post(
        "/api/v1/users",
        json={
            "username": "novikova",
            "full_name": "Новикова Ольга Ивановна",
            "roles": ["manager"],
        },
        headers=ADMIN,
    )
    assert created.status_code == 201, created.text
    assert created.json()["keycloak_id"] == "dev:novikova"

    # Под заглушкой новый сотрудник входит своим логином - это та же карточка.
    me = (
        await client.get(
            "/api/v1/me", headers={"X-Dev-User": "novikova", "X-Dev-Roles": "manager"}
        )
    ).json()
    assert me["id"] == created.json()["id"]
    assert me["full_name"] == "Новикова Ольга Ивановна"

    duplicate = await client.post(
        "/api/v1/users",
        json={"username": "novikova", "full_name": "Кто-то", "roles": ["manager"]},
        headers=ADMIN,
    )
    assert duplicate.status_code == 409


async def test_university_catalog_is_edited_by_staff(client: AsyncClient) -> None:
    denied = await client.post(
        "/api/v1/universities", json={"name": "Новый вуз"}, headers=MANAGER
    )
    assert denied.status_code == 403
    created = await client.post(
        "/api/v1/universities", json={"name": "Новый вуз"}, headers=HEAD
    )
    assert created.status_code == 201
    duplicate = await client.post(
        "/api/v1/universities", json={"name": "новый вуз"}, headers=HEAD
    )
    assert duplicate.status_code == 409


async def test_contacts_are_edited_by_responsible_manager(
    client: AsyncClient, university: dict
) -> None:
    url = f"/api/v1/universities/{university['id']}/contacts"
    denied = await client.post(url, json={"full_name": "Гусева Анна"}, headers=MANAGER)
    assert denied.status_code == 403

    petrov = await _user_id(client, MANAGER)
    await client.patch(
        f"/api/v1/universities/{university['id']}", json={"manager_id": petrov}, headers=HEAD
    )
    contact = (
        await client.post(url, json={"full_name": "Гусева Анна"}, headers=MANAGER)
    ).json()
    renamed = await client.patch(
        f"{url}/{contact['id']}", json={"position": "Проректор"}, headers=MANAGER
    )
    assert renamed.json()["position"] == "Проректор"
    assert (await client.delete(f"{url}/{contact['id']}", headers=MANAGER)).status_code == 204


async def test_university_with_contracts_is_not_deleted(
    client: AsyncClient, university: dict
) -> None:
    await make_contract(client, university["id"], MANAGER)
    response = await client.delete(f"/api/v1/universities/{university['id']}", headers=ADMIN)
    assert response.status_code == 409
    assert "архив" in response.json()["message"]
