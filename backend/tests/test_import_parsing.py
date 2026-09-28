"""Разбор значений при импорте, без базы данных.

Люди заполняют Excel по-разному, поэтому разбор не должен зависеть
от формы записи.
"""

from datetime import date

import pytest

from app.enums import ImportType, ProductTransferStatus
from app.services import imports


def test_dates_are_read_in_usual_formats() -> None:
    assert imports.parse_date("01.02.2026") == date(2026, 2, 1)
    assert imports.parse_date("2026-02-01") == date(2026, 2, 1)
    assert imports.parse_date(date(2026, 2, 1)) == date(2026, 2, 1)
    assert imports.parse_date(None) is None
    assert imports.parse_date("") is None


def test_unreadable_date_is_reported() -> None:
    with pytest.raises(ValueError, match="не похоже на дату"):
        imports.parse_date("как-нибудь потом")


def test_license_term_accepts_year_and_duration() -> None:
    signed = date(2026, 3, 10)
    # Год окончания.
    assert imports.parse_license_valid_to("2027", signed) == date(2027, 12, 31)
    # Срок в годах от даты подписания.
    assert imports.parse_license_valid_to("3 года", signed) == date(2029, 3, 10)
    # Полная дата.
    assert imports.parse_license_valid_to("31.12.2028", signed) == date(2028, 12, 31)
    assert imports.parse_license_valid_to(None, signed) is None


def test_transfer_status_understands_russian_wording() -> None:
    # У продукта свой статус: не «внедрён», а «передан».
    assert imports.parse_transfer_status("Передано") == ProductTransferStatus.TRANSFERRED
    assert imports.parse_transfer_status("в работе") == ProductTransferStatus.IN_PROGRESS
    assert imports.parse_transfer_status("Не начато") == ProductTransferStatus.NOT_STARTED
    assert imports.parse_transfer_status(None) is None

    with pytest.raises(ValueError, match="неизвестный статус"):
        imports.parse_transfer_status("почти готово")


def test_mapping_is_suggested_by_headers() -> None:
    spec = imports.SPECS[ImportType.CATALOG]
    mapping = imports.suggest_mapping(
        spec,
        ["название вуза", "Номер договора.", "ИТ-продукт", "Своя колонка"],
    )

    # Регистр, точки и лишние пробелы в заголовке значения не имеют.
    assert mapping["university_name"] == "название вуза"
    assert mapping["contract_number"] == "Номер договора."
    # «ИТ-продукт» известен как синоним колонки «ПО».
    assert mapping["product"] == "ИТ-продукт"
    assert mapping["comment"] is None


def test_mapping_requires_mandatory_columns() -> None:
    spec = imports.SPECS[ImportType.CATALOG]
    headers = ["Название ВУЗа"]

    with pytest.raises(Exception, match="Номер договора"):
        imports.check_mapping(spec, {"university_name": "Название ВУЗа"}, headers)


def test_header_row_is_found_after_empty_lines() -> None:
    sheet = imports._split(
        [
            [None, None],
            ["Название ВУЗа", "Номер договора"],
            ["МТУСИ", "ДГ-1"],
            [None, None],
        ]
    )
    assert sheet.headers == ["Название ВУЗа", "Номер договора"]
    assert sheet.rows == [["МТУСИ", "ДГ-1"]]


def test_numbers_do_not_turn_into_floats() -> None:
    # Excel отдаёт целые числа как 2026.0, а в ячейке должно остаться «2026».
    assert imports.cell_text(2026.0) == "2026"
    assert imports.cell_text(" МТУСИ ") == "МТУСИ"
    assert imports.cell_text(None) == ""
