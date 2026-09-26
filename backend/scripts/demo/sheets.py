"""Таблицы для проверки импорта каталогов (требование 1 ТЗ).

Заголовки берутся из описания загрузок в app/services/imports.py, поэтому
файлы не разойдутся с тем, что система ожидает. Строки ссылаются на вузы,
договоры, менеджеров и контакты из демоданных: на базе с демоданными часть
строк обновит существующие взаимодействия, часть - заведёт новые (с
договором, составом и лицензиями - через модель взаимодействия).

Даты здесь абсолютные: файлы лежат в репозитории и загружаются руками.
"""

from __future__ import annotations

from datetime import date

from app.services.imports import CATALOG_SPEC, PRODUCT_SPEC, PROGRAM_SPEC, UNIVERSITY_SPEC
from scripts.demo.catalog import CONTACTS_PER_UNIVERSITY, UNIVERSITY_BY_KEY
from scripts.demo.people import EMPLOYEE_BY_USERNAME, university_contacts

Sheet = tuple[list[str], list[list[object]]]


def _university(key: str) -> str:
    return UNIVERSITY_BY_KEY[key].name


def _manager(username: str) -> str:
    return EMPLOYEE_BY_USERNAME[username].full_name


def _contact(key: str, index: int = 0) -> str:
    return university_contacts(key, CONTACTS_PER_UNIVERSITY)[index].full_name


def _titles(spec) -> list[str]:  # noqa: ANN001 - ImportSpec
    return [field.title for field in spec.fields]


def _with_program(rows: list[list[object]], programs: dict[str, str]) -> list[list[object]]:
    """Колонка «ИТ-программа» после продукта: заполнена там, где программа
    не следует из справочного соответствия программ и продуктов однозначно."""
    return [[*row[:3], programs.get(str(row[3])), *row[3:]] for row in rows]


def catalog() -> Sheet:
    """Сводный каталог: десять колонок из требования 1 ТЗ и необязательная
    «ИТ-программа».

    Первые строки обновляют договоры из демоданных, дальше - новые
    взаимодействия с договорами в знакомых вузах и три вуза, которых
    в системе ещё нет (они придут «на проверку»). Даты встречаются и
    ячейкой-датой, и строкой; срок лицензии - годом, числом лет и датой.
    """
    rows = [
        # Обновления договоров из демоданных: без дат лицензия не меняется.
        [_university("mtuci"), "Ростелеком", "Платформа онлайн-обучения", "ДГ-2025-017",
         None, None, "Передано", _manager("petrov"), _contact("mtuci"),
         "Вуз готовит заявку на продление"],
        [_university("sut"), "Ростелеком", "Песочница DevOps", "ДГ-2026-047",
         None, None, "В работе", _manager("petrov"), _contact("sut"),
         "Стенд разворачивают во втором компьютерном классе"],
        [_university("nstu"), "Postgres Professional", "Postgres Pro Enterprise",
         "ДГ-2026-058", None, None, "В работе", _manager("ivanova"), _contact("nstu"), None],
        # Продление истёкшей лицензии: после импорта тревога по ней уходит.
        [_university("urfu"), "Ростелеком", "Стенд киберполигона", "ДГ-2026-012",
         date(2026, 9, 15), 2027, "Передано", _manager("orlova"), _contact("urfu"),
         "Лицензия продлена до конца 2027 года"],
        # Новые договоры в вузах из демоданных.
        [_university("itmo"), "Солар", "Solar appScreener", "ДГ-2026-201",
         date(2026, 9, 1), 2027, "В работе", _manager("smirnov"), _contact("itmo"),
         "Лаборатория анализа кода"],
        [_university("mipt"), "Postgres Professional", "Postgres Pro Enterprise",
         "ДГ-2026-202", "15.08.2026", 2, "Передано", _manager("kuznetsova"),
         _contact("mipt", 1), None],
        [_university("mpei"), "Группа Астра", "Astra Linux Special Edition", "ДГ-2026-203",
         date(2026, 8, 20), 2028, "В работе", _manager("sokolov"), _contact("mpei"),
         "Два компьютерных класса"],
        [_university("mpei"), "РЕД СОФТ", "РЕД ОС", "ДГ-2026-203",
         date(2026, 8, 20), 2028, "Не начато", _manager("sokolov"), _contact("mpei"), None],
        [_university("tusur"), "Positive Technologies", "PT Application Inspector",
         "ДГ-2026-204", "03.09.2026", 2027, "В работе", _manager("popova"),
         _contact("tusur"), None],
        [_university("kpfu"), "Ростелеком", "Платформа онлайн-обучения", "ДГ-2026-205",
         date(2026, 6, 10), 1, "Передано", _manager("egorova"), _contact("kpfu"), None],
        [_university("kantiana"), "Ростелеком", "Песочница DevOps", "ДГ-2026-206",
         date(2026, 7, 1), 2027, "Приостановлено", _manager("pavlov"),
         _contact("kantiana"), "Вуз перенёс старт программы на весенний семестр"],
        [_university("vsu"), "Солар", "Solar Dozor", "ДГ-2026-207",
         date(2026, 5, 12), date(2027, 6, 30), "Передано", _manager("stepanova"),
         _contact("vsu", 1), None],
        [_university("uust"), "Группа Астра", "RuBackup", "ДГ-2026-208",
         date(2026, 9, 5), 2027, "В работе", _manager("nikolaev"), _contact("uust"), None],
        [_university("uniyar"), "Ростелеком", "Платформа онлайн-обучения", "ДГ-2026-209",
         date(2026, 9, 10), 2027, "Не начато", _manager("belova"), _contact("uniyar"),
         "Ждём список групп от вуза"],
        [_university("spbstu"), "Positive Technologies", "MaxPatrol SIEM", "ДГ-2026-210",
         date(2026, 4, 22), 3, "Передано", _manager("fedorov"), _contact("spbstu"), None],
        [_university("omgtu"), "Ростелеком", "Стенд киберполигона", "ДГ-2026-211",
         date(2026, 9, 18), 2027, "В работе", _manager("zakharova"), _contact("omgtu"), None],
        # Вузов из этих строк в системе ещё нет - импорт их заведёт.
        ["Тульский государственный университет", "Ростелеком",
         "Платформа онлайн-обучения", "ДГ-2026-212", date(2026, 9, 1), 2027, "В работе",
         _manager("petrov"), "Лаврова Ирина Сергеевна", "Первый договор с вузом"],
        ["Вятский государственный университет", "Группа Астра",
         "Astra Linux Special Edition", "ДГ-2026-213", date(2026, 8, 25), 2027,
         "Передано", _manager("volkov"), "Чернов Антон Викторович", None],
        ["Вятский государственный университет", "Код Безопасности", "Secret Net Studio",
         "ДГ-2026-213", date(2026, 8, 25), 2027, "Не начато", _manager("volkov"),
         "Чернов Антон Викторович", "Новый вендор и продукт - появятся в справочниках"],
        ["Петрозаводский государственный университет", "Ростелеком",
         "Симулятор сетевой инфраструктуры", "ДГ-2026-214", "12.09.2026", 2027,
         "В работе", _manager("lebedev"), "Руденко Полина Андреевна", None],
    ]  # fmt: skip
    programs = {
        "ДГ-2026-201": "Анализ защищённости приложений",
        "ДГ-2026-204": "Анализ защищённости приложений",
        "ДГ-2026-212": "Python-разработчик",
    }
    return _titles(CATALOG_SPEC), _with_program(rows, programs)


def catalog_other_headers() -> Sheet:
    """Тот же каталог, но колонки названы иначе, переставлены и есть лишняя.

    Почти все заголовки система узнаёт по синонимам. «Ответственный от вуза»
    среди синонимов нет - эту колонку сопоставляют вручную на шаге проверки.
    """
    headers = [
        "Договор", "Вуз", "Регион", "Производитель", "Продукт", "Дата подписания лицензии",
        "Срок лицензии", "Статус передачи", "Менеджер", "Ответственный от вуза", "Примечание",
    ]  # fmt: skip
    rows = [
        ["ДГ-2026-231", _university("sfu"), "Красноярский край", "Postgres Professional",
         "Postgres Pro Enterprise", date(2026, 9, 2), 2027, "В работе", _manager("semenov"),
         _contact("sfu"), None],
        ["ДГ-2026-232", _university("dvfu"), "Приморский край", "Ростелеком",
         "Симулятор сетевой инфраструктуры", date(2026, 8, 28), 2027, "Передано",
         _manager("alekseeva"), _contact("dvfu"), "Кампус на острове Русский"],
        ["ДГ-2026-233", _university("utmn"), "Тюменская область", "Ростелеком",
         "Платформа онлайн-обучения", date(2026, 9, 12), 2, "В работе",
         _manager("zakharova"), _contact("utmn"), None],
        ["ДГ-2026-234", _university("istu"), "Иркутская область", "РЕД СОФТ", "РЕД ОС",
         date(2026, 9, 8), 2027, "Не начато", _manager("zaitsev"), _contact("istu", 1),
         None],
        ["ДГ-2026-235", _university("vlsu"), "Владимирская область", "Ростелеком",
         "Платформа онлайн-обучения", date(2026, 9, 3), 2027, "В работе",
         _manager("belova"), _contact("vlsu"), None],
        ["ДГ-2026-236", _university("pstu"), "Пермский край", "Ростелеком",
         "Песочница DevOps", date(2026, 9, 14), 2027, "В работе", _manager("volkov"),
         _contact("pstu"), "Второй поток по DevOps"],
    ]  # fmt: skip
    return headers, rows


def catalog_errors() -> Sheet:
    """Каталог с ошибками: проверка перед импортом должна их показать.

    Строки 2 и 9 правильные. Остальные: пустой вуз, пустой номер договора,
    несуществующая дата, непонятный срок лицензии, неизвестный статус.
    В строке 8 менеджера нет среди сотрудников - это не ошибка, а
    предупреждение: взаимодействие загрузится без ответственного.
    """
    rows = [
        [_university("unn"), "Ростелеком", "Платформа онлайн-обучения", "ДГ-2026-240",
         date(2026, 9, 1), 2027, "В работе", _manager("novikov"), _contact("unn"), None],
        [None, "Ростелеком", "Песочница DevOps", "ДГ-2026-241", date(2026, 9, 1), 2027,
         "В работе", _manager("novikov"), None, "Не указан вуз"],
        [_university("unn"), "Ростелеком", "Песочница DevOps", None, date(2026, 9, 1), 2027,
         "В работе", _manager("novikov"), None, "Не указан номер договора"],
        [_university("ssau"), "Ростелеком", "Платформа онлайн-обучения", "ДГ-2026-242",
         "31.02.2026", 2027, "Передано", _manager("morozova"), None, "Такой даты нет"],
        [_university("ssau"), "Солар", "Solar appScreener", "ДГ-2026-243",
         date(2026, 9, 1), "бессрочно", "Передано", _manager("morozova"), None,
         "Срок лицензии не разобрать"],
        [_university("psuti"), "Ростелеком", "Платформа онлайн-обучения", "ДГ-2026-244",
         date(2026, 9, 1), 2027, "Отгружено", _manager("lebedev"), None,
         "Такого статуса передачи нет"],
        [_university("psuti"), "Ростелеком", "Симулятор сетевой инфраструктуры",
         "ДГ-2026-245", date(2026, 9, 1), 2027, "В работе", "Сидоров Сидор Сидорович",
         None, "Менеджера нет среди сотрудников"],
        [_university("sibsutis"), "Ростелеком", "Симулятор сетевой инфраструктуры",
         "ДГ-2026-246", date(2026, 9, 1), 2027, "В работе", _manager("kozlova"),
         _contact("sibsutis"), None],
    ]  # fmt: skip
    return _titles(CATALOG_SPEC), _with_program(rows, {})


def universities() -> Sheet:
    """Справочник вузов: три знакомых (обновятся), три новых и пустая строка."""
    rows = [
        [_university("mtuci"), "МТУСИ", "Москва", "https://mtuci.ru", _manager("petrov")],
        [_university("ncfu"), "СКФУ", "Ставрополь", "https://www.ncfu.ru",
         _manager("egorova")],
        [_university("tusur"), "ТУСУР", "Томск", "https://tusur.ru", _manager("popova")],
        ["Северный (Арктический) федеральный университет имени М. В. Ломоносова", "САФУ",
         "Архангельск", "https://narfu.ru", _manager("lebedev")],
        ["Мордовский государственный университет им. Н. П. Огарёва", "МГУ им. Огарёва",
         "Саранск", "https://mrsu.ru", _manager("nikolaev")],
        ["Белгородский государственный технологический университет им. В. Г. Шухова",
         "БГТУ им. Шухова", "Белгород", "https://www.bstu.ru", None],
        [None, "ПГУ", "Пенза", None, None],
    ]  # fmt: skip
    return _titles(UNIVERSITY_SPEC), rows


def programs() -> Sheet:
    """Справочник программ: две знакомые, три новые и одно новое направление."""
    rows = [
        ["Python-разработчик", "Разработка", "Разработка на Python: веб-сервисы и автотесты"],
        ["Инженер DevOps", "DevOps", "Контейнеры, Kubernetes, CI/CD и наблюдаемость"],
        ["Мобильный разработчик", "Разработка", "Приложения для Android и iOS"],
        ["Инженер по надёжности (SRE)", "DevOps", "Надёжность, мониторинг и дежурства"],
        ["Системный аналитик", "Системный анализ", "Требования, моделирование и интеграции"],
    ]
    return _titles(PROGRAM_SPEC), rows


def products() -> Sheet:
    """Справочник продуктов: один знакомый и два новых, в том числе новый вендор."""
    rows = [
        ["Песочница DevOps", "Ростелеком", "Учебный контур: контейнеры, CI/CD, мониторинг"],
        ["ALD Pro", "Группа Астра", "Служба каталогов и управление доменом"],
        [
            "Kaspersky Security Center",
            "Лаборатория Касперского",
            "Управление защитой рабочих мест",
        ],
    ]
    return _titles(PRODUCT_SPEC), rows
