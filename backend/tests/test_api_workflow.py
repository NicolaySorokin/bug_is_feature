"""Рабочий процесс по договору и редактирование шаблонов."""

from httpx import AsyncClient

from tests.conftest import ADMIN, MANAGER, make_contract


async def _start(client: AsyncClient, contract_id: str, version: dict) -> dict:
    response = await client.post(
        f"/api/v1/contracts/{contract_id}/workflow",
        json={"template_id": version["template_id"], "version_id": version["id"]},
        headers=MANAGER,
    )
    assert response.status_code == 201, response.text
    return response.json()


def _stage(view: dict, code: str) -> str:
    return next(stage["id"] for stage in view["version"]["stages"] if stage["code"] == code)


async def test_process_moves_along_template(
    client: AsyncClient, university: dict, workflow_version: dict
) -> None:
    contract = await make_contract(client, university["id"], MANAGER)
    view = await _start(client, contract["id"], workflow_version)

    assert view["status"] == "in_progress"
    assert [t["to_stage_id"] for t in view["available_transitions"]] == [
        _stage(view, "meeting")
    ]

    moved = await client.post(
        f"/api/v1/workflow/instances/{view['id']}/transition",
        json={"to_stage_id": _stage(view, "meeting"), "comment": "Встреча назначена"},
        headers=MANAGER,
    )
    assert moved.status_code == 200
    body = moved.json()
    states = {item["stage_id"]: item["state"] for item in body["stage_states"]}
    assert states[_stage(view, "contact")] == "completed"
    assert states[_stage(view, "meeting")] == "active"
    assert len(body["events"]) == 2


async def test_transition_outside_template_is_rejected(
    client: AsyncClient, university: dict, workflow_version: dict
) -> None:
    contract = await make_contract(client, university["id"], MANAGER)
    view = await _start(client, contract["id"], workflow_version)

    response = await client.post(
        f"/api/v1/workflow/instances/{view['id']}/transition",
        json={"to_stage_id": _stage(view, "signing")},
        headers=MANAGER,
    )
    assert response.status_code == 409
    assert response.json()["code"] == "workflow_rule_violated"


async def test_final_stage_completes_process(
    client: AsyncClient, university: dict, workflow_version: dict
) -> None:
    contract = await make_contract(client, university["id"], MANAGER)
    view = await _start(client, contract["id"], workflow_version)

    await client.post(
        f"/api/v1/workflow/instances/{view['id']}/transition",
        json={"to_stage_id": _stage(view, "meeting")},
        headers=MANAGER,
    )
    finished = await client.post(
        f"/api/v1/workflow/instances/{view['id']}/transition",
        json={"to_stage_id": _stage(view, "signing")},
        headers=MANAGER,
    )
    assert finished.status_code == 200
    assert finished.json()["status"] == "completed"
    assert finished.json()["completed_at"] is not None


async def test_published_version_cannot_be_edited(
    client: AsyncClient, workflow_version: dict
) -> None:
    response = await client.put(
        f"/api/v1/workflow/versions/{workflow_version['id']}/graph",
        json={
            "stages": [{"code": "only", "name": "Единственный", "is_final": True}],
            "transitions": [],
        },
        headers=ADMIN,
    )
    assert response.status_code == 409
    assert "новую версию" in response.json()["message"]


async def test_new_version_copies_graph_and_keeps_running_process(
    client: AsyncClient, university: dict, workflow_version: dict
) -> None:
    contract = await make_contract(client, university["id"], MANAGER)
    view = await _start(client, contract["id"], workflow_version)

    created = await client.post(
        f"/api/v1/workflow/templates/{workflow_version['template_id']}/versions",
        json={},
        headers=ADMIN,
    )
    assert created.status_code == 201
    draft = created.json()
    assert draft["version_number"] == 2
    assert {stage["code"] for stage in draft["stages"]} == {
        "contact",
        "meeting",
        "signing",
    }

    # Правка черновика не трогает уже запущенный процесс.
    await client.put(
        f"/api/v1/workflow/versions/{draft['id']}/graph",
        json={
            "stages": [
                {"code": "contact", "name": "Первый контакт"},
                {"code": "signing", "name": "Подписание", "is_final": True},
            ],
            "transitions": [{"from_code": "contact", "to_code": "signing"}],
        },
        headers=ADMIN,
    )
    current = await client.get(
        f"/api/v1/contracts/{contract['id']}/workflow", headers=MANAGER
    )
    assert current.json()["workflow_version_id"] == view["workflow_version_id"]
    assert len(current.json()["version"]["stages"]) == 3


async def test_graph_without_final_stage_is_rejected(client: AsyncClient) -> None:
    response = await client.post(
        "/api/v1/workflow/templates",
        json={
            "name": "Без финала",
            "graph": {
                "stages": [{"code": "one", "name": "Один"}],
                "transitions": [],
            },
        },
        headers=ADMIN,
    )
    assert response.status_code == 409
    assert "завершающего этапа" in response.json()["message"]


async def test_layout_can_be_saved_on_published_version(
    client: AsyncClient, workflow_version: dict
) -> None:
    stage_id = workflow_version["stages"][0]["id"]
    response = await client.put(
        f"/api/v1/workflow/versions/{workflow_version['id']}/layout",
        json={"stages": [{"stage_id": stage_id, "layout_x": 120, "layout_y": 40}]},
        headers=ADMIN,
    )
    assert response.status_code == 200
    moved = next(s for s in response.json()["stages"] if s["id"] == stage_id)
    assert (moved["layout_x"], moved["layout_y"]) == (120, 40)


async def test_manager_cannot_edit_templates(client: AsyncClient) -> None:
    response = await client.post(
        "/api/v1/workflow/templates",
        json={"name": "Свой процесс"},
        headers=MANAGER,
    )
    assert response.status_code == 403
