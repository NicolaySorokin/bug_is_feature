"""Шаблоны рабочих процессов и тексты, которыми обрастают этапы.

Основной шаблон повторяет базовый workflow из ТЗ - 14 шагов от поиска
контактов в вузе до контроля исполнения. У него две опубликованные версии:
договоры, начатые до выхода второй, идут по первой - так видно правило
раздела 3.1 концепции «правка шаблона не меняет запущенные процессы».

Короткий шаблон - маршрут из концепции (Контакт -> Встреча -> Документы ->
Согласование -> Подписание) для дополнительных соглашений, где внедрение
уже идёт по основному договору.

Расположение этапов на схеме не задаётся: клиент раскладывает их по
порядку сам, а руководитель может передвинуть этапы и сохранить схему.
"""

from __future__ import annotations

from dataclasses import dataclass, replace


@dataclass(frozen=True, slots=True)
class StageSpec:
    code: str
    name: str
    description: str
    sla_days: int | None
    optional: bool = False
    final: bool = False


@dataclass(frozen=True, slots=True)
class TransitionSpec:
    source: str
    target: str
    name: str
    backward: bool = False
    needs_comment: bool = False


@dataclass(frozen=True, slots=True)
class VersionSpec:
    number: int
    published_days_ago: int
    stages: tuple[StageSpec, ...]
    transitions: tuple[TransitionSpec, ...]


@dataclass(frozen=True, slots=True)
class TemplateSpec:
    key: str
    name: str
    description: str
    created_days_ago: int
    document: str  # как в текстах называется то, что подписывают
    versions: tuple[VersionSpec, ...]

    @property
    def latest(self) -> VersionSpec:
        return self.versions[-1]

    def min_sla(self, code: str) -> int | None:
        """Самая строгая норма этапа по всем версиям."""
        values = [
            stage.sla_days
            for version in self.versions
            for stage in version.stages
            if stage.code == code and stage.sla_days
        ]
        return min(values) if values else None


# --- Основной шаблон: 14 шагов ТЗ ---------------------------------------------

_MAIN_V1_STAGES = (
    StageSpec("contacts", "Поиск контактов", "Найти ответственного в вузе и его контакты", 7),
    StageSpec(
        "programs",
        "Уточнение программ",
        "Обсудить с ответственным актуальность программ по ИТ-направлениям",
        10,
    ),
    StageSpec("meeting", "Встреча с вузом", "Провести встречу с представителями вуза", 14),
    StageSpec(
        "documents",
        "Обмен документами",
        "Обменяться пакетом документов для подписания",
        10,
    ),
    StageSpec(
        "corrections",
        "Корректировка документов",
        "Внести правки вуза в документы перед подписанием",
        7,
        optional=True,
    ),
    StageSpec(
        "signing",
        "Подписание документов",
        "Подписать договор и сопутствующие документы",
        21,
    ),
    StageSpec(
        "handover",
        "Передача материалов и лицензий",
        "Передать вузу обучающие материалы, лицензии ИТ-продукта и его документацию",
        10,
    ),
    StageSpec("rollout", "Сопровождение внедрения", "Помочь вузу развернуть ИТ-продукты", 30),
    StageSpec(
        "training",
        "Обучение преподавателей",
        "Обучить преподавателей работе с программой и продуктом",
        21,
    ),
    StageSpec(
        "curriculum",
        "Актуализация учебной программы",
        "Обновить учебную программу с учётом обучения преподавателей и ИТ-продукта",
        30,
    ),
    StageSpec("classes", "Ведение занятий", "Занятия со студентами по программе", 150),
    StageSpec(
        "docs_update",
        "Актуализация документации",
        "Обновить документацию по продукту и обучающие материалы",
        14,
    ),
    StageSpec(
        "upskilling",
        "Повышение квалификации",
        "Повысить квалификацию преподавателей",
        30,
    ),
    StageSpec(
        "control",
        "Контроль исполнения",
        "Проверить исполнение всех этапов и закрыть цикл",
        None,
        final=True,
    ),
)

_MAIN_TRANSITIONS = (
    TransitionSpec("contacts", "programs", "Контакт найден"),
    TransitionSpec(
        "programs", "contacts", "Контакт не подтвердился", backward=True, needs_comment=True
    ),
    TransitionSpec("programs", "meeting", "Программы актуальны, назначаем встречу"),
    TransitionSpec(
        "meeting", "programs", "Встреча перенесена", backward=True, needs_comment=True
    ),
    TransitionSpec("meeting", "documents", "Встреча проведена"),
    TransitionSpec("documents", "corrections", "Вуз прислал правки"),
    TransitionSpec("documents", "signing", "Документы согласованы без правок"),
    TransitionSpec("corrections", "signing", "Правки внесены"),
    TransitionSpec(
        "signing", "corrections", "Нужны ещё правки", backward=True, needs_comment=True
    ),
    TransitionSpec("signing", "handover", "Документы подписаны"),
    TransitionSpec("handover", "rollout", "Материалы и лицензии переданы"),
    TransitionSpec(
        "rollout",
        "handover",
        "Нужны дополнительные материалы",
        backward=True,
        needs_comment=True,
    ),
    TransitionSpec("rollout", "training", "Продукт развёрнут"),
    TransitionSpec("training", "curriculum", "Преподаватели обучены"),
    TransitionSpec("curriculum", "classes", "Программа утверждена"),
    TransitionSpec(
        "classes",
        "curriculum",
        "Программа требует доработки",
        backward=True,
        needs_comment=True,
    ),
    TransitionSpec("classes", "docs_update", "Семестр завершён"),
    TransitionSpec("docs_update", "upskilling", "Документация обновлена"),
    TransitionSpec("upskilling", "control", "Квалификация повышена"),
)


def _v2_stage(stage: StageSpec) -> StageSpec:
    """Вторая версия: по итогам первого года повышение квалификации стало
    необязательным, на обновление документации дали больше времени,
    финальный этап переименовали."""
    if stage.code == "upskilling":
        return replace(stage, optional=True)
    if stage.code == "docs_update":
        return replace(stage, sla_days=21)
    if stage.code == "control":
        return replace(stage, name="Итоговый контроль")
    return stage


MAIN = TemplateSpec(
    key="main",
    name="Базовый процесс взаимодействия с вузом",
    description=(
        "Полный цикл из ТЗ: от поиска контактов в вузе до ведения занятий, "
        "повышения квалификации преподавателей и контроля исполнения."
    ),
    created_days_ago=820,
    document="договор",
    versions=(
        VersionSpec(1, 800, _MAIN_V1_STAGES, _MAIN_TRANSITIONS),
        VersionSpec(
            2, 150, tuple(_v2_stage(stage) for stage in _MAIN_V1_STAGES), _MAIN_TRANSITIONS
        ),
    ),
)


# --- Короткий шаблон: дополнительное соглашение -------------------------------

_SHORT_STAGES = (
    StageSpec("contact", "Контакт", "Обсудить с вузом расширение сотрудничества", 7),
    StageSpec("meeting", "Встреча", "Согласовать состав новых программ", 14),
    StageSpec("documents", "Документы", "Подготовить дополнительное соглашение", 10),
    StageSpec("approval", "Согласование", "Согласовать соглашение с юристами вуза", 14),
    StageSpec("revision", "Доработка", "Внести замечания вуза", 7, optional=True),
    StageSpec(
        "signing", "Подписание", "Подписать дополнительное соглашение", None, final=True
    ),
)

_SHORT_TRANSITIONS = (
    TransitionSpec("contact", "meeting", "Назначена встреча"),
    TransitionSpec(
        "meeting", "contact", "Вернуть к контакту", backward=True, needs_comment=True
    ),
    TransitionSpec("meeting", "documents", "Собрать документы"),
    TransitionSpec(
        "documents", "meeting", "Вернуть к встрече", backward=True, needs_comment=True
    ),
    TransitionSpec("documents", "approval", "Отправить на согласование"),
    TransitionSpec("approval", "signing", "Согласовано, на подписание"),
    TransitionSpec(
        "approval", "revision", "Отправить на доработку", backward=True, needs_comment=True
    ),
    TransitionSpec("revision", "approval", "Вернуть на согласование"),
)

SHORT = TemplateSpec(
    key="short",
    name="Дополнительное соглашение",
    description=(
        "Короткий маршрут из концепции для расширения действующего сотрудничества: "
        "внедрение идёт по основному договору."
    ),
    created_days_ago=600,
    document="дополнительное соглашение",
    versions=(VersionSpec(1, 590, _SHORT_STAGES, _SHORT_TRANSITIONS),),
)

# Порядок важен: основным считается шаблон, заведённый первым, - по нему
# синхронизация с сайтом запускает процессы по новым заявкам.
TEMPLATES: tuple[TemplateSpec, ...] = (MAIN, SHORT)
TEMPLATE_BY_KEY = {template.key: template for template in TEMPLATES}


# --- Тексты этапов ------------------------------------------------------------
# Подстановки: {number}, {university}, {programs}, {contact}, {date},
# {students}, {teachers}, {licenses}, {document}.


@dataclass(frozen=True, slots=True)
class Upload:
    kind: str  # расширение файла - оно же выбирает генератор в files
    name: str
    chance: float = 1.0
    when_done: bool = False  # только если этап пройден: скан подписанного договора


@dataclass(frozen=True, slots=True)
class StageTexts:
    entry: tuple[str, ...] = ()  # комментарий к переходу на этап
    notes: tuple[str, ...] = ()  # заметки, пока договор на этапе
    uploads: tuple[Upload, ...] = ()


MAIN_TEXTS: dict[str, StageTexts] = {
    "contacts": StageTexts(
        notes=(
            "Нашли контакт через центр карьеры вуза",
            "Вуз сам написал через сайт ИТ Школы",
        ),
    ),
    "programs": StageTexts(
        entry=(
            "Ответственный от вуза: {contact}",
            "Связались с {contact}, вуз готов обсуждать сотрудничество",
        ),
        notes=("Кафедра просит прислать программы курсов", "Вуз интересуется: {programs}"),
        uploads=(Upload("pdf", "Каталог программ ИТ Школы.pdf", 0.5),),
    ),
    "meeting": StageTexts(
        entry=(
            "Состав программ согласован: {programs}",
            "Вуз подтвердил интерес к программам",
        ),
        notes=("Встреча назначена, со стороны вуза будут {contact} и заведующий кафедрой",),
        uploads=(
            Upload("pdf", "Протокол встречи.pdf", 0.9),
            Upload("png", "Схема учебного стенда.png", 0.3),
        ),
    ),
    "documents": StageTexts(
        entry=(
            "Встреча прошла {date}, вуз готов к подписанию",
            "Итоги встречи: сроки согласованы",
        ),
        notes=("Отправили пакет документов: договор, спецификацию, лицензионное соглашение",),
        uploads=(
            Upload("docx", "Проект договора {number}.docx"),
            Upload("zip", "Пакет документов.zip", 0.5),
        ),
    ),
    "corrections": StageTexts(
        entry=(
            "Юристы вуза прислали правки в раздел об ответственности сторон",
            "Вуз просит сдвинуть сроки передачи лицензий",
        ),
        notes=("Правки согласованы с нашим юристом",),
        uploads=(
            Upload("doc", "Договор — редакция вуза.doc"),
            Upload("pdf", "Протокол разногласий.pdf", 0.5),
        ),
    ),
    "signing": StageTexts(
        entry=(
            "Документы на подписи у ректора",
            "Отправили экземпляр, подписанный с нашей стороны",
        ),
        notes=("Подписание займёт около недели: ректор в командировке",),
        uploads=(Upload("jpeg", "Скан подписанного договора {number}.jpeg", when_done=True),),
    ),
    "handover": StageTexts(
        entry=("Договор {number} подписан обеими сторонами",),
        notes=("Передали методические материалы в электронном виде",),
        uploads=(
            Upload("pdf", "Лицензионный сертификат.pdf"),
            Upload("rar", "Методические материалы.rar", 0.6),
        ),
    ),
    "rollout": StageTexts(
        entry=(
            "Передали {licenses} лицензий и комплект материалов",
            "Доступы для вуза выданы",
        ),
        notes=("Проверили доступы студентов, всё работает",),
        uploads=(
            Upload("pdf", "Акт развёртывания стенда.pdf", 0.7),
            Upload("gz", "Журнал развёртывания.log.gz", 0.4),
            Upload("png", "Схема стенда.png", 0.3),
        ),
    ),
    "training": StageTexts(
        entry=(
            "Стенд развёрнут в компьютерном классе",
            "Продукт установлен, доступы проверены",
        ),
        notes=("Преподаватели прошли первый модуль обучения",),
        uploads=(
            Upload("xlsx", "Список обученных преподавателей.xlsx", 0.8),
            Upload("zip", "Сертификаты преподавателей.zip", 0.4),
        ),
    ),
    "curriculum": StageTexts(
        entry=(
            "Обучение прошли {teachers} преподавателей",
            "Преподаватели получили сертификаты",
        ),
        notes=("Проект программы отправлен в учебно-методический отдел",),
        uploads=(Upload("xlsx", "Учебный план.xlsx", 0.8),),
    ),
    "classes": StageTexts(
        entry=("Программа утверждена на учёном совете", "Учебный план обновлён и утверждён"),
        notes=(
            "Занятия идут по расписанию, в потоке {students} студентов",
            "Вуз просит открыть второй поток в следующем семестре",
        ),
        uploads=(
            Upload("xlsx", "Расписание занятий.xlsx", 0.6),
            Upload("jpeg", "Фото с занятия.jpeg", 0.4),
        ),
    ),
    "docs_update": StageTexts(
        entry=("Семестр завершён, обучение прошли {students} студентов",),
        notes=("Обновили методичку под новую версию продукта",),
        uploads=(Upload("pdf", "Документация по продукту.pdf", 0.6),),
    ),
    "upskilling": StageTexts(
        entry=("Документация и материалы обновлены",),
        notes=("Курс повышения квалификации запланирован на каникулы",),
        uploads=(Upload("docx", "Программа повышения квалификации.docx", 0.6),),
    ),
    "control": StageTexts(
        entry=("Цикл пройден, результаты переданы руководителю",),
        uploads=(Upload("pdf", "Итоговый отчёт.pdf", 0.9),),
    ),
}

SHORT_TEXTS: dict[str, StageTexts] = {
    "contact": StageTexts(notes=("Вуз хочет расширить сотрудничество",)),
    "meeting": StageTexts(
        entry=("Вуз предлагает добавить программы: {programs}",),
        uploads=(Upload("pdf", "Протокол встречи.pdf", 0.8),),
    ),
    "documents": StageTexts(
        entry=("Встреча проведена, готовим дополнительное соглашение",),
        uploads=(Upload("docx", "Проект дополнительного соглашения.docx"),),
    ),
    "approval": StageTexts(
        entry=("Проект соглашения отправлен в вуз",),
        notes=("Юристы вуза обещали ответить на этой неделе",),
        uploads=(Upload("pdf", "Лист согласования.pdf", 0.5),),
    ),
    "revision": StageTexts(uploads=(Upload("doc", "Замечания вуза.doc"),)),
    "signing": StageTexts(
        entry=("Соглашение подписано",),
        uploads=(Upload("jpeg", "Скан подписанного соглашения {number}.jpeg"),),
    ),
}

TEXTS: dict[str, dict[str, StageTexts]] = {MAIN.key: MAIN_TEXTS, SHORT.key: SHORT_TEXTS}

# Возврат назад требует комментария - вот они.
BACKWARD_REASONS: dict[tuple[str, str], str] = {
    ("programs", "contacts"): "Контакт не подтвердился: ответственный сменился, ищем нового",
    ("meeting", "programs"): "Встреча перенесена по просьбе вуза, уточняем состав программ",
    ("signing", "corrections"): "Юристы вуза прислали ещё правки к договору",
    ("rollout", "handover"): "Вузу нужны лицензии для второго компьютерного класса",
    ("classes", "curriculum"): "По итогам первых занятий программу нужно доработать",
    ("meeting", "contact"): "Вуз сменил ответственного, возвращаемся к контакту",
    ("documents", "meeting"): "Нужна повторная встреча по составу программ",
    ("approval", "revision"): "Отправили на доработку: у вуза замечания по срокам",
}

# Причина пропуска необязательного этапа - по коду пропускаемого этапа.
SKIP_REASONS: dict[str, str] = {
    "corrections": "Вуз снял замечания, правки не потребовались",
    "upskilling": "Преподаватели проходили повышение квалификации в прошлом году",
    "revision": "Замечания сняты на встрече, доработка не нужна",
}
