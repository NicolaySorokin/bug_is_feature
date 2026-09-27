"""Взаимодействия с вузами: реестр, карточка, состав, договор и права.

Взаимодействие - центральная сущность: договор внутри него необязателен
(0..1), состав программ и продуктов задаётся на уровне взаимодействия,
а область данных решает, кто что видит.
"""

from httpx import AsyncClient

from tests.conftest import (
    ADMIN,
    HEAD,
    MANAGER,
    OTHER_MANAGER,
    PURE_HEAD,
    contract_payload,
    create_template,
    join_team,
    make_contract,
    make_interaction,
    me,
)


async def _program(client: AsyncClient, name: str, direction_id: str | None = None) -> dict:
    payload = {"name": name, "direction_id": direction_id}
    response = await client.post("/api/v1/catalog/programs", json=payload, headers=ADMIN)
    assert response.status_code == 201, response.text
    return response.json()


async def _product(client: AsyncClient, name: str) -> dict:
    response = await client.post(
        "/api/v1/catalog/products", json={"name": name}, headers=ADMIN
    )
    assert response.status_code == 201, response.text
    return response.json()


# --- Область данных -----------------------------------------------------------------


async def test_manager_sees_only_own_interactions(
    client: AsyncClient, university: dict
) -> None:
    mine = await make_interaction(client, university["id"], MANAGER)
    await make_interaction(client, university["id"], OTHER_MANAGER)

    listing = (await client.get("/api/v1/interactions", headers=MANAGER)).json()
    assert [item["id"] for item in listing["items"]] == [mine["id"]]
    assert listing["total"] == 1

    # Руководитель видит взаимодействия своей команды.
    for_head = (await client.get("/api/v1/interactions", headers=HEAD)).json()
    assert for_head["total"] == 2


async def test_admin_without_business_scope_sees_nothing(
    client: AsyncClient, university: dict
) -> None:
    await make_interaction(client, university["id"], MANAGER)
    profile = await me(client, ADMIN)
    assert profile["effective_scope"] == "none"
    listing = (await client.get("/api/v1/interactions", headers=ADMIN)).json()
    assert listing["total"] == 0


async def test_head_role_does_not_include_manager_rights(
    client: AsyncClient, university: dict
) -> None:
    """Руководитель без роли менеджера не может стать ответственным сам."""
    await create_template(client)
    head = await me(client, PURE_HEAD)
    response = await client.post(
        "/api/v1/interactions",
        json={"university_id": university["id"], "manager_id": head["id"]},
        headers=PURE_HEAD,
    )
    assert response.status_code == 409
    assert "Менеджер" in response.json()["message"]


async def test_foreign_interaction_is_forbidden(client: AsyncClient, university: dict) -> None:
    foreign = await make_interaction(client, university["id"], OTHER_MANAGER)

    response = await client.get(f"/api/v1/interactions/{foreign['id']}", headers=MANAGER)
    assert response.status_code == 403
    assert response.json()["code"] == "forbidden"


async def test_temporary_grant_opens_university(client: AsyncClient, university: dict) -> None:
    foreign = await make_interaction(client, university["id"], OTHER_MANAGER)
    petrov = await me(client, MANAGER)
    url = f"/api/v1/users/{petrov['id']}/grants"

    no_reason = await client.put(url, json={"university_id": university["id"]}, headers=ADMIN)
    assert no_reason.status_code == 422

    granted = await client.put(
        url,
        json={"university_id": university["id"], "reason": "Замещает коллегу в отпуске"},
        headers=ADMIN,
    )
    assert granted.status_code == 200, granted.text
    response = await client.get(f"/api/v1/interactions/{foreign['id']}", headers=MANAGER)
    assert response.status_code == 200

    # Отзыв не удаляет запись: видно, кто и когда закрыл доступ.
    revoked = await client.delete(f"{url}/{university['id']}", headers=ADMIN)
    assert revoked.status_code == 200, revoked.text
    grant = next(
        item for item in revoked.json()["grants"] if item["university_id"] == university["id"]
    )
    assert grant["revoked_at"] is not None
    response = await client.get(f"/api/v1/interactions/{foreign['id']}", headers=MANAGER)
    assert response.status_code == 403


async def test_unknown_interaction_returns_error_code(client: AsyncClient) -> None:
    response = await client.get(
        "/api/v1/interactions/00000000-0000-0000-0000-000000000000", headers=MANAGER
    )
    assert response.status_code == 404
    body = response.json()
    assert body["code"] == "not_found"
    assert body["message"]


async def test_manager_cannot_reassign_responsible(
    client: AsyncClient, university: dict
) -> None:
    interaction = await make_interaction(client, university["id"], MANAGER)

    response = await client.patch(
        f"/api/v1/interactions/{interaction['id']}",
        json={"manager_id": None},
        headers=MANAGER,
    )
    assert response.status_code == 403

    allowed = await client.patch(
        f"/api/v1/interactions/{interaction['id']}",
        json={"comment": "Уточнили состав"},
        headers=MANAGER,
    )
    assert allowed.status_code == 200
    assert allowed.json()["comment"] == "Уточнили состав"


async def test_head_reassigns_within_team_with_history(
    client: AsyncClient, university: dict
) -> None:
    interaction = await make_interaction(client, university["id"], MANAGER)
    await join_team(client, OTHER_MANAGER)
    ivanova = await me(client, OTHER_MANAGER)

    response = await client.patch(
        f"/api/v1/interactions/{interaction['id']}",
        json={"manager_id": ivanova["id"]},
        headers=HEAD,
    )
    assert response.status_code == 200, response.text
    assert response.json()["manager"]["id"] == ivanova["id"]
    view = (
        await client.get(f"/api/v1/interactions/{interaction['id']}/workflow", headers=HEAD)
    ).json()
    assert any(event["event_type"] == "reassigned" for event in view["events"])


async def test_default_manager_outside_team_leaves_interaction_unassigned(
    client: AsyncClient, university: dict, workflow_version: dict
) -> None:
    """Менеджер по умолчанию у вуза - подсказка: если руководитель не может его
    назначить (другая команда), взаимодействие заводится без ответственного,
    а не получает отказ."""
    ivanova = await me(client, OTHER_MANAGER)
    updated = await client.patch(
        f"/api/v1/universities/{university['id']}",
        json={"manager_id": ivanova["id"]},
        headers=ADMIN,
    )
    assert updated.status_code == 200, updated.text

    response = await client.post(
        "/api/v1/interactions",
        json={"university_id": university["id"], "title": "Без ответственного"},
        headers=HEAD,
    )
    assert response.status_code == 201, response.text
    assert response.json()["manager"] is None

    # Своего менеджера руководитель по-прежнему получает по умолчанию.
    await join_team(client, OTHER_MANAGER)
    team = await client.post(
        "/api/v1/interactions",
        json={"university_id": university["id"], "title": "С ответственным"},
        headers=HEAD,
    )
    assert team.status_code == 201, team.text
    assert team.json()["manager"]["id"] == ivanova["id"]


# --- Жизненный цикл -----------------------------------------------------------------


async def test_draft_is_started_later(client: AsyncClient, university: dict) -> None:
    draft = await make_interaction(client, university["id"], MANAGER, start=False)
    assert draft["status"] == "draft"
    assert draft["stage"] is None
    assert draft["contract"] is None

    started = await client.post(f"/api/v1/interactions/{draft['id']}/start", headers=MANAGER)
    assert started.status_code == 200, started.text
    detail = (await client.get(f"/api/v1/interactions/{draft['id']}", headers=MANAGER)).json()
    assert detail["status"] == "in_progress"
    assert detail["stage"]["stage_name"] == "Контакт"
    assert detail["stage"]["next_actions"]


async def test_only_empty_draft_is_deleted(client: AsyncClient, university: dict) -> None:
    draft = await make_interaction(client, university["id"], HEAD, start=False)
    started = await make_interaction(client, university["id"], HEAD)

    refused = await client.delete(f"/api/v1/interactions/{started['id']}", headers=HEAD)
    assert refused.status_code == 409
    deleted = await client.delete(f"/api/v1/interactions/{draft['id']}", headers=HEAD)
    assert deleted.status_code == 204


async def test_cancel_needs_reason_and_keeps_outcome(
    client: AsyncClient, university: dict
) -> None:
    interaction = await make_interaction(client, university["id"], MANAGER)
    url = f"/api/v1/interactions/{interaction['id']}/cancel"

    other = await client.post(url, json={"reason": "other"}, headers=MANAGER)
    assert other.status_code == 422
    # Нарушенное правило видно в тексте ошибки, а не только в подробностях.
    assert other.json()["message"] == "Для причины «Иное» нужен комментарий"

    cancelled = await client.post(
        url,
        json={"reason": "lost_relevance", "comment": "Кафедру расформировали"},
        headers=MANAGER,
    )
    assert cancelled.status_code == 200, cancelled.text
    detail = (
        await client.get(f"/api/v1/interactions/{interaction['id']}", headers=MANAGER)
    ).json()
    assert detail["status"] == "cancelled"
    assert detail["outcome"] == "unsuccessful"
    assert detail["closure_reason"] == "lost_relevance"
    assert detail["closure_comment"] == "Кафедру расформировали"
    assert detail["closed_by"]["full_name"]

    again = await client.post(url, json={"reason": "duplicate"}, headers=MANAGER)
    assert again.status_code == 409

    # Фильтр реестра по результату.
    listing = (
        await client.get(
            "/api/v1/interactions", params={"outcome": "unsuccessful"}, headers=MANAGER
        )
    ).json()
    assert listing["total"] == 1


async def test_cancelled_blocked_interaction_is_no_longer_blocked(
    client: AsyncClient, university: dict
) -> None:
    interaction = await make_interaction(client, university["id"], MANAGER)
    url = f"/api/v1/interactions/{interaction['id']}"
    await client.post(f"{url}/block", json={"reason": "Ждём ректора"}, headers=MANAGER)
    cancelled = await client.post(
        f"{url}/cancel", json={"reason": "university_refused"}, headers=MANAGER
    )
    assert cancelled.status_code == 200, cancelled.text

    detail = (await client.get(url, headers=MANAGER)).json()
    assert detail["status"] == "cancelled"
    assert detail["blocked_reason"] is None
    assert detail["blocked_at"] is None


async def test_unconfirmed_university_gets_no_interaction(client: AsyncClient) -> None:
    await create_template(client)
    proposed = await client.post(
        "/api/v1/universities", json={"name": "Новый вуз от менеджера"}, headers=MANAGER
    )
    assert proposed.status_code == 201, proposed.text
    assert proposed.json()["status"] == "pending"

    response = await client.post(
        "/api/v1/interactions",
        json={"university_id": proposed.json()["id"]},
        headers=HEAD,
    )
    assert response.status_code == 409


# --- Договор 0..1 -----------------------------------------------------------------


async def test_contract_is_optional_and_single(client: AsyncClient, university: dict) -> None:
    interaction = await make_interaction(client, university["id"], MANAGER)
    url = f"/api/v1/interactions/{interaction['id']}/contract"
    assert (await client.get(url, headers=MANAGER)).json() is None

    draft = await client.put(
        url, json={"number": "ДГ-2026-900", "status": "draft"}, headers=MANAGER
    )
    assert draft.status_code == 200, draft.text
    # Повторный PUT меняет тот же договор, а не заводит второй.
    active = await client.put(
        url, json=contract_payload(number="ДГ-2026-900"), headers=MANAGER
    )
    assert active.json()["id"] == draft.json()["id"]
    assert active.json()["status"] == "active"

    unsigned = await client.put(
        url, json={"number": "ДГ-2026-900", "status": "active"}, headers=MANAGER
    )
    assert unsigned.status_code == 422

    # Подписанный договор не удаляют - только закрывают с причиной.
    refused = await client.delete(url, headers=MANAGER)
    assert refused.status_code == 409
    closed = await client.put(
        url,
        json=contract_payload(number="ДГ-2026-900", status="closed"),
        headers=MANAGER,
    )
    assert closed.status_code == 422  # без причины закрытия
    closed = await client.put(
        url,
        json=contract_payload(
            number="ДГ-2026-900", status="closed", closure_reason="fulfilled"
        ),
        headers=MANAGER,
    )
    assert closed.status_code == 200, closed.text

    detail = (
        await client.get(f"/api/v1/interactions/{interaction['id']}", headers=MANAGER)
    ).json()
    assert detail["contract"]["number"] == "ДГ-2026-900"
    by_number = (
        await client.get(
            "/api/v1/interactions", params={"search": "2026-900"}, headers=MANAGER
        )
    ).json()
    assert by_number["total"] == 1


async def test_registry_filters_by_contract_presence(
    client: AsyncClient, university: dict
) -> None:
    await make_contract(client, university["id"], MANAGER)
    await make_interaction(client, university["id"], MANAGER)

    async def total(**params: object) -> int:
        response = await client.get("/api/v1/interactions", params=params, headers=MANAGER)
        assert response.status_code == 200, response.text
        return response.json()["total"]

    assert await total(has_contract=True) == 1
    assert await total(has_contract=False) == 1
    assert await total(contract_status="active") == 1


# --- Состав: программы, продукты и их связи ----------------------------------------


async def test_programs_are_added_and_removed(client: AsyncClient, university: dict) -> None:
    interaction = await make_interaction(client, university["id"], MANAGER)
    program = await _program(client, "Python-разработчик")
    url = f"/api/v1/interactions/{interaction['id']}/programs"

    link = (await client.post(url, json={"program_id": program["id"]}, headers=MANAGER)).json()
    duplicate = await client.post(url, json={"program_id": program["id"]}, headers=MANAGER)
    assert duplicate.status_code == 409
    assert duplicate.json()["code"] == "conflict"

    removed = await client.delete(f"{url}/{link['id']}", headers=MANAGER)
    assert removed.status_code == 204
    detail = (
        await client.get(f"/api/v1/interactions/{interaction['id']}", headers=MANAGER)
    ).json()
    assert detail["programs"] == []


async def test_product_needs_program_and_catalog_link(
    client: AsyncClient, university: dict
) -> None:
    """Продукт - инструмент программы: без связи его не добавить, а связь вне
    справочного соответствия - исключение руководителя с комментарием."""
    program = await _program(client, "Инженер DevOps")
    product = await _product(client, "Песочница DevOps")
    other = await _product(client, "Стенд киберполигона")
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
    program_link = detail["program_links"][0]["id"]
    url = f"/api/v1/interactions/{interaction['id']}/products"

    without_program = await client.post(
        url, json={"product_id": product["id"], "program_link_ids": []}, headers=MANAGER
    )
    assert without_program.status_code == 422

    added = await client.post(
        url,
        json={"product_id": product["id"], "program_link_ids": [program_link]},
        headers=MANAGER,
    )
    assert added.status_code == 201, added.text

    exception = {"product_id": other["id"], "program_link_ids": [program_link]}
    by_manager = await client.post(
        url, json={**exception, "exception_comment": "Нужен для практикума"}, headers=MANAGER
    )
    assert by_manager.status_code == 403
    no_comment = await client.post(url, json=exception, headers=HEAD)
    assert no_comment.status_code == 400
    assert no_comment.json()["code"] == "validation_error"
    by_head = await client.post(
        url, json={**exception, "exception_comment": "Нужен для практикума"}, headers=HEAD
    )
    assert by_head.status_code == 201, by_head.text

    detail = (
        await client.get(f"/api/v1/interactions/{interaction['id']}", headers=MANAGER)
    ).json()
    assert sorted(link["is_exception"] for link in detail["links"]) == [False, True]


async def test_product_status_changed_by_hand_needs_comment(
    client: AsyncClient, university: dict
) -> None:
    program = await _program(client, "Аналитик данных")
    product = await _product(client, "Postgres Pro Enterprise")
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
    url = f"/api/v1/interactions/{interaction['id']}/products/{link['id']}"

    silent = await client.patch(url, json={"transfer_status": "transferred"}, headers=MANAGER)
    assert silent.status_code == 400
    assert silent.json()["code"] == "validation_error"
    explained = await client.patch(
        url,
        json={"transfer_status": "transferred", "comment": "Передали досрочно по письму"},
        headers=MANAGER,
    )
    assert explained.status_code == 200, explained.text
    assert explained.json()["transfer_status"] == "transferred"


async def test_university_contacts_are_assigned_to_interaction(
    client: AsyncClient, university: dict
) -> None:
    interaction = await make_interaction(client, university["id"], MANAGER)
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
    url = f"/api/v1/interactions/{interaction['id']}/contacts"
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
    removed = await client.delete(f"{url}/{first['id']}", headers=MANAGER)
    assert removed.status_code == 204
    assert len((await client.get(url, headers=MANAGER)).json()) == 1


async def test_contact_of_other_university_is_refused(
    client: AsyncClient, university: dict
) -> None:
    interaction = await make_interaction(client, university["id"], MANAGER)
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
        f"/api/v1/interactions/{interaction['id']}/contacts",
        json={"contact_id": stranger["id"]},
        headers=MANAGER,
    )
    assert response.status_code == 404


# --- Реестр ---------------------------------------------------------------------------


async def test_registry_row_separates_status_stage_and_sla(
    client: AsyncClient, university: dict
) -> None:
    await make_interaction(client, university["id"], MANAGER)
    listing = (await client.get("/api/v1/interactions", headers=MANAGER)).json()
    row = listing["items"][0]
    assert row["status"] == "in_progress"
    assert row["stage"]["stage_name"] == "Контакт"
    assert row["stage"]["sla"]["days_on_stage"] == 0
    assert row["stage"]["sla"]["sla_days"] == 7
    assert row["stage"]["sla"]["state"] == "ok"

    by_stage = (
        await client.get("/api/v1/interactions", params={"stage": "Контакт"}, headers=MANAGER)
    ).json()
    assert by_stage["total"] == 1
    none = (
        await client.get("/api/v1/interactions", params={"stage": "Встреча"}, headers=MANAGER)
    ).json()
    assert none["total"] == 0


async def test_registry_filters_by_status(client: AsyncClient, university: dict) -> None:
    started = await make_interaction(client, university["id"], MANAGER)
    await make_interaction(client, university["id"], MANAGER, start=False)

    async def total(*statuses: str) -> int:
        response = await client.get(
            "/api/v1/interactions", params={"status": list(statuses)}, headers=MANAGER
        )
        assert response.status_code == 200, response.text
        return response.json()["total"]

    assert await total("in_progress") == 1
    assert await total("draft") == 1
    assert await total("blocked") == 0

    blocked = await client.post(
        f"/api/v1/interactions/{started['id']}/block",
        json={"reason": "Ждём подписи ректора"},
        headers=MANAGER,
    )
    assert blocked.status_code == 200, blocked.text
    assert await total("blocked") == 1
    assert await total("in_progress") == 0
    assert await total("in_progress", "blocked", "draft") == 2
    detail = (
        await client.get(f"/api/v1/interactions/{started['id']}", headers=MANAGER)
    ).json()
    assert detail["blocked_reason"] == "Ждём подписи ректора"


async def test_registry_filters_by_direction(client: AsyncClient, university: dict) -> None:
    direction = (
        await client.post("/api/v1/catalog/directions", json={"name": "QA"}, headers=ADMIN)
    ).json()
    program = await _program(client, "Инженер-тестировщик", direction["id"])
    await make_interaction(client, university["id"], MANAGER, program_ids=[program["id"]])
    await make_interaction(client, university["id"], MANAGER)

    listing = (
        await client.get(
            "/api/v1/interactions", params={"direction_id": direction["id"]}, headers=MANAGER
        )
    ).json()
    assert listing["total"] == 1
    assert listing["items"][0]["programs"] == ["Инженер-тестировщик"]


# --- Шаблон процесса ----------------------------------------------------------------


async def test_stage_is_renamed_by_admin(client: AsyncClient, workflow_version: dict) -> None:
    stage = workflow_version["stages"][0]
    denied = await client.patch(
        f"/api/v1/workflow/stages/{stage['id']}", json={"name": "Знакомство"}, headers=MANAGER
    )
    assert denied.status_code == 403

    # Версия опубликована, но название статуса поправить можно: на ход процессов
    # оно не влияет.
    renamed = await client.patch(
        f"/api/v1/workflow/stages/{stage['id']}", json={"name": "Знакомство"}, headers=ADMIN
    )
    assert renamed.status_code == 200
    graph = (
        await client.get(
            f"/api/v1/workflow/versions/{workflow_version['id']}", headers=MANAGER
        )
    ).json()
    assert graph["stages"][0]["name"] == "Знакомство"
    assert graph["status"] == "active"


async def test_versions_show_usage(
    client: AsyncClient, university: dict, workflow_version: dict
) -> None:
    await make_interaction(
        client, university["id"], MANAGER, template_id=workflow_version["template_id"]
    )
    versions = (
        await client.get(
            f"/api/v1/workflow/templates/{workflow_version['template_id']}/versions",
            headers=MANAGER,
        )
    ).json()
    assert versions[0]["instances_count"] == 1


# --- Журнал изменений ---------------------------------------------------------------


async def test_changes_get_into_audit_log(client: AsyncClient, university: dict) -> None:
    _, contract = await make_contract(client, university["id"], HEAD)

    entries = (
        await client.get(
            "/api/v1/audit",
            params={"entity_type": "contracts", "entity_id": contract["id"]},
            headers=ADMIN,
        )
    ).json()
    assert entries["total"] >= 1
    entry = entries["items"][-1]
    assert entry["action"] == "create"
    assert entry["after_data"]["number"] == contract["number"]


async def test_audit_names_author_even_when_role_check_is_enough(
    client: AsyncClient, university: dict
) -> None:
    manager = await me(client, MANAGER)
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
    head = await me(client, HEAD)
    assert update["user_id"] == head["id"]
    assert update["user_name"] == head["full_name"]


async def test_audit_is_closed_for_manager(client: AsyncClient) -> None:
    response = await client.get("/api/v1/audit", headers=MANAGER)
    assert response.status_code == 403
