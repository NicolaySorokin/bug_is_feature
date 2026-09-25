"""Карточка договора: состав, ответственные от вуза, строка реестра, статусы."""

from httpx import AsyncClient

from tests.conftest import ADMIN, HEAD, MANAGER, make_contract


async def _program(client: AsyncClient, name: str, direction_id: str | None = None) -> dict:
    payload = {"name": name, "direction_id": direction_id}
    response = await client.post("/api/v1/catalog/programs", json=payload, headers=ADMIN)
    assert response.status_code == 201, response.text
    return response.json()


async def test_composition_is_added_and_removed(client: AsyncClient, university: dict) -> None:
    contract = await make_contract(client, university["id"], MANAGER)
    program = await _program(client, "Python-разработчик")
    url = f"/api/v1/contracts/{contract['id']}/programs"

    link = (await client.post(url, json={"program_id": program["id"]}, headers=MANAGER)).json()
    duplicate = await client.post(url, json={"program_id": program["id"]}, headers=MANAGER)
    assert duplicate.status_code == 409
    assert duplicate.json()["code"] == "conflict"

    removed = await client.delete(f"{url}/{link['id']}", headers=MANAGER)
    assert removed.status_code == 204
    detail = (await client.get(f"/api/v1/contracts/{contract['id']}", headers=MANAGER)).json()
    assert detail["programs"] == []


async def test_university_contacts_are_assigned_to_contract(
    client: AsyncClient, university: dict
) -> None:
    contract = await make_contract(client, university["id"], MANAGER)
    first = (
        await client.post(
            f"/api/v1/universities/{university['id']}/contacts",
            json={"full_name": "Гусева Анна Петровна", "position": "Проректор"},
            headers=HEAD,
        )
    ).json()
    second = (
        await client.post(
            f"/api/v1/universities/{university['id']}/contacts",
            json={"full_name": "Тарасов Олег Юрьевич"},
            headers=HEAD,
        )
    ).json()
    url = f"/api/v1/contracts/{contract['id']}/contacts"
    await client.put(
        url, json={"contact_id": first["id"], "is_primary": True}, headers=MANAGER
    )
    await client.put(
        url,
        json={"contact_id": second["id"], "role": "Юрист", "is_primary": True},
        headers=MANAGER,
    )

    contacts = (await client.get(url, headers=MANAGER)).json()
    # Основной контакт один: назначение второго сняло признак с первого.
    assert [(item["contact"]["full_name"], item["is_primary"]) for item in contacts] == [
        ("Тарасов Олег Юрьевич", True),
        ("Гусева Анна Петровна", False),
    ]
    detail = (await client.get(f"/api/v1/contracts/{contract['id']}", headers=MANAGER)).json()
    assert len(detail["contacts"]) == 2

    removed = await client.delete(f"{url}/{first['id']}", headers=MANAGER)
    assert removed.status_code == 204
    assert len((await client.get(url, headers=MANAGER)).json()) == 1


async def test_contact_of_other_university_is_refused(
    client: AsyncClient, university: dict
) -> None:
    contract = await make_contract(client, university["id"], MANAGER)
    other = (
        await client.post("/api/v1/universities", json={"name": "Другой вуз"}, headers=HEAD)
    ).json()
    stranger = (
        await client.post(
            f"/api/v1/universities/{other['id']}/contacts",
            json={"full_name": "Чужой контакт"},
            headers=HEAD,
        )
    ).json()
    response = await client.put(
        f"/api/v1/contracts/{contract['id']}/contacts",
        json={"contact_id": stranger["id"]},
        headers=MANAGER,
    )
    assert response.status_code == 404


async def test_registry_row_shows_current_stage(
    client: AsyncClient, university: dict, workflow_version: dict
) -> None:
    await make_contract(
        client,
        university["id"],
        MANAGER,
        workflow_template_id=workflow_version["template_id"],
    )
    listing = (await client.get("/api/v1/contracts", headers=MANAGER)).json()
    process = listing["items"][0]["process"]
    assert process["status"] == "in_progress"
    assert process["stage_name"] == "Контакт"
    assert process["days_on_stage"] == 0
    assert process["sla_days"] == 7

    by_stage = (
        await client.get("/api/v1/contracts", params={"stage": "Контакт"}, headers=MANAGER)
    ).json()
    assert by_stage["total"] == 1
    none = (
        await client.get("/api/v1/contracts", params={"stage": "Встреча"}, headers=MANAGER)
    ).json()
    assert none["total"] == 0


async def test_registry_filters_by_process_state(
    client: AsyncClient, university: dict, workflow_version: dict
) -> None:
    started = await make_contract(
        client,
        university["id"],
        MANAGER,
        workflow_template_id=workflow_version["template_id"],
    )
    await make_contract(client, university["id"], MANAGER)

    async def total(process: str) -> int:
        response = await client.get(
            "/api/v1/contracts", params={"process": process}, headers=MANAGER
        )
        assert response.status_code == 200, response.text
        return response.json()["total"]

    assert await total("in_progress") == 1
    assert await total("none") == 1
    assert await total("blocked") == 0

    workflow = (
        await client.get(f"/api/v1/contracts/{started['id']}/workflow", headers=MANAGER)
    ).json()
    blocked = await client.post(
        f"/api/v1/workflow/instances/{workflow['id']}/block",
        json={"reason": "Ждём подписи ректора"},
        headers=MANAGER,
    )
    assert blocked.status_code == 200, blocked.text
    assert await total("blocked") == 1
    assert await total("in_progress") == 0


async def test_registry_filters_by_direction(client: AsyncClient, university: dict) -> None:
    direction = (
        await client.post("/api/v1/catalog/directions", json={"name": "QA"}, headers=ADMIN)
    ).json()
    program = await _program(client, "Инженер-тестировщик", direction["id"])
    await make_contract(client, university["id"], MANAGER, program_ids=[program["id"]])
    await make_contract(client, university["id"], MANAGER)

    listing = (
        await client.get(
            "/api/v1/contracts", params={"direction_id": direction["id"]}, headers=MANAGER
        )
    ).json()
    assert listing["total"] == 1


async def test_stage_is_renamed_by_head(client: AsyncClient, workflow_version: dict) -> None:
    stage = workflow_version["stages"][0]
    denied = await client.patch(
        f"/api/v1/workflow/stages/{stage['id']}", json={"name": "Знакомство"}, headers=MANAGER
    )
    assert denied.status_code == 403

    # Версия опубликована, но название статуса поправить можно: на ход процессов
    # оно не влияет.
    renamed = await client.patch(
        f"/api/v1/workflow/stages/{stage['id']}", json={"name": "Знакомство"}, headers=HEAD
    )
    assert renamed.status_code == 200
    graph = (
        await client.get(
            f"/api/v1/workflow/versions/{workflow_version['id']}", headers=MANAGER
        )
    ).json()
    assert graph["stages"][0]["name"] == "Знакомство"
    assert graph["published_at"] is not None


async def test_versions_show_usage(
    client: AsyncClient, university: dict, workflow_version: dict
) -> None:
    await make_contract(
        client, university["id"], MANAGER, workflow_template_id=workflow_version["template_id"]
    )
    versions = (
        await client.get(
            f"/api/v1/workflow/templates/{workflow_version['template_id']}/versions",
            headers=MANAGER,
        )
    ).json()
    assert versions[0]["instances_count"] == 1
