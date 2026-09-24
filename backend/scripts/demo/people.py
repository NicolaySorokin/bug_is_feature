"""Сотрудники ИТ Школы и контактные лица вузов.

Сотрудник - это и пользователь системы, и учётная запись в реалме Keycloak
(deploy/keycloak/realm-export.json). Идентификатор пользователя в Keycloak
не случайный, а выводится из логина: сид знает его заранее и привязывает
договоры к тому, кто войдёт через Keycloak. Совпадение с реалмом проверяет
tests/test_demo_data.py, а свежий список для реалма печатает
``python -m scripts.demo.people``.

Люди вымышленные, совпадения случайны. Почта - на зарезервированных
доменах example.com и *.example, телефоны - из несуществующего диапазона.
"""

from __future__ import annotations

import json
import random
import uuid
from dataclasses import dataclass

from app.enums import Role

# От этого пространства имён считаются id пользователей в Keycloak.
# Поменяете - придётся заново выгрузить пользователей в реалм.
KEYCLOAK_NAMESPACE = uuid.UUID("3d4a8f0e-6c1b-4b7e-9a52-1f0e8c2d7b64")

KAM = (Role.MANAGER,)
HEAD = (Role.MANAGER, Role.HEAD)
ADMIN = (Role.MANAGER, Role.HEAD, Role.ADMIN)


@dataclass(frozen=True, slots=True)
class Employee:
    username: str
    full_name: str  # Фамилия Имя Отчество
    roles: tuple[str, ...]

    @property
    def keycloak_id(self) -> str:
        return str(uuid.uuid5(KEYCLOAK_NAMESPACE, self.username))

    @property
    def last_name(self) -> str:
        return self.full_name.split()[0]

    @property
    def first_name(self) -> str:
        return self.full_name.split()[1]

    @property
    def email(self) -> str:
        return f"{self.username}@example.com"


# ТЗ: около 20 менеджеров по вузам (КАМ), их руководители и администратор.
EMPLOYEES: tuple[Employee, ...] = (
    Employee("petrov", "Петров Пётр Алексеевич", KAM),
    Employee("ivanova", "Иванова Мария Сергеевна", KAM),
    Employee("smirnov", "Смирнов Алексей Викторович", KAM),
    Employee("kuznetsova", "Кузнецова Елена Андреевна", KAM),
    Employee("sokolov", "Соколов Дмитрий Игоревич", KAM),
    Employee("popova", "Попова Наталья Валерьевна", KAM),
    Employee("lebedev", "Лебедев Игорь Николаевич", KAM),
    Employee("kozlova", "Козлова Анастасия Олеговна", KAM),
    Employee("novikov", "Новиков Сергей Павлович", KAM),
    Employee("morozova", "Морозова Татьяна Евгеньевна", KAM),
    Employee("volkov", "Волков Андрей Михайлович", KAM),
    Employee("alekseeva", "Алексеева Юлия Романовна", KAM),
    Employee("semenov", "Семёнов Максим Ильич", KAM),
    Employee("egorova", "Егорова Дарья Константиновна", KAM),
    Employee("pavlov", "Павлов Кирилл Андреевич", KAM),
    Employee("stepanova", "Степанова Ирина Владимировна", KAM),
    Employee("nikolaev", "Николаев Роман Сергеевич", KAM),
    Employee("zakharova", "Захарова Светлана Юрьевна", KAM),
    Employee("zaitsev", "Зайцев Артём Денисович", KAM),
    Employee("belova", "Белова Ксения Александровна", KAM),
    Employee("orlova", "Орлова Ольга Дмитриевна", HEAD),
    Employee("fedorov", "Фёдоров Виктор Геннадьевич", HEAD),
    Employee("admin", "Григорьев Олег Вадимович", ADMIN),
)

EMPLOYEE_BY_USERNAME = {employee.username: employee for employee in EMPLOYEES}


def realm_users() -> list[dict]:
    """Пользователи в формате realm-export.json. Пароль совпадает с логином."""
    return [
        {
            "id": employee.keycloak_id,
            "username": employee.username,
            "email": employee.email,
            "firstName": employee.first_name,
            "lastName": employee.last_name,
            "enabled": True,
            "emailVerified": True,
            "credentials": [
                {"type": "password", "value": employee.username, "temporary": False}
            ],
            "realmRoles": [str(role) for role in employee.roles],
        }
        for employee in EMPLOYEES
    ]


# --- Контактные лица вузов -----------------------------------------------------


@dataclass(frozen=True, slots=True)
class ContactInfo:
    full_name: str
    position: str
    email: str
    phone: str


# Фамилии в мужской и женской форме. Фамилий сотрудников ИТ Школы здесь нет,
# чтобы в карточке договора не путать своих с представителями вуза.
_SURNAMES = (
    ("Гусев", "Гусева"),
    ("Тарасов", "Тарасова"),
    ("Ковалёв", "Ковалёва"),
    ("Жуков", "Жукова"),
    ("Комаров", "Комарова"),
    ("Карпов", "Карпова"),
    ("Афанасьев", "Афанасьева"),
    ("Власов", "Власова"),
    ("Мельников", "Мельникова"),
    ("Денисов", "Денисова"),
    ("Гаврилов", "Гаврилова"),
    ("Тихонов", "Тихонова"),
    ("Фролов", "Фролова"),
    ("Журавлёв", "Журавлёва"),
    ("Соловьёв", "Соловьёва"),
    ("Борисов", "Борисова"),
    ("Киселёв", "Киселёва"),
    ("Филиппов", "Филиппова"),
    ("Марков", "Маркова"),
    ("Громов", "Громова"),
    ("Максимов", "Максимова"),
    ("Ильин", "Ильина"),
    ("Головин", "Головина"),
    ("Шубин", "Шубина"),
    ("Калинин", "Калинина"),
    ("Кудрявцев", "Кудрявцева"),
    ("Баранов", "Баранова"),
    ("Ершов", "Ершова"),
    ("Никитин", "Никитина"),
    ("Вишневский", "Вишневская"),
    ("Ефимов", "Ефимова"),
    ("Воробьёв", "Воробьёва"),
    ("Орехов", "Орехова"),
    ("Зырянов", "Зырянова"),
    ("Гафуров", "Гафурова"),
    ("Сафин", "Сафина"),
)

_MALE_NAMES = (
    "Александр", "Дмитрий", "Сергей", "Андрей", "Михаил", "Игорь", "Владимир",
    "Николай", "Евгений", "Олег", "Павел", "Константин", "Юрий", "Виталий",
    "Григорий", "Вадим", "Леонид", "Борис", "Ильдар", "Тимур",
)  # fmt: skip

_FEMALE_NAMES = (
    "Елена", "Ольга", "Татьяна", "Наталья", "Ирина", "Светлана", "Анна",
    "Марина", "Юлия", "Людмила", "Екатерина", "Галина", "Надежда", "Вера",
    "Лариса", "Оксана", "Валентина", "Алла", "Жанна", "Инна",
)  # fmt: skip

_PATRONYMICS = (
    ("Александрович", "Александровна"),
    ("Сергеевич", "Сергеевна"),
    ("Викторович", "Викторовна"),
    ("Николаевич", "Николаевна"),
    ("Иванович", "Ивановна"),
    ("Петрович", "Петровна"),
    ("Владимирович", "Владимировна"),
    ("Михайлович", "Михайловна"),
    ("Анатольевич", "Анатольевна"),
    ("Геннадьевич", "Геннадьевна"),
    ("Юрьевич", "Юрьевна"),
    ("Борисович", "Борисовна"),
    ("Олегович", "Олеговна"),
    ("Васильевич", "Васильевна"),
    ("Рашидович", "Рашидовна"),
)

# Кто обычно ведёт сотрудничество со стороны вуза: первый - основной контакт.
# Вторая строка - форма для женщины, если должность её требует.
_POSITIONS = (
    (("Проректор по учебной работе",), ("Проректор по цифровой трансформации",)),
    (
        ("Директор института информационных технологий",),
        ("Заведующий кафедрой информатики", "Заведующая кафедрой информатики"),
        ("Декан факультета информационных технологий",),
    ),
    (
        ("Начальник учебно-методического управления",),
        ("Руководитель центра карьеры",),
        ("Ведущий специалист отдела договорной работы",),
    ),
)

_TRANSLIT = str.maketrans(
    {
        "а": "a", "б": "b", "в": "v", "г": "g", "д": "d", "е": "e", "ё": "e",
        "ж": "zh", "з": "z", "и": "i", "й": "y", "к": "k", "л": "l", "м": "m",
        "н": "n", "о": "o", "п": "p", "р": "r", "с": "s", "т": "t", "у": "u",
        "ф": "f", "х": "kh", "ц": "ts", "ч": "ch", "ш": "sh", "щ": "shch",
        "ъ": "", "ы": "y", "ь": "", "э": "e", "ю": "yu", "я": "ya",
    }
)  # fmt: skip


def translit(text: str) -> str:
    return text.lower().translate(_TRANSLIT)


def university_contacts(key: str, count: int) -> list[ContactInfo]:
    """Контакты вуза. Одинаковы при каждом запуске: генератор зависит от кода вуза."""
    rng = random.Random(f"contacts:{key}")
    surnames = rng.sample(_SURNAMES, count)
    contacts: list[ContactInfo] = []
    for index, (male_surname, female_surname) in enumerate(surnames):
        female = rng.random() < 0.5
        surname = female_surname if female else male_surname
        name = rng.choice(_FEMALE_NAMES if female else _MALE_NAMES)
        patronymic = rng.choice(_PATRONYMICS)[1 if female else 0]

        variants = _POSITIONS[min(index, len(_POSITIONS) - 1)]
        forms = rng.choice(variants)
        position = forms[1] if female and len(forms) > 1 else forms[0]

        login = f"{translit(surname)}.{translit(name[0])}{translit(patronymic[0])}"
        contacts.append(
            ContactInfo(
                full_name=f"{surname} {name} {patronymic}",
                position=position,
                email=f"{login}@{key}.example",
                phone=f"+7 (900) 000-{rng.randint(10, 99)}-{rng.randint(10, 99)}",
            )
        )
    return contacts


if __name__ == "__main__":
    # Раздел users для deploy/keycloak/realm-export.json.
    print(json.dumps(realm_users(), ensure_ascii=False, indent=2))
