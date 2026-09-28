"""Справочники демоданных: направления, программы, продукты, вузы.

Названия совпадают с тестовыми ответами LMS и сайта, поэтому синхронизация
обновляет эти записи, а не заводит дубли.
"""

from __future__ import annotations

from dataclasses import dataclass

# ИТ-направления

DEV = "Разработка"
QA = "QA"
DEVOPS = "DevOps"
DATA = "Аналитика данных"
SEC = "Информационная безопасность"
NET = "Сети и телекоммуникации"
SYS = "Системное администрирование"
AI = "Искусственный интеллект"

DIRECTIONS: dict[str, str] = {
    DEV: "Программирование, проектирование и сопровождение программ",
    QA: "Ручное и автоматизированное тестирование программного обеспечения",
    DEVOPS: "Сборка, развёртывание и эксплуатация сервисов",
    DATA: "Сбор, обработка и визуализация данных",
    SEC: "Защита информации и анализ защищённости",
    NET: "Проектирование и эксплуатация сетей связи",
    SYS: "Администрирование операционных систем, баз данных и инфраструктуры",
    AI: "Машинное обучение и прикладной искусственный интеллект",
}


# Вендоры и ИТ-продукты

RT = "Ростелеком"

VENDORS: dict[str, str] = {
    RT: "Собственные учебные платформы и стенды ИТ Школы",
    "Солар": "Продукты кибербезопасности группы Ростелеком",
    "Группа Астра": "Операционная система и инфраструктурное ПО",
    "Postgres Professional": "Российская СУБД на основе PostgreSQL",
    "Positive Technologies": "Средства анализа защищённости и мониторинга",
    "РЕД СОФТ": "Операционная система и прикладное ПО",
}


@dataclass(frozen=True, slots=True)
class ProductInfo:
    name: str
    vendor: str
    description: str


PRODUCTS: tuple[ProductInfo, ...] = (
    ProductInfo(
        "Платформа онлайн-обучения", RT, "Занятия, проверка заданий и учёт успеваемости"
    ),
    ProductInfo("Симулятор сетевой инфраструктуры", RT, "Лабораторные работы по сетям связи"),
    ProductInfo("Песочница DevOps", RT, "Учебный контур с контейнерами, CI/CD и мониторингом"),
    ProductInfo("Стенд киберполигона", RT, "Отработка атак и защиты на модели инфраструктуры"),
    ProductInfo("Solar appScreener", "Солар", "Статический анализ исходного кода"),
    ProductInfo("Solar Dozor", "Солар", "Защита от утечек информации"),
    ProductInfo(
        "Astra Linux Special Edition", "Группа Астра", "Защищённая операционная система"
    ),
    ProductInfo("RuBackup", "Группа Астра", "Резервное копирование и восстановление"),
    ProductInfo("Postgres Pro Enterprise", "Postgres Professional", "Промышленная СУБД"),
    ProductInfo(
        "PT Application Inspector", "Positive Technologies", "Анализ защищённости приложений"
    ),
    ProductInfo(
        "MaxPatrol SIEM", "Positive Technologies", "Выявление инцидентов безопасности"
    ),
    ProductInfo("РЕД ОС", "РЕД СОФТ", "Операционная система для серверов и рабочих мест"),
)


# ИТ-программы


@dataclass(frozen=True, slots=True)
class ProgramInfo:
    name: str
    direction: str
    description: str
    products: tuple[str, ...]  # на каких продуктах строится обучение


PROGRAMS: tuple[ProgramInfo, ...] = (
    ProgramInfo(
        "Python-разработчик",
        DEV,
        "Основы разработки на Python и веб-сервисы",
        ("Платформа онлайн-обучения", "Solar appScreener"),
    ),
    ProgramInfo(
        "Java-разработчик",
        DEV,
        "Промышленная разработка на Java и Spring",
        ("Платформа онлайн-обучения", "Solar appScreener"),
    ),
    ProgramInfo(
        "Frontend-разработчик",
        DEV,
        "Интерфейсы на TypeScript и React",
        ("Платформа онлайн-обучения",),
    ),
    ProgramInfo(
        "Инженер по тестированию",
        QA,
        "Ручное тестирование и работа с требованиями",
        ("Платформа онлайн-обучения",),
    ),
    ProgramInfo(
        "Автоматизация тестирования",
        QA,
        "Автотесты API и интерфейсов, запуск в CI",
        ("Платформа онлайн-обучения", "Песочница DevOps"),
    ),
    ProgramInfo(
        "Инженер DevOps",
        DEVOPS,
        "Контейнеры, CI/CD и мониторинг",
        ("Песочница DevOps", "Astra Linux Special Edition"),
    ),
    ProgramInfo(
        "Инженер облачной инфраструктуры",
        DEVOPS,
        "Виртуализация, облака и резервное копирование",
        ("Песочница DevOps", "Astra Linux Special Edition", "RuBackup"),
    ),
    ProgramInfo(
        "Аналитик данных",
        DATA,
        "SQL, отчётность и визуализация",
        ("Платформа онлайн-обучения", "Postgres Pro Enterprise"),
    ),
    ProgramInfo(
        "Инженер данных",
        DATA,
        "Хранилища и конвейеры данных",
        ("Postgres Pro Enterprise",),
    ),
    ProgramInfo(
        "Специалист по защите информации",
        SEC,
        "Защита информационных систем и расследование инцидентов",
        ("Стенд киберполигона", "Solar Dozor", "MaxPatrol SIEM"),
    ),
    ProgramInfo(
        "Анализ защищённости приложений",
        SEC,
        "Поиск уязвимостей в коде и веб-приложениях",
        ("Solar appScreener", "PT Application Inspector", "Стенд киберполигона"),
    ),
    ProgramInfo(
        "Сетевой инженер",
        NET,
        "Маршрутизация, коммутация и сетевые сервисы",
        ("Симулятор сетевой инфраструктуры",),
    ),
    ProgramInfo(
        "Инженер сетей связи",
        NET,
        "Сети доступа и мобильная связь",
        ("Симулятор сетевой инфраструктуры",),
    ),
    ProgramInfo(
        "Администратор Linux",
        SYS,
        "Администрирование отечественных ОС",
        ("Astra Linux Special Edition", "РЕД ОС", "RuBackup"),
    ),
    ProgramInfo(
        "Администратор баз данных PostgreSQL",
        SYS,
        "Установка, настройка и сопровождение СУБД",
        ("Postgres Pro Enterprise",),
    ),
    ProgramInfo(
        "Инженер машинного обучения",
        AI,
        "Модели машинного обучения и их внедрение",
        ("Платформа онлайн-обучения",),
    ),
)

PROGRAM_BY_NAME = {program.name: program for program in PROGRAMS}


# Вузы


@dataclass(frozen=True, slots=True)
class UniversityInfo:
    key: str  # латинский код: домен почты контактов и ссылка из сюжетов
    name: str
    short_name: str
    city: str
    website: str
    manager: str | None  # логин закреплённого менеджера
    directions: tuple[str, ...]  # что вузу интересно, из этого собираются договоры


UNIVERSITIES: tuple[UniversityInfo, ...] = (
    UniversityInfo(
        "mtuci",
        "Московский технический университет связи и информатики",
        "МТУСИ",
        "Москва",
        "https://mtuci.ru",
        "petrov",
        (DEV, QA, NET, DATA),
    ),
    UniversityInfo(
        "sut",
        "Санкт-Петербургский государственный университет телекоммуникаций "
        "им. проф. М. А. Бонч-Бруевича",
        "СПбГУТ",
        "Санкт-Петербург",
        "https://www.sut.ru",
        "petrov",
        (QA, NET, DEVOPS),
    ),
    UniversityInfo(
        "mirea",
        "МИРЭА — Российский технологический университет",
        "РТУ МИРЭА",
        "Москва",
        "https://www.mirea.ru",
        "petrov",
        (SEC, DEVOPS),
    ),
    UniversityInfo(
        "kai",
        "Казанский национальный исследовательский технический университет "
        "им. А. Н. Туполева — КАИ",
        "КНИТУ-КАИ",
        "Казань",
        "https://kai.ru",
        "ivanova",
        (DEVOPS, DEV, SEC),
    ),
    UniversityInfo(
        "nstu",
        "Новосибирский государственный технический университет",
        "НГТУ",
        "Новосибирск",
        "https://www.nstu.ru",
        "ivanova",
        (DATA, DEV),
    ),
    UniversityInfo(
        "urfu",
        "Уральский федеральный университет имени первого Президента России Б. Н. Ельцина",
        "УрФУ",
        "Екатеринбург",
        "https://urfu.ru",
        "orlova",
        (SEC, DEV, DATA, AI),
    ),
    UniversityInfo(
        "sfedu",
        "Южный федеральный университет",
        "ЮФУ",
        "Ростов-на-Дону",
        "https://sfedu.ru",
        "orlova",
        (DEV, AI),
    ),
    UniversityInfo(
        "itmo",
        "Национальный исследовательский университет ИТМО",
        "ИТМО",
        "Санкт-Петербург",
        "https://itmo.ru",
        "smirnov",
        (AI, DEV, DEVOPS),
    ),
    UniversityInfo(
        "mipt",
        "Московский физико-технический институт (национальный исследовательский университет)",
        "МФТИ",
        "Долгопрудный",
        "https://mipt.ru",
        "kuznetsova",
        (AI, DATA),
    ),
    UniversityInfo(
        "mpei",
        "Национальный исследовательский университет «МЭИ»",
        "НИУ «МЭИ»",
        "Москва",
        "https://mpei.ru",
        "sokolov",
        (SYS, NET),
    ),
    UniversityInfo(
        "mai",
        "Московский авиационный институт (национальный исследовательский университет)",
        "МАИ",
        "Москва",
        "https://mai.ru",
        "sokolov",
        (DEV, SYS),
    ),
    UniversityInfo(
        "tusur",
        "Томский государственный университет систем управления и радиоэлектроники",
        "ТУСУР",
        "Томск",
        "https://tusur.ru",
        "popova",
        (DEV, SEC),
    ),
    UniversityInfo(
        "psuti",
        "Поволжский государственный университет телекоммуникаций и информатики",
        "ПГУТИ",
        "Самара",
        "https://www.psuti.ru",
        "lebedev",
        (QA, NET),
    ),
    UniversityInfo(
        "sibsutis",
        "Сибирский государственный университет телекоммуникаций и информатики",
        "СибГУТИ",
        "Новосибирск",
        "https://sibsutis.ru",
        "kozlova",
        (NET, SYS),
    ),
    UniversityInfo(
        "unn",
        "Нижегородский государственный университет им. Н. И. Лобачевского",
        "ННГУ",
        "Нижний Новгород",
        "https://www.unn.ru",
        "novikov",
        (DEV, DATA),
    ),
    UniversityInfo(
        "ssau",
        "Самарский национальный исследовательский университет имени академика С. П. Королёва",
        "Самарский университет",
        "Самара",
        "https://ssau.ru",
        "morozova",
        (DEV, QA),
    ),
    UniversityInfo(
        "pstu",
        "Пермский национальный исследовательский политехнический университет",
        "ПНИПУ",
        "Пермь",
        "https://pstu.ru",
        "volkov",
        (DEVOPS, SYS),
    ),
    UniversityInfo(
        "dvfu",
        "Дальневосточный федеральный университет",
        "ДВФУ",
        "Владивосток",
        "https://www.dvfu.ru",
        "alekseeva",
        (NET, DEV),
    ),
    UniversityInfo(
        "sfu",
        "Сибирский федеральный университет",
        "СФУ",
        "Красноярск",
        "https://www.sfu-kras.ru",
        "semenov",
        (DATA, SYS),
    ),
    UniversityInfo(
        "kpfu",
        "Казанский (Приволжский) федеральный университет",
        "КФУ",
        "Казань",
        "https://kpfu.ru",
        "egorova",
        (AI, DATA),
    ),
    UniversityInfo(
        "kantiana",
        "Балтийский федеральный университет имени Иммануила Канта",
        "БФУ им. И. Канта",
        "Калининград",
        "https://kantiana.ru",
        "pavlov",
        (DEV, QA),
    ),
    UniversityInfo(
        "vsu",
        "Воронежский государственный университет",
        "ВГУ",
        "Воронеж",
        "https://www.vsu.ru",
        "stepanova",
        (SEC, DEV),
    ),
    UniversityInfo(
        "uust",
        "Уфимский университет науки и технологий",
        "УУНиТ",
        "Уфа",
        "https://uust.ru",
        "nikolaev",
        (DEVOPS, SEC),
    ),
    UniversityInfo(
        "ncfu",
        "Северо-Кавказский федеральный университет",
        "СКФУ",
        "Ставрополь",
        "https://www.ncfu.ru",
        None,  # менеджер не закреплён, это повод для сигнала на главной
        (DATA, DEV),
    ),
    UniversityInfo(
        "utmn",
        "Тюменский государственный университет",
        "ТюмГУ",
        "Тюмень",
        "https://www.utmn.ru",
        "zakharova",
        (DEV, DATA),
    ),
    UniversityInfo(
        "omgtu",
        "Омский государственный технический университет",
        "ОмГТУ",
        "Омск",
        "https://omgtu.ru",
        "zakharova",
        (SEC, NET),
    ),
    UniversityInfo(
        "istu",
        "Иркутский национальный исследовательский технический университет",
        "ИРНИТУ",
        "Иркутск",
        "https://www.istu.edu",
        "zaitsev",
        (SYS, NET),
    ),
    UniversityInfo(
        "vlsu",
        "Владимирский государственный университет имени Александра Григорьевича "
        "и Николая Григорьевича Столетовых",
        "ВлГУ",
        "Владимир",
        "https://www.vlsu.ru",
        "belova",
        (QA, DEV),
    ),
    UniversityInfo(
        "uniyar",
        "Ярославский государственный университет им. П. Г. Демидова",
        "ЯрГУ",
        "Ярославль",
        "https://www.uniyar.ac.ru",
        "belova",
        (DATA, AI),
    ),
    UniversityInfo(
        "spbstu",
        "Санкт-Петербургский политехнический университет Петра Великого",
        "СПбПУ",
        "Санкт-Петербург",
        "https://www.spbstu.ru",
        "fedorov",
        (DEVOPS, AI, SEC),
    ),
)

UNIVERSITY_BY_KEY = {university.key: university for university in UNIVERSITIES}

# Сколько контактных лиц заводить у вуза: у крупных партнёров их больше.
CONTACTS_PER_UNIVERSITY = 3
