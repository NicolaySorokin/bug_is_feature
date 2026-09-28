"""Таблицы каталогов для демонстрационных загрузок из Excel.

Заголовки берутся из описания загрузок в app/services/imports.py, поэтому
не разойдутся с тем, что ждёт система.
"""

from __future__ import annotations

from datetime import date

from app.services.imports import CATALOG_SPEC, UNIVERSITY_SPEC
from scripts.demo.catalog import CONTACTS_PER_UNIVERSITY, UNIVERSITY_BY_KEY
from scripts.demo.people import EMPLOYEE_BY_USERNAME, university_contacts

Sheet = tuple[list[str], list[list[object]]]


def _university(key: str) -> str:
    return UNIVERSITY_BY_KEY[key].name


def _manager(username: str) -> str:
    return EMPLOYEE_BY_USERNAME[username].full_name


def _contact(key: str, index: int = 0) -> str:
    return university_contacts(key, CONTACTS_PER_UNIVERSITY)[index].full_name


def _titles(spec) -> list[str]:  # noqa: ANN001 (ImportSpec)
    return [field.title for field in spec.fields]


def _with_program(rows: list[list[object]], programs: dict[str, str]) -> list[list[object]]:
    """Колонка «ИТ-программа» после продукта: там, где программа не следует
    из справочника однозначно.
    """
    return [[*row[:3], programs.get(str(row[3])), *row[3:]] for row in rows]


def catalog() -> Sheet:
    """Сводный каталог: десять колонок из требования 1 ТЗ и «ИТ-программа».

    Часть строк обновляет договоры из демоданных, часть заводит новые,
    три вуза придут «на проверку».
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
        # Вузов из этих строк в системе ещё нет, импорт их заведёт.
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
    # Без колонки программы строка с продуктом из нескольких программ была бы
    # отклонена. У первых четырёх строк продукт уже во взаимодействии.
    programs = {
        "ДГ-2026-201": "Анализ защищённости приложений",
        "ДГ-2026-202": "Администратор баз данных PostgreSQL",
        "ДГ-2026-203": "Администратор Linux",
        "ДГ-2026-204": "Анализ защищённости приложений",
        "ДГ-2026-205": "Python-разработчик",
        "ДГ-2026-206": "Инженер DevOps",
        "ДГ-2026-208": "Администратор Linux",
        "ДГ-2026-209": "Java-разработчик",
        "ДГ-2026-211": "Специалист по защите информации",
        "ДГ-2026-212": "Python-разработчик",
        "ДГ-2026-213": "Администратор Linux",
        "ДГ-2026-214": "Сетевой инженер",
    }
    return _titles(CATALOG_SPEC), _with_program(rows, programs)


def catalog_errors() -> Sheet:
    """Каталог с ошибками для проверки перед импортом.

    Строки 2 и 9 правильные, в остальных ошибки. В строке 8 неизвестный
    менеджер: это предупреждение, взаимодействие загрузится без ответственного.
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
    programs = {
        "ДГ-2026-240": "Инженер по тестированию",
        "ДГ-2026-242": "Python-разработчик",
        "ДГ-2026-243": "Анализ защищённости приложений",
        "ДГ-2026-244": "Аналитик данных",
        "ДГ-2026-245": "Сетевой инженер",
        "ДГ-2026-246": "Инженер сетей связи",
    }
    return _titles(CATALOG_SPEC), _with_program(rows, programs)


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
    # ИНН пустой: в выгрузках его часто нет, и вуз узнаётся по названию.
    return _titles(UNIVERSITY_SPEC), [[row[0], None, *row[1:]] for row in rows]
