"""Каталог вендоров в формате кейсодержателя.

В ячейке «Продукт» бывает несколько продуктов через запятую. Контакты
вымышленные. Грузится тем же импортом, что и файл из интерфейса.
"""

from __future__ import annotations

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.catalog import VendorContact
from app.services import imports

HEADERS = ["Компания", "Продукт", "ФИО", "Телефон", "Почта", "Способ связи"]

ROWS: list[list[object]] = [
    ["ООО «Базис»", "«Базис Dynamix»", "Иванов Иван Иванович", "+7 (900) 111-22-33",
     "ivanov.ii@example.ru", "Почта, Чат в ТГ"],
    ["ООО «ТДата»", "«RT.DataLake», «RT.Warehouse»", "Смирнова Анна Петровна",
     "+7 (911) 222-33-44", "smirnova.ap@example.ru", "Чат в ТГ"],
    ["ПАО «Ростелеком»", "«RT.DataVision»", "Кузнецов Дмитрий Сергеевич",
     "+7 (922) 333-44-55", "kuznetsov.ds@example.ru", "Чат в ТГ"],
    ["ООО «РТК ИТ Плюс»", "«AKOLA»", "Попова Мария Владимировна", "+7 (933) 444-55-66",
     "popova.mv@example.ru", "Чат в ТГ"],
    ["ООО «РТК ИТ Плюс»", "«Яга»", "Соколов Алексей Андреевич", "+7 (944) 555-66-77",
     "sokolov.aa@example.ru", "Чат в ТГ"],
    ["ООО «РТК ИТ»", "«Web3Gate»", "Лебедева Елена Дмитриевна", "+7 (955) 666-77-88",
     "lebedeva.ed@example.ru", "Чат в ТГ"],
    ["ООО «РТК ИТ»", "«Аврора SDK»", "Козлов Максим Игоревич", "+7 (966) 777-88-99",
     "kozlov.mi@example.ru", "Чат в ТГ"],
    ["ООО «РТК ИТ»", "«Нейрошлюз»", "Новикова Ольга Александровна", "+7 (977) 888-99-00",
     "novikova.oa@example.ru", "Почта"],
]  # fmt: skip


async def is_empty(session: AsyncSession) -> bool:
    return not await session.scalar(select(func.count()).select_from(VendorContact))


async def load(session: AsyncSession) -> imports.ImportOutcome:
    data = imports.SheetData(headers=HEADERS, rows=ROWS)
    mapping = imports.suggest_mapping(imports.VENDOR_SPEC, HEADERS)
    return await imports.run_import(session, imports.VENDOR_SPEC, data, mapping)
