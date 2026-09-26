"""Заявки с сайта и анкеты LMS в формате кейсодержателя, статистика обучения.

Выгрузки загружаются файлом через POST /integrations/sources/{code}/upload -
тем же адаптером, что и ответ по сети. Данные вымышленные, форма - как
в переданных кейсодержателем файлах: пустой элемент в начале списка,
номер заявки с датой внутри (бывает испорченный), телефон со скобками.
"""

import json

from httpx import AsyncClient

from tests.conftest import ADMIN, HEAD, MANAGER, make_interaction

SITE = [
    None,
    {
        "Номер заявки": "ORD-20260313051569-OYJRVN",  # секунда 69 - даты нет
        "Курс": "Анализ данных без программирования",
        "Фамилия": "Гусева",
        "Имя": "Анна",
        "Отчество": "Петровна",
        "Телефон": "7 (900) 023-43-65",
        "Email": "guseva.a@example.com",
        "Номер потока": 1,
    },
    {
        "Номер заявки": "ORD-20260522061330-2LT0MG",
        "Курс": "Анализ данных без программирования",
        "Фамилия": "Тарасов",
        "Имя": "Олег",
        "Отчество": "Юрьевич",
        "Телефон": "7 (900) 736-13-51",
        "Email": "tarasov.o@example.com",
        "Номер потока": 2,
    },
    {
        "Номер заявки": "ORD-20260904075403-ZXFSZX",
        "Курс": "Промпт-инжиниринг",
        "Фамилия": "Власова",
        "Имя": "Ирина",
        "Отчество": "Николаевна",
        "Телефон": "7 (900) 458-34-34",
        "Email": "vlasova.i@example.com",
        "Номер потока": 1,
    },
    {"Номер заявки": "ORD-без-курса", "Фамилия": "Без курса"},
]

LMS = [
    {
        "Фамилия": "Гусева",
        "Имя": "Анна",
        "Отчествопри наличии)": "Петровна",  # заголовок, испорченный при выгрузке
        "Номер телефона": 79000234365,
        "Email": "guseva.a@example.com",
        "СНИЛС": "000-000-000 00",
        "Серия паспорта": "0000",
        "Номер паспорта": "000000",
        "Пол": "Ж",
        "Образование": "Высшее образование – бакалавриат",
        "Регион регистрации": "Москва",
    },
    {
        # Совпадает с заявкой только по телефону: почта в анкете другая.
        "Фамилия": "Власова",
        "Имя": "Ирина",
        "Номер телефона": "8 900 458 34 34",
        "Email": "irina.vlasova@example.ru",
    },
]


async def upload(client: AsyncClient, code: str, payload: object, headers=ADMIN) -> dict:  # noqa: ANN001
    response = await client.post(
        f"/api/v1/integrations/sources/{code}/upload",
        files={"file": ("export.json", json.dumps(payload, ensure_ascii=False).encode())},
        headers=headers,
    )
    assert response.status_code == 200, response.text
    return response.json()


async def map_courses(client: AsyncClient) -> list[str]:
    """Администратор заводит программы для новых курсов из очереди сопоставления."""
    queue = (await client.get("/api/v1/integrations/mappings", headers=ADMIN)).json()
    names = []
    for item in queue:
        if item["entity_type"] != "course" or item["status"] != "pending":
            continue
        created = await client.post(
            f"/api/v1/integrations/mappings/{item['id']}/create", headers=ADMIN
        )
        assert created.status_code == 200, created.text
        names.append(item["external_name"])
    return names


async def allow_personal_data(client: AsyncClient) -> None:
    orlova = (await client.get("/api/v1/me", headers=HEAD)).json()
    response = await client.patch(
        f"/api/v1/users/{orlova['id']}",
        json={"permissions": ["view_personal_data"]},
        headers=ADMIN,
    )
    assert response.status_code == 200, response.text


async def test_site_applications_in_case_format(client: AsyncClient) -> None:
    run = await upload(client, "site", SITE)
    # null и заявка без курса пропущены: запуск загрузил не всё.
    assert run["status"] == "partial"
    assert run["records_received"] == 5
    assert run["records_created"] == 3
    assert run["records_failed"] == 2
    # Курсов нет в справочнике: по названию программу не выбираем - очередь.
    assert run["records_pending"] == 2
    assert "Ждут ручного сопоставления" in run["notes"]
    assert "взаимодействия с вузами они не создают" in run["notes"]

    assert sorted(await map_courses(client)) == [
        "Анализ данных без программирования",
        "Промпт-инжиниринг",
    ]
    programs = (await client.get("/api/v1/catalog/programs", headers=ADMIN)).json()
    assert {"Анализ данных без программирования", "Промпт-инжиниринг"} <= {
        item["name"] for item in programs
    }

    await allow_personal_data(client)
    applications = (await client.get("/api/v1/statistics/applications", headers=HEAD)).json()
    assert applications["total"] == 3
    by_number = {item["external_id"]: item for item in applications["items"]}
    # Телефон приведён к цифрам, дата подачи взята из номера заявки.
    assert by_number["ORD-20260522061330-2LT0MG"]["phone"] == "79007361351"
    assert by_number["ORD-20260522061330-2LT0MG"]["submitted_at"].startswith(
        "2026-05-22T06:13:30"
    )
    assert by_number["ORD-20260904075403-ZXFSZX"]["full_name"] == "Власова Ирина Николаевна"
    assert by_number["ORD-20260904075403-ZXFSZX"]["course_name"] == "Промпт-инжиниринг"

    # Повторная выгрузка обновляет заявки, а не множит их.
    again = await upload(client, "site", SITE)
    assert again["records_created"] == 0
    assert again["records_updated"] == 3
    assert again["records_pending"] == 0


async def test_lms_questionnaire_is_minimized(client: AsyncClient) -> None:
    run = await upload(client, "lms", LMS)
    assert run["records_created"] == 2
    # Паспорт и СНИЛС не сохраняются, и об этом сказано в журнале.
    assert "СНИЛС" in run["notes"]
    assert "Серия паспорта" in run["notes"]

    audit = (
        await client.get("/api/v1/audit", params={"entity_type": "learners"}, headers=ADMIN)
    ).json()
    assert audit["total"] == 2
    # В журнале изменений персональные данные замаскированы.
    assert audit["items"][0]["after_data"]["last_name"] == "***"
    assert "passport" not in json.dumps(audit["items"][0]["after_data"])


async def test_statistics_rank_programs(client: AsyncClient) -> None:
    await upload(client, "site", SITE)
    await map_courses(client)
    await upload(client, "lms", LMS)

    stats = (await client.post("/api/v1/statistics/programs", json={}, headers=MANAGER)).json()
    assert stats["totals"] == {
        "applications": 3,
        "learners": 2,  # Гусева по почте, Власова по телефону
        "enrollments": 2,
        "streams": 3,
        "programs": 2,
        "directions": 1,
    }
    first, second = stats["rows"]
    assert (first["rank"], first["program"]) == (1, "Анализ данных без программирования")
    assert (first["applications"], first["learners"], first["streams"]) == (2, 1, 2)
    assert first["conversion"] == 50.0
    assert (second["program"], second["learners"]) == ("Промпт-инжиниринг", 1)

    charts = {chart["key"]: chart for chart in stats["charts"]}
    by_program = {
        item["label"]: item["value"] for item in charts["applications_by_program"]["items"]
    }
    assert by_program == {"Анализ данных без программирования": 2, "Промпт-инжиниринг": 1}
    education = charts["learners_by_education"]["items"]
    assert {"label": "Высшее образование – бакалавриат", "value": 1} in education

    # Фильтр по периоду подачи. У заявки с испорченным номером даты нет -
    # она датирована моментом получения и в период до 10 сентября не входит.
    filtered = (
        await client.post(
            "/api/v1/statistics/programs",
            json={"date_from": "2026-05-01", "date_to": "2026-09-10"},
            headers=MANAGER,
        )
    ).json()
    assert filtered["totals"]["applications"] == 2


async def test_same_stream_number_in_other_period_is_other_stream(
    client: AsyncClient,
) -> None:
    """Поток опознаётся стабильным ключом с периодом: «поток 1» весной и
    осенью - разные потоки."""
    spring = dict(SITE[1]) | {"Номер заявки": "ORD-20260310090000-SPRNG1"}
    autumn = dict(SITE[1]) | {
        "Номер заявки": "ORD-20260915090000-AUTMN1",
        "Email": "other@example.com",
    }
    await upload(client, "site", [spring, autumn])
    await map_courses(client)
    stats = (await client.post("/api/v1/statistics/programs", json={}, headers=MANAGER)).json()
    assert stats["totals"]["applications"] == 2
    assert stats["totals"]["streams"] == 2


async def test_statistics_exports(client: AsyncClient) -> None:
    await upload(client, "site", SITE)
    await map_courses(client)
    for fmt, signature in (("xlsx", b"PK"), ("xls", b"\xd0\xcf"), ("pdf", b"%PDF")):
        response = await client.post(
            f"/api/v1/statistics/export?format={fmt}", json={}, headers=MANAGER
        )
        assert response.status_code == 200, response.text
        assert response.content.startswith(signature)

    chart = await client.post(
        "/api/v1/statistics/chart?key=applications_by_month&format=png",
        json={},
        headers=MANAGER,
    )
    assert chart.status_code == 200
    assert chart.content[:4] == b"\x89PNG"


async def test_personal_data_is_closed_without_permission(client: AsyncClient) -> None:
    for headers in (MANAGER, HEAD):
        response = await client.get("/api/v1/statistics/applications", headers=headers)
        assert response.status_code == 403
    upload_attempt = await client.post(
        "/api/v1/integrations/sources/site/upload",
        files={"file": ("export.json", b"[]")},
        headers=MANAGER,
    )
    assert upload_attempt.status_code == 403


async def test_student_application_does_not_create_interaction(
    client: AsyncClient, university: dict, workflow_version: dict
) -> None:
    """Заявка студента - только статистика: вуз заявителя - разрез отчёта."""
    await make_interaction(client, university["id"], MANAGER)
    item = dict(SITE[3]) | {"Вуз": university["name"]}
    other = dict(SITE[1]) | {"Вуз": university["name"]}
    run = await upload(client, "site", [item, other])
    assert run["records_created"] == 2

    interactions = (await client.get("/api/v1/interactions", headers=HEAD)).json()
    assert interactions["total"] == 1
    comments = (
        await client.get(
            f"/api/v1/interactions/{interactions['items'][0]['id']}/comments",
            headers=MANAGER,
        )
    ).json()
    assert comments == []

    await allow_personal_data(client)
    applications = (await client.get("/api/v1/statistics/applications", headers=HEAD)).json()
    assert {item["university_id"] for item in applications["items"]} == {university["id"]}


async def test_bad_json_is_reported(client: AsyncClient) -> None:
    response = await client.post(
        "/api/v1/integrations/sources/site/upload",
        files={"file": ("export.json", b"{not json")},
        headers=ADMIN,
    )
    assert response.status_code == 400
    assert response.json()["code"] == "integration_failed"
