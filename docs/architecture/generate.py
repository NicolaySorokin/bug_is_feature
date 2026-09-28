"""Модель архитектуры в формате Archi (ArchiMate 3.1).

Модель собирается этим скриптом, чтобы её было удобно править и сравнивать.
Результат docs/architecture/edu-crm.archimate открывается в Archi через File → Open.

    python docs/architecture/generate.py
"""

from __future__ import annotations

import uuid
from pathlib import Path
from xml.sax.saxutils import escape

NS = uuid.UUID("7b0f7a8e-5a4c-4f1e-9d57-3c2a8e7f0b11")


def ident(key: str) -> str:
    return "id-" + uuid.uuid5(NS, key).hex


# Элементы: ключ, тип ArchiMate, имя, папка, документация.
ELEMENTS: dict[str, tuple[str, str, str, str]] = {
    # Бизнес. Ключ "kam" оставлен, чтобы Archi узнал тот же элемент.
    "kam": ("BusinessActor", "Менеджер", "business", "Ведёт свои взаимодействия с вузами"),
    "head": (
        "BusinessActor",
        "Руководитель",
        "business",
        "Команда менеджеров: ответственные, блокировки, исключения, проверка вузов",
    ),
    "admin": (
        "BusinessActor",
        "Администратор",
        "business",
        "Права, справочники, шаблоны процессов, обмен; без бизнес-данных",
    ),
    "sysadmin": ("BusinessActor", "Системный администратор", "business", "Установка, обновление, резервные копии"),
    "university": ("BusinessActor", "Вуз / школа", "business", "Партнёр ИТ Школы"),
    "proc": (
        "BusinessProcess",
        "Взаимодействие с вузом (14 этапов)",
        "business",
        "Поиск контактов → ... → Итоговый контроль; шаблон процесса с версиями",
    ),
    "reporting": ("BusinessProcess", "Отчётность по взаимодействию и обучению", "business", ""),
    "interaction": (
        "BusinessObject",
        "Взаимодействие с вузом",
        "business",
        "Центральный объект: вуз, ответственный, статус и результат, процесс, "
        "программы и продукты, контакты, файлы",
    ),
    "contract": ("BusinessObject", "Договор (0..1)", "business", "Необязательная часть взаимодействия: подписание, сроки, статус, лицензии"),
    "program": ("BusinessObject", "ИТ-программа", "business", ""),
    "product": ("BusinessObject", "ИТ-продукт и лицензия", "business", ""),
    "application": ("BusinessObject", "Заявка на обучение", "business", "С сайта ИТ Школы"),
    "learner": ("BusinessObject", "Обучающийся", "business", "Из LMS; персональные данные минимизированы"),
    # Приложения
    "spa": ("ApplicationComponent", "Клиентская часть (React SPA)", "application", "Дизайн-система Atomaro, тема Ростелекома"),
    "api": ("ApplicationComponent", "EDU CRM API (FastAPI)", "application", "REST /api/v1, OpenAPI /docs"),
    "kc": ("ApplicationComponent", "Keycloak (реалм edu-crm)", "application", "OIDC, PKCE, роли manager/head/admin"),
    "lms": ("ApplicationComponent", "LMS ИТ Школы", "application", "Внешняя система"),
    "site": ("ApplicationComponent", "Сайт ИТ Школы", "application", "Внешняя система"),
    "svc_contracts": ("ApplicationService", "Взаимодействия, вузы, программы и продукты, договоры", "application", ""),
    "svc_workflow": ("ApplicationService", "Рабочий процесс: переходы, комментарии, файлы", "application", ""),
    "svc_reports": ("ApplicationService", "Отчёты и диаграммы (XLSX, XLS, PDF, PNG, JSON)", "application", ""),
    "svc_stats": ("ApplicationService", "Статистика обучения", "application", ""),
    "svc_import": ("ApplicationService", "Загрузка каталогов из Excel", "application", ""),
    "svc_sync": ("ApplicationService", "Обмен с LMS и сайтом", "application", ""),
    "svc_admin": ("ApplicationService", "Пользователи, права, журнал, настройки", "application", ""),
    "svc_auth": ("ApplicationService", "Вход и роли", "application", ""),
    "data_crm": ("DataObject", "Данные CRM", "application", "Взаимодействия, процессы, договоры, справочники, журнал изменений"),
    "data_files": ("DataObject", "Файлы вложений", "application", "PNG, JPEG, PDF, ZIP, GZIP, RAR, DOC(X), XLS(X)"),
    # Технологии
    "server": ("Node", "Сервер Linux (4 ГБ, Docker Compose)", "technology", ""),
    "nginx": ("SystemSoftware", "Nginx 1.27 (образ edu-crm-web)", "technology", "TLS, CSP, статика, прокси"),
    "uvicorn": ("SystemSoftware", "Python 3.12 / Uvicorn (образ edu-crm-api)", "technology", ""),
    "pg": ("SystemSoftware", "PostgreSQL 16", "technology", "Том pgdata"),
    "kcsw": ("SystemSoftware", "Keycloak 26", "technology", ""),
    "img_web": ("Artifact", "Образ edu-crm-web", "technology", "Nginx + собранная клиентская часть"),
    "img_api": ("Artifact", "Образ edu-crm-api", "technology", "Python 3.12, FastAPI, шрифты для PDF"),
    "vol_pg": ("Artifact", "Том pgdata", "technology", ""),
    "storage": ("Artifact", "Том api_storage", "technology", ""),
    "net": ("CommunicationNetwork", "Интернет, HTTPS", "technology", ""),
    "ci": ("SystemSoftware", "GitHub Actions: CI и деплой", "technology", "Сборка образов, выкладка по SSH, откат"),
}

# Связи: тип, источник, цель, имя.
RELATIONS: list[tuple[str, str, str, str]] = [
    ("Assignment", "kam", "proc", ""),
    ("Assignment", "head", "proc", ""),
    ("Assignment", "head", "reporting", ""),
    ("Association", "university", "proc", ""),
    ("Access", "proc", "interaction", ""),
    ("Aggregation", "interaction", "contract", "0..1"),
    ("Aggregation", "interaction", "program", ""),
    ("Aggregation", "interaction", "product", ""),
    ("Access", "reporting", "application", ""),
    ("Access", "reporting", "learner", ""),
    ("Serving", "svc_contracts", "proc", ""),
    ("Serving", "svc_workflow", "proc", ""),
    ("Serving", "svc_reports", "reporting", ""),
    ("Serving", "svc_stats", "reporting", ""),
    ("Serving", "svc_import", "admin", ""),
    ("Serving", "svc_admin", "admin", ""),
    ("Serving", "svc_auth", "kam", ""),
    ("Realization", "api", "svc_contracts", ""),
    ("Realization", "api", "svc_workflow", ""),
    ("Realization", "api", "svc_reports", ""),
    ("Realization", "api", "svc_stats", ""),
    ("Realization", "api", "svc_import", ""),
    ("Realization", "api", "svc_sync", ""),
    ("Realization", "api", "svc_admin", ""),
    ("Realization", "kc", "svc_auth", ""),
    ("Serving", "api", "spa", "REST JSON"),
    ("Serving", "kc", "spa", "OIDC + PKCE"),
    ("Serving", "kc", "api", "JWKS, Admin REST API"),
    ("Flow", "lms", "api", "программы, обучающиеся"),
    ("Flow", "site", "api", "заявки"),
    ("Access", "api", "data_crm", ""),
    ("Access", "api", "data_files", ""),
    ("Composition", "server", "nginx", ""),
    ("Composition", "server", "uvicorn", ""),
    ("Composition", "server", "pg", ""),
    ("Composition", "server", "kcsw", ""),
    ("Assignment", "server", "img_web", ""),
    ("Assignment", "server", "img_api", ""),
    ("Assignment", "server", "vol_pg", ""),
    ("Assignment", "server", "storage", ""),
    ("Realization", "img_web", "spa", ""),
    ("Realization", "img_api", "api", ""),
    ("Realization", "vol_pg", "data_crm", ""),
    ("Realization", "storage", "data_files", ""),
    ("Serving", "nginx", "spa", ""),
    ("Serving", "uvicorn", "api", ""),
    ("Serving", "kcsw", "kc", ""),
    ("Serving", "pg", "api", "SQL"),
    ("Association", "net", "server", ""),
    ("Association", "ci", "server", "выкладка релизов"),
    ("Association", "sysadmin", "ci", ""),
]

# Виды: имя и координаты элементов.
W, H = 180, 60
VIEWS: dict[str, dict[str, tuple[int, int]]] = {
    "1. Бизнес-контекст": {
        "kam": (20, 20), "head": (220, 20), "admin": (420, 20), "university": (620, 20),
        "proc": (120, 140), "reporting": (420, 140),
        "interaction": (120, 270), "application": (620, 270), "learner": (820, 270),
        "contract": (20, 390), "program": (220, 390), "product": (420, 390),
    },
    "2. Приложения": {
        "kam": (20, 20), "head": (220, 20), "admin": (420, 20),
        "svc_auth": (20, 130), "svc_contracts": (220, 130), "svc_workflow": (420, 130),
        "svc_reports": (620, 130), "svc_stats": (820, 130), "svc_import": (1020, 130), "svc_admin": (1220, 130),
        "svc_sync": (1020, 20),
        "spa": (120, 260), "kc": (20, 390), "api": (520, 260),
        "lms": (900, 260), "site": (900, 390),
        "data_crm": (420, 390), "data_files": (620, 390),
    },
    "3. Развёртывание": {
        "net": (20, 20), "server": (380, 20), "ci": (740, 20), "sysadmin": (1000, 20),
        "nginx": (20, 150), "uvicorn": (240, 150), "kcsw": (460, 150), "pg": (680, 150),
        "img_web": (20, 270), "img_api": (240, 270), "vol_pg": (680, 270), "storage": (900, 270),
        "spa": (20, 400), "api": (240, 400), "kc": (460, 400), "data_crm": (680, 400), "data_files": (900, 400),
    },
}

FOLDERS = [
    ("Strategy", "strategy"),
    ("Business", "business"),
    ("Application", "application"),
    ("Technology &amp; Physical", "technology"),
    ("Motivation", "motivation"),
    ("Implementation &amp; Migration", "implementation_migration"),
    ("Other", "other"),
]


def attr(value: str) -> str:
    return escape(value, {'"': "&quot;"})


def build() -> str:
    lines = [
        '<?xml version="1.0" encoding="UTF-8"?>',
        '<archimate:model xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance" '
        'xmlns:archimate="http://www.archimatetool.com/archimate" '
        f'name="EDU CRM - взаимодействие ИТ Школы Ростелекома с вузами" id="{ident("model")}" version="5.0.0">',
    ]
    for title, kind in FOLDERS:
        items = [(key, spec) for key, spec in ELEMENTS.items() if spec[2] == kind]
        if not items:
            lines.append(f'  <folder name="{title}" id="{ident("folder-" + kind)}" type="{kind}"/>')
            continue
        lines.append(f'  <folder name="{title}" id="{ident("folder-" + kind)}" type="{kind}">')
        for key, (etype, name, _, doc) in items:
            if doc:
                lines.append(f'    <element xsi:type="archimate:{etype}" name="{attr(name)}" id="{ident(key)}">')
                lines.append(f"      <documentation>{escape(doc)}</documentation>")
                lines.append("    </element>")
            else:
                lines.append(f'    <element xsi:type="archimate:{etype}" name="{attr(name)}" id="{ident(key)}"/>')
        lines.append("  </folder>")

    lines.append(f'  <folder name="Relations" id="{ident("folder-relations")}" type="relations">')
    for rtype, source, target, name in RELATIONS:
        rid = ident(f"rel-{rtype}-{source}-{target}")
        name_attr = f' name="{attr(name)}"' if name else ""
        lines.append(
            f'    <element xsi:type="archimate:{rtype}Relationship"{name_attr} id="{rid}" '
            f'source="{ident(source)}" target="{ident(target)}"/>'
        )
    lines.append("  </folder>")

    lines.append(f'  <folder name="Views" id="{ident("folder-views")}" type="diagrams">')
    for view, placement in VIEWS.items():
        lines.append(f'    <element xsi:type="archimate:ArchimateDiagramModel" name="{attr(view)}" id="{ident("view-" + view)}">')
        for key, (x, y) in placement.items():
            node = ident(f"node-{view}-{key}")
            lines.append(f'      <child xsi:type="archimate:DiagramObject" id="{node}" archimateElement="{ident(key)}">')
            lines.append(f'        <bounds x="{x}" y="{y}" width="{W}" height="{H}"/>')
            for rtype, source, target, _ in RELATIONS:
                if source == key and target in placement:
                    lines.append(
                        f'        <sourceConnection xsi:type="archimate:Connection" '
                        f'id="{ident(f"conn-{view}-{rtype}-{source}-{target}")}" source="{node}" '
                        f'target="{ident(f"node-{view}-{target}")}" '
                        f'archimateRelationship="{ident(f"rel-{rtype}-{source}-{target}")}"/>'
                    )
            lines.append("      </child>")
        lines.append("    </element>")
    lines.append("  </folder>")
    lines.append("</archimate:model>")
    return "\n".join(lines) + "\n"


if __name__ == "__main__":
    target = Path(__file__).with_name("edu-crm.archimate")
    target.write_text(build(), encoding="utf-8")
    print(f"Модель сохранена: {target}")
