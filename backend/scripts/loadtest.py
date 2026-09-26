"""Нагрузочная проверка по нефункциональным требованиям ТЗ.

ТЗ требует: отклик интерфейса не дольше секунды, 50 параллельных
пользователей и не меньше 10 параллельных отчётов разной сложности.
Скрипт так и нагружает стенд: 50 «пользователей» ходят по сценарию
менеджера (главная, реестр, карточка договора, процесс, предпросмотр
отчёта), а 10 «аналитиков» параллельно выгружают отчёты в XLSX и PDF
с разными фильтрами. В конце - времена отклика и вывод по каждому пункту.

Запуск - при поднятом стенде; объём лучше добавить заранее (make seed-load):

    python -m scripts.loadtest                              # dev-заглушка, localhost
    python -m scripts.loadtest --duration 120 --users 50 --reports 10
    python -m scripts.loadtest --keycloak-url http://keycloak:8080  # под Keycloak

Под Keycloak сотрудники входят по паролю через отдельный клиент
edu-crm-loadtest: у клиента веб-интерфейса вход в обход страницы Keycloak
выключен. Клиент нагрузки тоже выключен, его включают на время замера
(python -m scripts.keycloak_setup --loadtest on, после - off). Пароли -
из переменной KEYCLOAK_USER_PASSWORDS (логин:пароль через запятую); хватит
одного менеджера и одного руководителя, нагрузка пойдёт от их имени.
Порядок целиком - cicd/README.md, «Нагрузочная проверка».
Не запускайте на стенде во время показа: нагрузка настоящая.
"""

from __future__ import annotations

import argparse
import asyncio
import os
import random
import statistics
import sys
import time
from collections import Counter, defaultdict
from dataclasses import dataclass, field

import httpx

from scripts.demo.people import EMPLOYEES, Employee
from scripts.keycloak_setup import LOADTEST_CLIENT_ID, SetupError, parse_passwords

INTERFACE_LIMIT = 1.0  # секунд, нефункциональное требование 1
EXPORT = "Выгрузка отчёта"


@dataclass
class Stats:
    samples: dict[str, list[float]] = field(default_factory=lambda: defaultdict(list))
    errors: Counter[str] = field(default_factory=Counter)


async def _headers(
    client: httpx.AsyncClient, args: argparse.Namespace, employee: Employee
) -> dict[str, str]:
    if not args.keycloak_url:
        return {"X-Dev-User": employee.username, "X-Dev-Roles": ",".join(employee.roles)}
    response = await client.post(
        f"{args.keycloak_url.rstrip('/')}/realms/{args.realm}/protocol/openid-connect/token",
        data={
            "client_id": LOADTEST_CLIENT_ID,
            "grant_type": "password",
            "username": employee.username,
            "password": args.passwords[employee.username],
        },
    )
    if response.status_code in (400, 401):
        raise SystemExit(
            f"Keycloak не выдал токен {employee.username}: {response.text[:200]}. "
            f"Клиент {LOADTEST_CLIENT_ID} включён (keycloak_setup --loadtest on)?"
        )
    response.raise_for_status()
    return {"Authorization": f"Bearer {response.json()['access_token']}"}


async def _hit(
    client: httpx.AsyncClient,
    stats: Stats,
    label: str,
    method: str,
    path: str,
    headers: dict[str, str],
    **kwargs: object,
) -> httpx.Response | None:
    started = time.perf_counter()
    try:
        response = await client.request(method, path, headers=headers, **kwargs)
    except httpx.HTTPError as exc:
        stats.errors[f"{label}: {type(exc).__name__}"] += 1
        return None
    stats.samples[label].append(time.perf_counter() - started)
    if response.status_code >= 400:
        stats.errors[f"{label}: HTTP {response.status_code}"] += 1
        return None
    return response


def _report_body(rng: random.Random) -> dict:
    """Отчёты разной сложности: от всего массива до узкой выборки."""
    filters: dict[str, object] = {}
    if rng.random() < 0.6:
        filters["date_from"] = rng.choice(("2024-09-01", "2025-01-01", "2025-09-01"))
    if rng.random() < 0.3:
        filters["period_basis"] = rng.choice(("signed", "created", "activity"))
    if rng.random() < 0.3:
        filters["statuses"] = rng.sample(["draft", "active", "suspended", "closed"], 2)
    columns = ["university", "direction", "program", "product", "contract_status", "manager"]
    if rng.random() < 0.5:
        columns += ["contract_number", "stage", "days_on_stage", "valid_to"]
    return {"filters": filters, "columns": columns}


async def _user(
    client: httpx.AsyncClient,
    stats: Stats,
    headers: dict[str, str],
    deadline: float,
    rng: random.Random,
) -> None:
    """Сценарий менеджера: главная, реестр, договор, процесс, отчёт."""
    while time.monotonic() < deadline:
        await _hit(client, stats, "Главная", "GET", "/dashboard", headers)
        page = await _hit(
            client, stats, "Реестр договоров", "GET", "/contracts?limit=50", headers
        )
        items = page.json().get("items", []) if page is not None else []
        if items:
            contract_id = rng.choice(items)["id"]
            await _hit(
                client, stats, "Карточка договора", "GET", f"/contracts/{contract_id}", headers
            )
            await _hit(
                client,
                stats,
                "Процесс по договору",
                "GET",
                f"/contracts/{contract_id}/workflow",
                headers,
            )
        await _hit(
            client,
            stats,
            "Предпросмотр отчёта",
            "POST",
            "/reports/preview",
            headers,
            json=_report_body(rng),
        )
        await asyncio.sleep(rng.uniform(0.3, 1.5))  # человек читает экран


async def _reporter(
    client: httpx.AsyncClient,
    stats: Stats,
    headers: dict[str, str],
    deadline: float,
    rng: random.Random,
) -> None:
    while time.monotonic() < deadline:
        kind = rng.choice(("xlsx", "pdf"))
        await _hit(
            client,
            stats,
            f"{EXPORT} {kind.upper()}",
            "POST",
            f"/reports/export?format={kind}",
            headers,
            json=_report_body(rng),
        )


def _print(stats: Stats, args: argparse.Namespace) -> bool:
    print(f"\n{'Действие':<26}{'запросов':>9}{'медиана':>9}{'p95':>8}{'макс':>8}{'≤1 с':>8}")
    ok = True
    for label, values in sorted(stats.samples.items()):
        ordered = sorted(values)
        p95 = ordered[min(len(ordered) - 1, int(len(ordered) * 0.95))]
        fast = sum(value <= INTERFACE_LIMIT for value in ordered) / len(ordered)
        print(
            f"{label:<26}{len(ordered):>9}{statistics.median(ordered):>8.2f}с"
            f"{p95:>7.2f}с{ordered[-1]:>7.2f}с{fast:>8.0%}"
        )
        if not label.startswith(EXPORT) and p95 > INTERFACE_LIMIT:
            ok = False

    if stats.errors:
        ok = False
        print("\nОшибки:")
        for label, count in stats.errors.most_common():
            print(f"  {label}: {count}")

    exports = sum(len(v) for k, v in stats.samples.items() if k.startswith(EXPORT))
    print(
        f"\n{args.users} пользователей и {args.reports} параллельных отчётов "
        f"за {args.duration} с, выгрузок выполнено: {exports}."
    )
    print(
        "Итог: отклик интерфейса в пределах секунды (p95), ошибок нет."
        if ok
        else "Итог: требования не выполнены - см. таблицу и ошибки выше."
    )
    return ok


def _fork(rng: random.Random) -> random.Random:
    """Свой генератор каждому участнику: прогон повторяется при том же --seed."""
    return random.Random(rng.getrandbits(64))


async def main(args: argparse.Namespace) -> bool:
    rng = random.Random(args.seed)
    people = [employee for employee in EMPLOYEES if employee.username != "admin"]
    heads = [employee for employee in EMPLOYEES if "head" in employee.roles]
    args.passwords = {}
    if args.keycloak_url:
        try:
            args.passwords = parse_passwords(os.environ.get("KEYCLOAK_USER_PASSWORDS", ""))
        except SetupError as exc:
            raise SystemExit(str(exc)) from exc
        # Пароли могли задать на сайте не всем: нагрузка идёт от тех, кто есть.
        people = [e for e in people if e.username in args.passwords]
        heads = [e for e in heads if e.username in args.passwords]
        if not people or not heads:
            raise SystemExit(
                "Для входа нужны пароли в KEYCLOAK_USER_PASSWORDS хотя бы одного "
                "менеджера и одного руководителя"
            )
    stats = Stats()
    limits = httpx.Limits(max_connections=args.users + args.reports + 10)
    async with httpx.AsyncClient(
        base_url=args.base_url.rstrip("/"), timeout=120, limits=limits
    ) as client:
        # Токены - по одному на сотрудника; «пользователи» ходят под ними по кругу.
        identities = [await _headers(client, args, employee) for employee in people]
        analysts = [await _headers(client, args, employee) for employee in heads]

        deadline = time.monotonic() + args.duration
        tasks = [
            _user(client, stats, identities[i % len(identities)], deadline, _fork(rng))
            for i in range(args.users)
        ]
        tasks += [
            _reporter(client, stats, analysts[i % len(analysts)], deadline, _fork(rng))
            for i in range(args.reports)
        ]
        print(
            f"Нагрузка на {args.base_url}: {args.users} пользователей, "
            f"{args.reports} отчётов, {args.duration} с..."
        )
        await asyncio.gather(*tasks)
    return _print(stats, args)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Нагрузочная проверка по ТЗ")
    parser.add_argument("--base-url", default="http://localhost:8000/api/v1")
    parser.add_argument(
        "--keycloak-url", default="", help="адрес Keycloak; пусто - dev-заглушка"
    )
    parser.add_argument("--realm", default="edu-crm")
    parser.add_argument("--users", type=int, default=50)
    parser.add_argument("--reports", type=int, default=10)
    parser.add_argument("--duration", type=int, default=60, help="секунд")
    parser.add_argument("--seed", type=int, default=1)
    sys.exit(0 if asyncio.run(main(parser.parse_args())) else 1)
