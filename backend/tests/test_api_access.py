"""Ролевая модель: роли, права и область данных разделены.

* роли не наследуются: руководитель не получает права менеджера,
  администратор - права руководителя;
* область данных (свои / команда / все / никаких) задаётся по ролям или
  явно администратором, в том числе временно - со сроком и основанием;
* точечный доступ к вузу - со сроком, основанием и отметкой, кто выдал;
* дополнительные права (персональные данные, журнал обмена) выдаются
  отдельно и из роли не следуют.
"""

from datetime import UTC, datetime, timedelta

from httpx import AsyncClient

from tests.conftest import (
    ADMIN,
    HEAD,
    MANAGER,
    OTHER_MANAGER,
    PURE_HEAD,
    ensure_template,
    join_team,
    make_interaction,
    me,
)


async def _user_id(client: AsyncClient, headers: dict) -> str:
    return (await me(client, headers))["id"]


async def test_me_shows_roles_scope_and_actions(client: AsyncClient) -> None:
    manager = await me(client, MANAGER)
    assert manager["roles"] == ["manager"]
    assert manager["effective_scope"] == "own"
    assert "create_interaction" in manager["actions"]
    assert "assign_responsible" not in manager["actions"]

    head = await me(client, PURE_HEAD)
    assert head["effective_scope"] == "team"
    assert "assign_responsible" in head["actions"]

    admin = await me(client, ADMIN)
    assert admin["effective_scope"] == "none"
    assert "manage_users" in admin["actions"]
    # Администратор не получает бизнес-действия руководителя и менеджера.
    assert "create_interaction" not in admin["actions"]
    assert "view_reports" not in admin["actions"]


async def test_users_list_filters_by_role(client: AsyncClient) -> None:
    for headers in (MANAGER, OTHER_MANAGER, HEAD, PURE_HEAD):
        await me(client, headers)

    heads = (await client.get("/api/v1/users", params={"role": "head"}, headers=ADMIN)).json()
    assert sorted(item["username"] for item in heads["items"]) == ["fedorov", "orlova"]
    managers = (
        await client.get("/api/v1/users", params={"role": "manager"}, headers=ADMIN)
    ).json()
    # Орлова совмещает роли явно, у Фёдорова роли менеджера нет.
    assert managers["total"] == 3


async def test_directory_is_available_to_business_roles(client: AsyncClient) -> None:
    """Справочник сотрудников для назначения - без прав администратора."""
    petrov = await _user_id(client, MANAGER)
    await join_team(client, MANAGER)
    response = await client.get(
        "/api/v1/users/directory", params={"role": "manager"}, headers=HEAD
    )
    assert response.status_code == 200, response.text
    assert petrov in {item["id"] for item in response.json()}


async def test_head_assigns_default_manager_for_university(
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

    # Вуз, где менеджер закреплён по умолчанию, открывает ему взаимодействия вуза.
    foreign = await make_interaction(client, university["id"], OTHER_MANAGER)
    visible = await client.get(f"/api/v1/interactions/{foreign['id']}", headers=MANAGER)
    assert visible.status_code == 200

    removed = await client.patch(
        f"/api/v1/universities/{university['id']}", json={"manager_id": None}, headers=HEAD
    )
    assert removed.json()["manager_id"] is None
    hidden = await client.get(f"/api/v1/interactions/{foreign['id']}", headers=MANAGER)
    assert hidden.status_code == 403


async def test_manager_creates_interaction_only_for_himself(
    client: AsyncClient, university: dict
) -> None:
    petrov = await _user_id(client, MANAGER)
    await client.patch(
        f"/api/v1/universities/{university['id']}", json={"manager_id": petrov}, headers=HEAD
    )
    await ensure_template(client)
    ivanova = await _user_id(client, OTHER_MANAGER)
    response = await client.post(
        "/api/v1/interactions",
        json={"university_id": university["id"], "manager_id": ivanova},
        headers=MANAGER,
    )
    assert response.status_code == 403

    own = await client.post(
        "/api/v1/interactions", json={"university_id": university["id"]}, headers=MANAGER
    )
    assert own.status_code == 201, own.text
    assert own.json()["manager"]["id"] == petrov


async def test_manager_cannot_open_interaction_outside_scope(
    client: AsyncClient, university: dict
) -> None:
    await make_interaction(client, university["id"], HEAD)
    response = await client.post(
        "/api/v1/interactions", json={"university_id": university["id"]}, headers=MANAGER
    )
    assert response.status_code == 403


async def test_admin_sets_temporary_scope_with_reason(
    client: AsyncClient, university: dict
) -> None:
    await make_interaction(client, university["id"], OTHER_MANAGER)
    petrov = await _user_id(client, MANAGER)
    assert (await client.get("/api/v1/interactions", headers=MANAGER)).json()["total"] == 0

    no_reason = await client.patch(
        f"/api/v1/users/{petrov}", json={"data_scope": "all"}, headers=ADMIN
    )
    assert no_reason.status_code == 400

    expires = (datetime.now(UTC) + timedelta(days=7)).isoformat()
    granted = await client.patch(
        f"/api/v1/users/{petrov}",
        json={
            "data_scope": "all",
            "data_scope_reason": "Подготовка годового отчёта",
            "data_scope_expires_at": expires,
        },
        headers=ADMIN,
    )
    assert granted.status_code == 200, granted.text
    assert (await client.get("/api/v1/interactions", headers=MANAGER)).json()["total"] == 1
    profile = await me(client, MANAGER)
    assert profile["effective_scope"] == "all"
    assert profile["data_scope_reason"] == "Подготовка годового отчёта"


async def test_admin_gets_business_data_only_by_scope(
    client: AsyncClient, university: dict
) -> None:
    await make_interaction(client, university["id"], MANAGER)
    admin = await _user_id(client, ADMIN)
    assert (await client.get("/api/v1/interactions", headers=ADMIN)).json()["total"] == 0

    await client.patch(
        f"/api/v1/users/{admin}",
        json={"data_scope": "all", "data_scope_reason": "Проверка данных после импорта"},
        headers=ADMIN,
    )
    listing = (await client.get("/api/v1/interactions", headers=ADMIN)).json()
    assert listing["total"] == 1
    # Видеть - не значит работать: менять ход процесса без бизнес-роли нельзя.
    blocked = await client.post(
        f"/api/v1/interactions/{listing['items'][0]['id']}/block",
        json={"reason": "Проверка"},
        headers=ADMIN,
    )
    assert blocked.status_code == 403


async def test_personal_data_needs_separate_permission(client: AsyncClient) -> None:
    for headers in (MANAGER, HEAD):
        response = await client.get("/api/v1/statistics/applications", headers=headers)
        assert response.status_code == 403

    orlova = await _user_id(client, HEAD)
    await client.patch(
        f"/api/v1/users/{orlova}",
        json={"permissions": ["view_personal_data"]},
        headers=ADMIN,
    )
    response = await client.get("/api/v1/statistics/applications", headers=HEAD)
    assert response.status_code == 200, response.text


async def test_disabled_user_is_locked_out(client: AsyncClient) -> None:
    petrov = await _user_id(client, MANAGER)
    await client.patch(f"/api/v1/users/{petrov}", json={"is_active": False}, headers=ADMIN)

    response = await client.get("/api/v1/interactions", headers=MANAGER)
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
            f"/api/v1/users/{petrov}",
            json={"data_scope": "all", "data_scope_reason": "Нужно"},
            headers=headers,
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
    profile = await me(client, {"X-Dev-User": "novikova", "X-Dev-Roles": "manager"})
    assert profile["id"] == created.json()["id"]
    assert profile["full_name"] == "Новикова Ольга Ивановна"

    duplicate = await client.post(
        "/api/v1/users",
        json={"username": "novikova", "full_name": "Кто-то", "roles": ["manager"]},
        headers=ADMIN,
    )
    assert duplicate.status_code == 409


# --- Вузы: единый жизненный цикл ---------------------------------------------------


async def test_university_proposed_by_manager_waits_for_confirmation(
    client: AsyncClient,
) -> None:
    proposed = await client.post(
        "/api/v1/universities",
        json={"name": "Новый вуз", "inn": "7700000001"},
        headers=MANAGER,
    )
    assert proposed.status_code == 201, proposed.text
    assert proposed.json()["status"] == "pending"

    duplicate = await client.post(
        "/api/v1/universities", json={"name": "новый вуз"}, headers=HEAD
    )
    assert duplicate.status_code == 409
    same_inn = await client.post(
        "/api/v1/universities",
        json={"name": "Другое название", "inn": "7700000001"},
        headers=HEAD,
    )
    assert same_inn.status_code == 409

    denied = await client.post(
        f"/api/v1/universities/{proposed.json()['id']}/confirm", headers=MANAGER
    )
    assert denied.status_code == 403
    confirmed = await client.post(
        f"/api/v1/universities/{proposed.json()['id']}/confirm", headers=HEAD
    )
    assert confirmed.status_code == 200
    assert confirmed.json()["status"] == "confirmed"


async def test_duplicates_are_merged_into_one_record(client: AsyncClient) -> None:
    target = (
        await client.post("/api/v1/universities", json={"name": "МТУСИ"}, headers=HEAD)
    ).json()
    twin = (
        await client.post(
            "/api/v1/universities", json={"name": "МТУСИ (Москва)"}, headers=MANAGER
        )
    ).json()
    contact = await client.post(
        f"/api/v1/universities/{twin['id']}/contacts",
        json={"full_name": "Гусева Анна Петровна"},
        headers=HEAD,
    )
    assert contact.status_code == 201, contact.text

    merged = await client.post(
        f"/api/v1/universities/{twin['id']}/merge",
        json={"target_id": target["id"]},
        headers=HEAD,
    )
    assert merged.status_code == 200, merged.text
    assert merged.json()["id"] == target["id"]
    assert [item["full_name"] for item in merged.json()["contacts"]] == [
        "Гусева Анна Петровна"
    ]
    source = (await client.get(f"/api/v1/universities/{twin['id']}", headers=HEAD)).json()
    assert source["status"] == "archived"
    assert source["merged_into_id"] == target["id"]


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


async def test_university_with_interactions_is_archived_not_deleted(
    client: AsyncClient, university: dict
) -> None:
    await make_interaction(client, university["id"], MANAGER)
    response = await client.delete(f"/api/v1/universities/{university['id']}", headers=ADMIN)
    assert response.status_code == 409
    assert "архив" in response.json()["message"]

    archived = await client.post(
        f"/api/v1/universities/{university['id']}/archive", headers=HEAD
    )
    assert archived.status_code == 200
    assert archived.json()["status"] == "archived"
