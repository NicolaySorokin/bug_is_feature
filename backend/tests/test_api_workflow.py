"""Процесс взаимодействия и жизненный цикл шаблонов.

* переходы - только разрешённые схемой версии;
* финальный этап даёт бизнес-результат, неуспешный - с причиной;
* обязательные документы этапа не дают уйти с него вперёд;
* версия: черновик -> действующая -> устаревшая -> выведена; действующая
  у шаблона одна, опубликованную структурно не меняют (это держит и база);
* перед публикацией граф проверяется целиком.
"""

from datetime import UTC, datetime

import pytest
from httpx import AsyncClient
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError
from sqlalchemy.ext.asyncio import AsyncEngine

from tests.conftest import ADMIN, HEAD, MANAGER, TEST_GRAPH, create_template, make_interaction

REFUSAL_GRAPH = {
    "stages": [
        {"code": "contact", "name": "Контакт", "is_initial": True},
        {
            "code": "documents",
            "name": "Документы",
            "required_documents": ["contract"],
            "program_status_on_enter": "in_progress",
        },
        {"code": "done", "name": "Подписано", "is_final": True, "outcome": "successful"},
        {"code": "refusal", "name": "Отказ", "is_final": True, "outcome": "unsuccessful"},
    ],
    "transitions": [
        {"from_code": "contact", "to_code": "documents"},
        {"from_code": "contact", "to_code": "refusal", "requires_comment": True},
        {"from_code": "documents", "to_code": "done"},
        {"from_code": "documents", "to_code": "refusal", "requires_comment": True},
    ],
}


async def _view(client: AsyncClient, interaction: dict) -> dict:
    response = await client.get(
        f"/api/v1/interactions/{interaction['id']}/workflow", headers=MANAGER
    )
    assert response.status_code == 200, response.text
    return response.json()


def _stage(view: dict, code: str) -> str:
    return next(stage["id"] for stage in view["version"]["stages"] if stage["code"] == code)


async def _move(client: AsyncClient, interaction: dict, to_stage: str, **extra):  # noqa: ANN202
    return await client.post(
        f"/api/v1/interactions/{interaction['id']}/transition",
        json={"to_stage_id": to_stage, **extra},
        headers=MANAGER,
    )


async def test_process_moves_along_template(
    client: AsyncClient, university: dict, workflow_version: dict
) -> None:
    interaction = await make_interaction(client, university["id"], MANAGER)
    view = await _view(client, interaction)

    assert view["status"] == "in_progress"
    assert [t["to_stage_id"] for t in view["available_transitions"]] == [
        _stage(view, "meeting")
    ]

    moved = await _move(client, interaction, _stage(view, "meeting"), comment="Назначена")
    assert moved.status_code == 200, moved.text
    body = moved.json()
    states = {item["stage_id"]: item["state"] for item in body["stage_states"]}
    assert states[_stage(view, "contact")] == "completed"
    assert states[_stage(view, "meeting")] == "active"
    # Заведено, запущено, переход.
    assert [event["event_type"] for event in body["events"]] == [
        "created",
        "started",
        "forward",
    ]


async def test_transition_outside_template_is_rejected(
    client: AsyncClient, university: dict, workflow_version: dict
) -> None:
    interaction = await make_interaction(client, university["id"], MANAGER)
    view = await _view(client, interaction)

    response = await _move(client, interaction, _stage(view, "signing"))
    assert response.status_code == 409
    assert response.json()["code"] == "workflow_rule_violated"


async def test_draft_cannot_move(client: AsyncClient, university: dict) -> None:
    draft = await make_interaction(client, university["id"], MANAGER, start=False)
    view = await _view(client, draft)
    response = await _move(client, draft, _stage(view, "meeting"))
    assert response.status_code == 409


async def test_final_stage_completes_with_outcome(
    client: AsyncClient, university: dict, workflow_version: dict
) -> None:
    interaction = await make_interaction(client, university["id"], MANAGER)
    view = await _view(client, interaction)

    await _move(client, interaction, _stage(view, "meeting"))
    finished = await _move(client, interaction, _stage(view, "signing"))
    assert finished.status_code == 200
    assert finished.json()["status"] == "completed"
    assert finished.json()["outcome"] == "successful"
    assert finished.json()["closed_at"] is not None


async def test_refusal_needs_reason_and_documents_block_forward(
    client: AsyncClient, university: dict
) -> None:
    version = await create_template(client, "С отказом", REFUSAL_GRAPH)
    program = (
        await client.post("/api/v1/catalog/programs", json={"name": "Курс"}, headers=ADMIN)
    ).json()
    interaction = await make_interaction(
        client,
        university["id"],
        MANAGER,
        template_id=version["template_id"],
        program_ids=[program["id"]],
    )
    view = await _view(client, interaction)

    # Этап сам ставит статус программ при входе.
    entered = await _move(client, interaction, _stage(view, "documents"))
    assert entered.status_code == 200, entered.text
    detail = (
        await client.get(f"/api/v1/interactions/{interaction['id']}", headers=MANAGER)
    ).json()
    assert detail["program_links"][0]["implementation_status"] == "in_progress"
    assert detail["missing_documents"] == ["contract"]

    blocked = await _move(client, interaction, _stage(view, "done"))
    assert blocked.status_code == 409
    assert blocked.json()["details"]["missing_documents"] == ["contract"]

    upload = await client.post(
        f"/api/v1/interactions/{interaction['id']}/attachments",
        files={"file": ("договор.pdf", b"%PDF-1.4", "application/pdf")},
        data={"document_type": "contract"},
        headers=MANAGER,
    )
    assert upload.status_code == 201, upload.text

    # На неуспешный финальный этап - только с причиной и комментарием.
    no_reason = await _move(
        client, interaction, _stage(view, "refusal"), comment="Вуз передумал"
    )
    assert no_reason.status_code == 409
    refused = await _move(
        client,
        interaction,
        _stage(view, "refusal"),
        comment="Вуз выбрал другого партнёра",
        closure_reason="university_refused",
    )
    assert refused.status_code == 200, refused.text
    assert refused.json()["status"] == "completed"
    assert refused.json()["outcome"] == "unsuccessful"
    assert refused.json()["closure_reason"] == "university_refused"


async def test_block_and_unblock_keep_reason(
    client: AsyncClient, university: dict, workflow_version: dict
) -> None:
    interaction = await make_interaction(client, university["id"], MANAGER)
    url = f"/api/v1/interactions/{interaction['id']}"
    blocked = await client.post(
        f"{url}/block", json={"reason": "Ждём приказ"}, headers=MANAGER
    )
    assert blocked.json()["status"] == "blocked"
    assert blocked.json()["blocked_reason"] == "Ждём приказ"
    view = await _view(client, interaction)
    moved = await _move(client, interaction, _stage(view, "meeting"))
    assert moved.status_code == 409

    unblocked = await client.post(
        f"{url}/unblock", json={"reason": "Приказ подписан"}, headers=MANAGER
    )
    assert unblocked.json()["status"] == "in_progress"
    assert unblocked.json()["blocked_reason"] is None


async def test_only_head_skips_required_stage(
    client: AsyncClient, university: dict, workflow_version: dict
) -> None:
    interaction = await make_interaction(client, university["id"], MANAGER)
    view = await _view(client, interaction)
    url = f"/api/v1/interactions/{interaction['id']}/skip"
    payload = {"to_stage_id": _stage(view, "meeting"), "reason": "Контакт уже есть"}

    denied = await client.post(url, json=payload, headers=MANAGER)
    assert denied.status_code == 409
    allowed = await client.post(url, json=payload, headers=HEAD)
    assert allowed.status_code == 200, allowed.text
    states = {item["stage_id"]: item["state"] for item in allowed.json()["stage_states"]}
    assert states[_stage(view, "contact")] == "skipped"


# --- Шаблоны и версии ---------------------------------------------------------------


async def test_published_version_cannot_be_edited(
    client: AsyncClient, workflow_version: dict
) -> None:
    response = await client.put(
        f"/api/v1/workflow/versions/{workflow_version['id']}/graph",
        json={
            "stages": [
                {"code": "only", "name": "Единственный", "is_initial": True, "is_final": True}
            ],
            "transitions": [],
        },
        headers=ADMIN,
    )
    assert response.status_code == 409
    assert "новую версию" in response.json()["message"]


async def test_database_guards_published_version(
    engine: AsyncEngine, workflow_version: dict
) -> None:
    """Обход API не помогает: опубликованную схему держит триггер базы."""
    stage_id = workflow_version["stages"][0]["id"]
    async with engine.connect() as connection:
        with pytest.raises(DBAPIError, match="опубликована"):
            await connection.execute(
                text("UPDATE workflow_stages SET sla_days = 99 WHERE id = :id"),
                {"id": stage_id},
            )
        await connection.rollback()
        # Название поправить можно - на ход процессов оно не влияет.
        await connection.execute(
            text("UPDATE workflow_stages SET name = 'Знакомство' WHERE id = :id"),
            {"id": stage_id},
        )
        await connection.rollback()


async def test_new_version_replaces_active_and_keeps_running_process(
    client: AsyncClient, university: dict, workflow_version: dict
) -> None:
    interaction = await make_interaction(client, university["id"], MANAGER)
    view = await _view(client, interaction)

    created = await client.post(
        f"/api/v1/workflow/templates/{workflow_version['template_id']}/versions",
        json={},
        headers=ADMIN,
    )
    assert created.status_code == 201
    draft = created.json()
    assert draft["version_number"] == 2
    assert draft["status"] == "draft"
    assert {stage["code"] for stage in draft["stages"]} == {"contact", "meeting", "signing"}

    saved = await client.put(
        f"/api/v1/workflow/versions/{draft['id']}/graph",
        json={
            "stages": [
                {"code": "contact", "name": "Первый контакт", "is_initial": True},
                {"code": "signing", "name": "Подписание", "is_final": True},
            ],
            "transitions": [{"from_code": "contact", "to_code": "signing"}],
        },
        headers=ADMIN,
    )
    assert saved.status_code == 200, saved.text
    published = await client.post(
        f"/api/v1/workflow/versions/{draft['id']}/publish", headers=ADMIN
    )
    assert published.status_code == 200, published.text
    assert published.json()["status"] == "active"

    versions = (
        await client.get(
            f"/api/v1/workflow/templates/{workflow_version['template_id']}/versions",
            headers=MANAGER,
        )
    ).json()
    by_number = {item["version_number"]: item for item in versions}
    # Первая версия устарела, но по ней ещё идёт процесс.
    assert by_number[1]["status"] == "deprecated"
    assert by_number[1]["open_instances_count"] == 1
    assert by_number[2]["status"] == "active"

    current = await _view(client, interaction)
    assert current["workflow_version_id"] == view["workflow_version_id"]
    assert len(current["version"]["stages"]) == 3

    # Процесс закрыт - устаревшая версия выводится из использования.
    await client.post(
        f"/api/v1/interactions/{interaction['id']}/cancel",
        json={"reason": "duplicate"},
        headers=MANAGER,
    )
    versions = (
        await client.get(
            f"/api/v1/workflow/templates/{workflow_version['template_id']}/versions",
            headers=MANAGER,
        )
    ).json()
    assert {item["version_number"]: item["status"] for item in versions}[1] == "retired"


async def test_new_draft_starts_on_active_version(
    client: AsyncClient, university: dict, workflow_version: dict
) -> None:
    """Черновик ещё без этапов: при запуске он встаёт на действующую версию."""
    draft = await make_interaction(client, university["id"], MANAGER, start=False)
    created = (
        await client.post(
            f"/api/v1/workflow/templates/{workflow_version['template_id']}/versions",
            json={},
            headers=ADMIN,
        )
    ).json()
    await client.post(f"/api/v1/workflow/versions/{created['id']}/publish", headers=ADMIN)

    started = await client.post(f"/api/v1/interactions/{draft['id']}/start", headers=MANAGER)
    assert started.status_code == 200, started.text
    assert started.json()["workflow_version_id"] == created["id"]


@pytest.mark.parametrize(
    ("graph", "problem"),
    [
        (
            {
                "stages": [
                    {"code": "one", "name": "Один"},
                    {"code": "two", "name": "Два", "is_final": True},
                ],
                "transitions": [{"from_code": "one", "to_code": "two"}],
            },
            "Стартовый этап",
        ),
        (
            {
                "stages": [{"code": "one", "name": "Один", "is_initial": True}],
                "transitions": [],
            },
            "финального этапа",
        ),
        (
            {
                "stages": [
                    {"code": "one", "name": "Один", "is_initial": True},
                    {"code": "lost", "name": "Потерянный"},
                    {"code": "end", "name": "Конец", "is_final": True},
                ],
                "transitions": [{"from_code": "one", "to_code": "end"}],
            },
            "недостижим",
        ),
        (
            {
                "stages": [
                    {"code": "one", "name": "Один", "is_initial": True},
                    {"code": "stuck", "name": "Тупик"},
                    {"code": "end", "name": "Конец", "is_final": True},
                ],
                "transitions": [
                    {"from_code": "one", "to_code": "stuck"},
                    {"from_code": "one", "to_code": "end"},
                ],
            },
            "тупик",
        ),
        (
            {
                "stages": [
                    {"code": "one", "name": "Один", "is_initial": True},
                    {"code": "end", "name": "Конец", "is_final": True},
                ],
                "transitions": [
                    {"from_code": "one", "to_code": "end"},
                    {"from_code": "end", "to_code": "one", "is_backward": True},
                ],
            },
            "финального",
        ),
    ],
    ids=["без старта", "без финала", "недостижимый", "тупик", "из финала"],
)
async def test_graph_is_validated_before_publishing(
    client: AsyncClient, graph: dict, problem: str
) -> None:
    created = await client.post(
        "/api/v1/workflow/templates",
        json={"name": f"Проверка {datetime.now(UTC).timestamp()}", "graph": graph},
        headers=ADMIN,
    )
    assert created.status_code == 201, created.text
    published = await client.post(
        f"/api/v1/workflow/versions/{created.json()['id']}/publish", headers=ADMIN
    )
    assert published.status_code == 409
    problems = " ".join(published.json()["details"]["problems"])
    assert problem.lower() in problems.lower(), problems


async def test_valid_graph_is_published(client: AsyncClient) -> None:
    version = await create_template(client, "Проверенный", TEST_GRAPH)
    assert version["status"] == "draft"


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


async def test_business_roles_cannot_edit_templates(client: AsyncClient) -> None:
    for headers in (MANAGER, HEAD):
        response = await client.post(
            "/api/v1/workflow/templates", json={"name": "Свой процесс"}, headers=headers
        )
        assert response.status_code == 403
