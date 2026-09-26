"""Какие взаимодействия заводить: сюжеты для показа и генератор остальных.

Взаимодействие с вузом - центральная сущность: у него свой ответственный,
состав программ и продуктов и ход по процессу. Договор появляется только
на этапе обмена документами (``Взаимодействие 0 -> 1 Договор``), поэтому
у ранних взаимодействий его нет.

Сюжетные взаимодействия собраны вручную так, чтобы на главной была
тревога каждого вида из раздела 7 концепции и понятная история за ней.
У Петрова (``petrov``) - основного героя показа - есть почти всё: договор,
который пора продлевать, застрявшая встреча, заблокированный процесс,
пропущенный этап и договор без документов. Есть и закрытые без успеха:
отказ вуза и досрочная отмена - с причиной.

Остальные взаимодействия генерируются «здоровыми»: сроки с запасом, этап
в пределах нормы, документы на месте. Они дают объём для реестра, отчётов
и диаграмм и не засоряют список проблем.

План описывает только суть: этапы, сроки, статусы. Даты истории,
комментарии и файлы достраивает загрузчик.
"""

from __future__ import annotations

import random
from dataclasses import dataclass

from app.enums import (
    ClosureReason,
    ContractStatus,
    InteractionSource,
    ProgramImplementationStatus,
)
from scripts.demo.catalog import PROGRAM_BY_NAME, UNIVERSITIES, UniversityInfo
from scripts.demo.processes import MAIN, SHORT


@dataclass(frozen=True, slots=True)
class Move:
    """Шаг истории процесса, если обычного кода этапа мало."""

    stage: str
    skip: bool = False  # пропуск текущего необязательного этапа
    comment: str | None = None


Route = tuple[str | Move, ...]


# С какого этапа у взаимодействия появляется договор (черновик).
CONTRACT_FROM = "documents"


@dataclass(frozen=True, slots=True)
class InteractionPlan:
    university: str  # код вуза из catalog
    manager: str | None  # логин ответственного
    programs: tuple[str, ...]
    products: tuple[str, ...]
    number: str | None = None  # номер договора; None - выдаст загрузчик по дате
    title: str | None = None
    template: str | None = MAIN.key  # None - черновик: процесс не запущен
    route: Route = ()  # этапы после стартового, по порядку
    days_on_stage: int = 3  # сколько дней назад был последний переход
    blocked: str | None = None  # причина блокировки
    # Закрытие без успеха: причина для отказа (финальный этап) или отмены.
    closure: ClosureReason | None = None
    cancelled: str | None = None  # взаимодействие отменено досрочно - комментарий
    contract_status: ContractStatus | None = None  # иначе выводится из этапа
    valid_days_left: int | None = None  # иначе - с запасом от даты подписания
    license_days_left: int | None = None  # иначе - до конца договора
    licenses: bool = True
    implementation: ProgramImplementationStatus | None = None  # иначе - по этапам
    unlinked: tuple[str, ...] = ()  # продукты без связи с программой - на исправление
    documents: bool = True
    notes: tuple[str, ...] = ()
    request: str | None = None  # заявка вуза с сайта, из которой появилось взаимодействие
    light: bool = False  # взаимодействие для нагрузки: без файлов и заметок

    @property
    def source(self) -> InteractionSource:
        return InteractionSource.SITE if self.request else InteractionSource.MANUAL

    @property
    def stages(self) -> list[str]:
        return [step.stage if isinstance(step, Move) else step for step in self.route]

    @property
    def has_contract(self) -> bool:
        """Договор есть, если дошли до обмена документами или его статус задан явно."""
        return self.contract_status is not None or CONTRACT_FROM in self.stages

    @property
    def label(self) -> str:
        return self.number or self.title or self.university


# Прежнее имя: план сюжета раньше описывал договор.
ContractPlan = InteractionPlan


# Полный проход основного шаблона без правок и возвратов.
FULL_MAIN: Route = (
    "programs",
    "meeting",
    "documents",
    "signing",
    "handover",
    "rollout",
    "training",
    "curriculum",
    "classes",
    "docs_update",
    "upskilling",
    "control",
)


def _until(stage: str) -> Route:
    return FULL_MAIN[: FULL_MAIN.index(stage) + 1]


STORIES: tuple[InteractionPlan, ...] = (
    # --- Петров: главный герой показа -------------------------------------------
    InteractionPlan(
        number="ДГ-2025-017",
        title="Основной договор о сотрудничестве",
        university="mtuci",
        manager="petrov",
        programs=("Python-разработчик", "Инженер по тестированию", "Сетевой инженер"),
        products=("Платформа онлайн-обучения",),
        route=FULL_MAIN,
        days_on_stage=250,  # цикл закрыт давно: договор заведён летом прошлого года
        valid_days_left=38,  # договор и лицензия скоро закончатся
        license_days_left=38,
        notes=("Вуз хочет продлить сотрудничество на следующий учебный год",),
    ),
    InteractionPlan(
        number="ДГ-2026-014",
        title="Расширение: аналитика и инженерия данных",
        university="mtuci",
        manager="petrov",
        programs=("Аналитик данных", "Инженер данных"),
        products=("Postgres Pro Enterprise",),
        route=_until("meeting"),
        days_on_stage=21,  # встреча не назначена три недели при норме 14 дней
        notes=("Проректор в отпуске, встречу обещали назначить после его возвращения",),
    ),
    InteractionPlan(
        number="ДГ-2026-047",
        title="Подготовка инженеров по тестированию",
        university="sut",
        manager="petrov",
        programs=("Инженер по тестированию", "Автоматизация тестирования"),
        products=("Платформа онлайн-обучения", "Песочница DevOps"),
        # Правки, подписание, ещё один круг правок - и дальше по плану.
        route=(
            "programs",
            "meeting",
            "documents",
            "corrections",
            "signing",
            "corrections",
            "signing",
            "handover",
            "rollout",
        ),
        days_on_stage=9,
        notes=("Вуз попросил добавить второй поток по автоматизации тестирования",),
    ),
    InteractionPlan(
        number="ДС-2026-011",
        title="Дополнительное соглашение: DevOps для магистратуры",
        university="sut",
        manager="petrov",
        programs=("Инженер DevOps",),
        products=("Песочница DevOps",),
        template=SHORT.key,
        route=("meeting", "documents", "approval"),
        days_on_stage=5,
    ),
    InteractionPlan(
        number="ДГ-2026-062",
        title="Кибербезопасность для бакалавриата",
        university="mirea",
        manager="petrov",
        programs=("Специалист по защите информации", "Анализ защищённости приложений"),
        products=("Стенд киберполигона", "Solar appScreener"),
        route=_until("training"),
        days_on_stage=16,
        blocked=(
            "Кафедра не может выделить преподавателей до окончания сессии, "
            "ждём приказ о нагрузке"
        ),
    ),
    InteractionPlan(
        number="ДГ-2026-071",
        title="Инженер DevOps: пилотный поток",
        university="mirea",
        manager="petrov",
        programs=("Инженер DevOps",),
        products=("Песочница DevOps", "Astra Linux Special Edition"),
        # Этап правок открыли, но вуз снял замечания - этап пропущен.
        route=("programs", "meeting", "documents", "corrections", Move("signing", skip=True)),
        days_on_stage=4,
    ),
    InteractionPlan(
        number="ДГ-2025-005",
        title="Сетевые технологии: учебная лаборатория",
        university="sut",
        manager="petrov",
        programs=("Сетевой инженер", "Инженер сетей связи"),
        products=("Симулятор сетевой инфраструктуры",),
        route=FULL_MAIN,
        days_on_stage=210,
        valid_days_left=300,
        documents=False,  # действующий договор без единого документа
        notes=("Договор перенесён из таблицы учёта, сканы в систему не загружены",),
    ),
    # --- Остальные тревоги - у других менеджеров --------------------------------
    InteractionPlan(
        number="ДГ-2026-003",
        title="DevOps и облачная инфраструктура",
        university="kai",
        manager="ivanova",
        programs=("Инженер DevOps", "Инженер облачной инфраструктуры"),
        products=("Песочница DevOps", "RuBackup"),
        route=_until("documents"),
        days_on_stage=34,  # втрое дольше нормы - критично
        notes=("Юристы вуза не отвечают, напомнили письмом",),
    ),
    InteractionPlan(
        number="ДГ-2026-058",
        title="Аналитика данных для инженерных специальностей",
        university="nstu",
        manager="ivanova",
        programs=("Аналитик данных", "Python-разработчик"),
        products=("Платформа онлайн-обучения", "Postgres Pro Enterprise"),
        route=_until("rollout"),
        days_on_stage=12,
    ),
    # Пример из концепции: два взаимодействия одного вуза с разным составом программ.
    InteractionPlan(
        number="ДГ-2026-012",
        title="Сотрудничество по четырём программам",
        university="urfu",
        manager="orlova",
        programs=(
            "Специалист по защите информации",
            "Python-разработчик",
            "Аналитик данных",
            "Инженер машинного обучения",
        ),
        products=("Стенд киберполигона",),
        route=_until("classes"),
        days_on_stage=30,
        license_days_left=-5,  # лицензия уже истекла
    ),
    InteractionPlan(
        number="ДГ-2026-029",
        title="Расширение сотрудничества: ещё три программы",
        university="urfu",
        manager="orlova",
        programs=("Java-разработчик", "Инженер данных", "Анализ защищённости приложений"),
        products=("Solar appScreener", "Postgres Pro Enterprise"),
        route=_until("signing"),
        days_on_stage=6,
        # Продукт добавили по письму вуза, а к программе не привязали - тревога
        # «продукт без программы» подсказывает, что данные нужно поправить.
        unlinked=("Postgres Pro Enterprise",),
        notes=("Postgres Pro вуз попросил письмом - уточняем, для какой программы",),
    ),
    InteractionPlan(
        number="ДГ-2026-040",
        title="Пилот по инженерии данных",
        university="ncfu",
        manager=None,  # ответственный не назначен
        programs=("Инженер данных",),
        products=("Postgres Pro Enterprise",),
        days_on_stage=2,
    ),
    InteractionPlan(
        number="ДГ-2026-077",
        title="Java-разработчик для магистратуры",
        university="sfedu",
        manager="orlova",
        programs=("Java-разработчик",),
        products=(),
        template=None,  # взаимодействие-черновик: процесс ещё не запущен
        notes=("Вуз позвонил сам, процесс запустим после первой встречи",),
    ),
    InteractionPlan(
        number="ДС-2026-005",
        title="Дополнительное соглашение: сетевые технологии",
        university="dvfu",
        manager="alekseeva",
        programs=("Сетевой инженер",),
        products=("Симулятор сетевой инфраструктуры",),
        template=SHORT.key,
        route=("meeting", "documents", "approval", "signing"),
        days_on_stage=25,
        implementation=ProgramImplementationStatus.NOT_STARTED,  # подписали, но не начали
    ),
    InteractionPlan(
        number="ДГ-2026-033",
        title="Разработка на Java для бакалавриата",
        university="tusur",
        manager="popova",
        programs=("Java-разработчик",),
        products=("Платформа онлайн-обучения",),
        route=_until("classes"),
        days_on_stage=50,
        blocked="Набор на программу не состоялся, занятия перенесены на весенний семестр",
        contract_status=ContractStatus.SUSPENDED,
        implementation=ProgramImplementationStatus.SUSPENDED,
    ),
    InteractionPlan(
        number="ДГ-2024-008",
        title="Пилотная программа по тестированию",
        university="psuti",
        manager="lebedev",
        programs=("Инженер по тестированию",),
        products=("Платформа онлайн-обучения",),
        route=FULL_MAIN,
        days_on_stage=470,
        contract_status=ContractStatus.CLOSED,  # сотрудничество завершено
        valid_days_left=-60,
        licenses=False,
    ),
    InteractionPlan(
        number="ДГ-2025-031",
        title="Сетевые технологии и связь",
        university="sibsutis",
        manager="kozlova",
        programs=("Сетевой инженер", "Инженер сетей связи"),
        products=("Симулятор сетевой инфраструктуры",),
        route=FULL_MAIN,
        days_on_stage=120,
        valid_days_left=-12,  # срок вышел, а договор всё ещё числится действующим
        license_days_left=-12,
    ),
    InteractionPlan(
        number="ДГ-2026-052",
        title="Администрирование Linux и СУБД",
        university="istu",
        manager="zaitsev",
        programs=("Администратор Linux", "Администратор баз данных PostgreSQL"),
        products=("Astra Linux Special Edition", "Postgres Pro Enterprise"),
        route=_until("signing"),
        days_on_stage=29,
    ),
    # Заявки с сайта, разобранные прошлыми синхронизациями.
    InteractionPlan(
        title="Заявка вуза с сайта ИТ Школы",
        university="unn",
        manager="novikov",
        programs=("Python-разработчик", "Аналитик данных"),
        products=(),
        route=("programs",),
        days_on_stage=3,
        request="req-2026-014",
    ),
    InteractionPlan(
        title="Заявка вуза с сайта ИТ Школы",
        university="ssau",
        manager="morozova",
        programs=("Инженер по тестированию",),
        products=(),
        route=("programs", "meeting"),
        days_on_stage=6,
        request="req-2026-019",
    ),
    # --- Закрытые без успеха: результат хранится отдельно от статуса -----------
    InteractionPlan(
        title="Кибербезопасность для магистратуры",
        university="vsu",
        manager="stepanova",
        programs=("Специалист по защите информации",),
        products=("Стенд киберполигона",),
        route=(
            "programs",
            "meeting",
            "documents",
            Move(
                "refusal",
                comment="Вуз выбрал программу другого партнёра, к вопросу вернутся через год",
            ),
        ),
        closure=ClosureReason.UNIVERSITY_REFUSED,
        days_on_stage=40,
    ),
    InteractionPlan(
        title="Сетевые технологии для колледжа при вузе",
        university="mpei",
        manager="sokolov",
        programs=("Сетевой инженер",),
        products=("Симулятор сетевой инфраструктуры",),
        route=("programs",),
        days_on_stage=18,
        closure=ClosureReason.LOST_RELEVANCE,
        cancelled="Колледж вошёл в состав вуза, программу обсуждаем в основном взаимодействии",
    ),
)


# --- Генератор ----------------------------------------------------------------

# Докуда дошёл процесс: вес этапа основного шаблона. Больше всего взаимодействий
# в работе после подписания, у заметной части цикл уже закрыт.
_MAIN_TARGETS = {
    "contacts": 4,
    "programs": 5,
    "meeting": 6,
    "documents": 6,
    "corrections": 3,
    "signing": 6,
    "handover": 5,
    "rollout": 8,
    "training": 6,
    "curriculum": 6,
    "classes": 14,
    "docs_update": 4,
    "upskilling": 4,
    "control": 12,
}
_SHORT_TARGETS = {"meeting": 1, "documents": 2, "approval": 2, "revision": 1, "signing": 4}

_MAIN_ORDER = (
    "contacts",
    "programs",
    "meeting",
    "documents",
    "corrections",
    "signing",
    "handover",
    "rollout",
    "training",
    "curriculum",
    "classes",
    "docs_update",
    "upskilling",
    "control",
)


def _main_route(target: str, rng: random.Random) -> list[str | Move]:
    """Путь до целевого этапа: иногда с правками, возвратами и пропусками."""
    goal = _MAIN_ORDER.index(target)
    with_corrections = target == "corrections" or rng.random() < 0.4
    route: list[str | Move] = []

    for index, code in enumerate(_MAIN_ORDER[1 : goal + 1], start=1):
        if code == "corrections" and not with_corrections:
            continue
        if code == "signing" and route and route[-1] == "corrections" and rng.random() < 0.3:
            route.append(Move("signing", skip=True))  # вуз снял замечания
            continue
        if code == "control" and route and route[-1] == "upskilling" and rng.random() < 0.3:
            # Пропуск возможен, только если в версии шаблона этап необязательный -
            # иначе загрузчик проведёт обычный переход.
            route.append(Move("control", skip=True))
            continue

        route.append(code)
        beyond = index < goal
        if code == "meeting" and beyond and rng.random() < 0.1:
            route += ["programs", "meeting"]  # встречу переносили
        if code == "signing" and beyond and with_corrections and rng.random() < 0.2:
            route += ["corrections", "signing"]  # ещё один круг правок
        if code == "rollout" and beyond and rng.random() < 0.1:
            route += ["handover", "rollout"]  # понадобились ещё лицензии
        if code == "classes" and beyond and rng.random() < 0.1:
            route += ["curriculum", "classes"]  # программу доработали на ходу
    return route


def _short_route(target: str, rng: random.Random) -> list[str | Move]:
    route: list[str | Move] = []
    for code in ("meeting", "documents", "approval"):
        route.append(code)
        if code == target:
            return route
    if target == "revision":
        return [*route, "revision"]
    if rng.random() < 0.3:
        route += ["revision", "approval"]  # круг доработки перед подписанием
    return [*route, "signing"]


def _programs_for(university: UniversityInfo, rng: random.Random) -> tuple[str, ...]:
    suitable = [
        p.name for p in PROGRAM_BY_NAME.values() if p.direction in university.directions
    ]
    count = min(len(suitable), rng.choices((1, 2, 3), weights=(45, 40, 15))[0])
    return tuple(rng.sample(suitable, count))


def _products_for(programs: tuple[str, ...], rng: random.Random) -> tuple[str, ...]:
    pool = sorted({product for name in programs for product in PROGRAM_BY_NAME[name].products})
    return tuple(rng.sample(pool, min(len(pool), rng.choice((1, 1, 2)))))


def _title(programs: tuple[str, ...], template: str) -> str:
    if template == SHORT.key:
        return f"Дополнительное соглашение: {programs[0]}"
    if len(programs) == 1:
        return f"Программа «{programs[0]}»"
    directions = sorted({PROGRAM_BY_NAME[name].direction for name in programs})
    if len(directions) == 1:
        return f"Подготовка кадров по направлению «{directions[0]}»"
    return f"Подготовка кадров: {', '.join(directions)}"


def _days_on_stage(template: str, target: str, rng: random.Random) -> int:
    """Сколько взаимодействие стоит на этапе - всегда в пределах нормы."""
    spec = MAIN if template == MAIN.key else SHORT
    final = next(stage for stage in spec.latest.stages if stage.successful_final)
    if target == final.code:
        return rng.randint(7, 420)  # цикл закрыт давно или недавно
    sla = spec.min_sla(target) or 14
    return rng.randint(0, max(1, int(sla * 0.8)))


def generate(count: int, rng: random.Random, *, light: bool = False) -> list[InteractionPlan]:
    """Здоровые взаимодействия: у каждого вуза с менеджером хотя бы одно."""
    universities = [university for university in UNIVERSITIES if university.manager]
    picks = list(universities) if count >= len(universities) else []
    picks += rng.choices(universities, k=count - len(picks))

    plans: list[InteractionPlan] = []
    for university in picks:
        template = SHORT.key if rng.random() < 0.1 else MAIN.key
        targets = _MAIN_TARGETS if template == MAIN.key else _SHORT_TARGETS
        target = rng.choices(list(targets), weights=list(targets.values()))[0]
        route = _main_route(target, rng) if template == MAIN.key else _short_route(target, rng)
        programs = _programs_for(university, rng)
        plans.append(
            InteractionPlan(
                university=university.key,
                manager=university.manager,
                programs=programs,
                products=_products_for(programs, rng),
                title=_title(programs, template),
                template=template,
                route=tuple(route),
                days_on_stage=_days_on_stage(template, target, rng),
                light=light,
            )
        )
    return plans
