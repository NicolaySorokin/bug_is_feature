"""Перечисления предметной области.

В базе и API хранится английский код, русские подписи лежат в app.services.labels.
У каждой сущности свои статусы, даже если коды совпадают.
"""

from enum import StrEnum


class Role(StrEnum):
    """Роли из Keycloak. Роли не наследуются, совмещение задаётся несколькими ролями."""

    MANAGER = "manager"  # Менеджер (КАМ)
    HEAD = "head"  # Руководитель
    ADMIN = "admin"  # Администратор


class DataScope(StrEnum):
    """Область бизнес-данных сотрудника.

    default значит по ролям: менеджеру own, руководителю team, администратору none.
    """

    DEFAULT = "default"
    OWN = "own"  # свои взаимодействия и явно открытые вузы
    TEAM = "team"  # плюс взаимодействия менеджеров своей команды
    ALL = "all"  # все бизнес-данные организации
    NONE = "none"  # только административные функции


class Permission(StrEnum):
    """Дополнительные права сверх роли, их выдаёт администратор."""

    SYNC_INTEGRATIONS = "sync_integrations"
    VIEW_INTEGRATION_LOG = "view_integration_log"
    VIEW_PERSONAL_DATA = "view_personal_data"
    EDIT_WORKFLOW_PRESENTATION = "edit_workflow_presentation"


class UniversityStatus(StrEnum):
    """Жизненный цикл записи о вузе: единый путь для всех источников."""

    PENDING = "pending"  # заведён импортом, обменом или менеджером, ждёт проверки
    CONFIRMED = "confirmed"  # проверен, с ним можно работать
    ARCHIVED = "archived"  # в архиве или объединён с другим вузом


class InteractionStatus(StrEnum):
    """Жизненный цикл взаимодействия (экземпляра workflow)."""

    DRAFT = "draft"  # создано, процесс ещё не запущен
    IN_PROGRESS = "in_progress"
    BLOCKED = "blocked"  # продолжение временно невозможно, причина обязательна
    COMPLETED = "completed"  # достигнут финальный этап шаблона
    CANCELLED = "cancelled"  # досрочно прекращено, причина обязательна


# Старое имя: там, где речь о состоянии процесса.
WorkflowInstanceStatus = InteractionStatus

# Взаимодействие ещё идёт: по нему ждут действий.
OPEN_INTERACTION_STATUSES = frozenset(
    {InteractionStatus.DRAFT, InteractionStatus.IN_PROGRESS, InteractionStatus.BLOCKED}
)
CLOSED_INTERACTION_STATUSES = frozenset(
    {InteractionStatus.COMPLETED, InteractionStatus.CANCELLED}
)


class InteractionOutcome(StrEnum):
    """Бизнес-результат закрытого взаимодействия. Хранится отдельно от статуса."""

    SUCCESSFUL = "successful"
    PARTIAL = "partial"
    UNSUCCESSFUL = "unsuccessful"


class ClosureReason(StrEnum):
    """Причина неуспешного завершения или отмены взаимодействия."""

    UNIVERSITY_REFUSED = "university_refused"
    SCHOOL_REFUSED = "school_refused"
    NO_CONTACT = "no_contact"
    LOST_RELEVANCE = "lost_relevance"
    DUPLICATE = "duplicate"
    OTHER = "other"


class InteractionSource(StrEnum):
    """Откуда появилось взаимодействие."""

    MANUAL = "manual"  # завёл сотрудник
    SITE = "site"  # заявка вуза на сотрудничество с сайта
    LMS = "lms"
    IMPORT = "import"  # загрузка каталога из Excel


class WorkflowVersionStatus(StrEnum):
    """Жизненный цикл версии шаблона."""

    DRAFT = "draft"  # правится, процессы не запускаются
    ACTIVE = "active"  # единственная действующая версия шаблона
    DEPRECATED = "deprecated"  # новые не запускаются, начатые продолжаются
    RETIRED = "retired"  # процессов не осталось, хранится для истории


class ContractStatus(StrEnum):
    DRAFT = "draft"
    ACTIVE = "active"
    SUSPENDED = "suspended"
    CLOSED = "closed"
    CANCELLED = "cancelled"  # отменён до вступления в силу


class ContractClosureReason(StrEnum):
    """Почему закрыт договор (только для статуса closed)."""

    FULFILLED = "fulfilled"  # исполнен
    EXPIRED = "expired"  # истёк срок
    TERMINATED = "terminated"  # расторгнут


class LicenseStatus(StrEnum):
    ACTIVE = "active"
    EXPIRED = "expired"
    REVOKED = "revoked"


class ProgramImplementationStatus(StrEnum):
    """Внедрение ИТ-программы во взаимодействии."""

    NOT_STARTED = "not_started"
    IN_PROGRESS = "in_progress"
    IMPLEMENTED = "implemented"
    SUSPENDED = "suspended"


# Прежнее имя статуса программы.
ImplementationStatus = ProgramImplementationStatus


class ProductTransferStatus(StrEnum):
    """Передача ИТ-продукта вузу. Отдельное перечисление: у продукта не
    «внедрён», а «передан»."""

    NOT_STARTED = "not_started"
    IN_PROGRESS = "in_progress"
    TRANSFERRED = "transferred"
    SUSPENDED = "suspended"


class StageState(StrEnum):
    """Пять состояний этапа. Не хранятся, а вычисляются из истории переходов."""

    NOT_STARTED = "not_started"
    ACTIVE = "active"
    COMPLETED = "completed"
    SKIPPED = "skipped"
    BLOCKED = "blocked"


class WorkflowEventType(StrEnum):
    CREATED = "created"  # взаимодействие заведено (черновик)
    STARTED = "started"
    FORWARD = "forward"
    BACKWARD = "backward"
    SKIPPED = "skipped"
    BLOCKED = "blocked"
    UNBLOCKED = "unblocked"
    COMPLETED = "completed"
    CANCELLED = "cancelled"
    REASSIGNED = "reassigned"  # сменился ответственный
    COMMENTED = "commented"


class DocumentType(StrEnum):
    """Тип документа во вложении: по нему проверяется комплектность этапа."""

    CONTRACT = "contract"  # договор
    # Проект договора, в том числе по шаблону. Не
    # закрывает обязательный документ «Договор».
    CONTRACT_DRAFT = "contract_draft"
    AGREEMENT = "agreement"  # дополнительное соглашение
    LICENSE = "license"  # лицензионный договор, сертификат лицензии
    ACT = "act"  # акт приёма-передачи
    LETTER = "letter"  # письмо, протокол встречи
    CURRICULUM = "curriculum"  # учебный план, программа курса
    PRESENTATION = "presentation"
    OTHER = "other"


class IntegrationRunStatus(StrEnum):
    RUNNING = "running"
    SUCCESS = "success"
    PARTIAL = "partial"  # часть записей не загружена, см. ошибки запуска
    FAILED = "failed"


class MappingStatus(StrEnum):
    """Сопоставление внешней записи с записью системы."""

    PENDING = "pending"  # ждёт решения администратора
    RESOLVED = "resolved"  # сопоставлено с существующей или создана новая
    IGNORED = "ignored"  # запись источника не нужна


class ImportRunStatus(StrEnum):
    """Состояния загрузки: от файла до итогов импорта."""

    UPLOADED = "uploaded"  # файл принят, показан предпросмотр
    VALIDATED = "validated"  # проверка прошла, можно импортировать
    COMPLETED = "completed"
    FAILED = "failed"


class ImportType(StrEnum):
    """Что именно загружаем. Набор колонок у каждого типа свой."""

    CATALOG = "catalog"  # сводная таблица из требования 1 ТЗ
    UNIVERSITIES = "universities"
    CONTACTS = "contacts"  # ответственные от вузов
    PROGRAMS = "programs"
    PRODUCTS = "products"
    VENDORS = "vendors"  # каталог «Вендоры»: компании, продукты, контакты
    LEARNERS = "learners"  # анкеты обучающихся из LMS


class AuditAction(StrEnum):
    CREATE = "create"
    UPDATE = "update"
    DELETE = "delete"


class AlertKind(StrEnum):
    """Почему взаимодействие попало в проблемные."""

    STAGE_STALE = "stage_stale"
    PROCESS_BLOCKED = "process_blocked"
    PROCESS_NOT_STARTED = "process_not_started"
    CONTRACT_EXPIRING = "contract_expiring"
    LICENSE_EXPIRING = "license_expiring"
    NO_MANAGER = "no_manager"
    NO_DOCUMENTS = "no_documents"
    IMPLEMENTATION_NOT_STARTED = "implementation_not_started"
    PRODUCT_WITHOUT_PROGRAM = "product_without_program"
    INTEGRATION_FAILED = "integration_failed"
    MAPPING_PENDING = "mapping_pending"
    UNIVERSITY_PENDING = "university_pending"


class AlertSeverity(StrEnum):
    INFO = "info"
    WARNING = "warning"
    CRITICAL = "critical"
