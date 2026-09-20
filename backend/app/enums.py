"""Перечисления предметной области.

В базе значения хранятся как varchar (см. раздел 9 концепции), проверка
допустимых значений выполняется на уровне схем Pydantic и сервисов.
"""

from enum import StrEnum


class Role(StrEnum):
    """Роли из Keycloak. Соответствуют разделу 8 концепции."""

    MANAGER = "manager"  # Пользователь / KAM
    HEAD = "head"  # Руководитель
    ADMIN = "admin"  # Администратор


class ContractStatus(StrEnum):
    DRAFT = "draft"
    ACTIVE = "active"
    SUSPENDED = "suspended"
    CLOSED = "closed"


class LicenseStatus(StrEnum):
    ACTIVE = "active"
    EXPIRED = "expired"
    REVOKED = "revoked"


class ImplementationStatus(StrEnum):
    """Статус внедрения программы или продукта внутри договора (раздел 4)."""

    NOT_STARTED = "not_started"
    IN_PROGRESS = "in_progress"
    IMPLEMENTED = "implemented"
    SUSPENDED = "suspended"


class WorkflowInstanceStatus(StrEnum):
    IN_PROGRESS = "in_progress"
    BLOCKED = "blocked"
    COMPLETED = "completed"
    CANCELLED = "cancelled"


class StageState(StrEnum):
    """Пять состояний этапа из раздела 3.4.

    Состояние не хранится отдельно, а вычисляется из истории переходов
    и текущего этапа экземпляра процесса.
    """

    NOT_STARTED = "not_started"
    ACTIVE = "active"
    COMPLETED = "completed"
    SKIPPED = "skipped"
    BLOCKED = "blocked"


class WorkflowEventType(StrEnum):
    STARTED = "started"
    FORWARD = "forward"
    BACKWARD = "backward"
    SKIPPED = "skipped"
    BLOCKED = "blocked"
    UNBLOCKED = "unblocked"
    COMPLETED = "completed"
    COMMENTED = "commented"


class IntegrationRunStatus(StrEnum):
    RUNNING = "running"
    SUCCESS = "success"
    FAILED = "failed"


class ImportRunStatus(StrEnum):
    """Состояния загрузки из раздела 6.2: от файла до итогов импорта."""

    UPLOADED = "uploaded"  # файл принят, показан предпросмотр
    VALIDATED = "validated"  # проверка прошла, можно импортировать
    COMPLETED = "completed"
    FAILED = "failed"


class ImportType(StrEnum):
    """Что именно загружаем. Набор колонок у каждого типа свой."""

    CATALOG = "catalog"  # сводная таблица из требования 1 ТЗ
    UNIVERSITIES = "universities"
    PROGRAMS = "programs"
    PRODUCTS = "products"


class AuditAction(StrEnum):
    CREATE = "create"
    UPDATE = "update"
    DELETE = "delete"


class AlertKind(StrEnum):
    """Причины, по которым договор попадает в проблемные (раздел 7)."""

    STAGE_STALE = "stage_stale"
    PROCESS_BLOCKED = "process_blocked"
    PROCESS_NOT_STARTED = "process_not_started"
    CONTRACT_EXPIRING = "contract_expiring"
    LICENSE_EXPIRING = "license_expiring"
    NO_MANAGER = "no_manager"
    NO_DOCUMENTS = "no_documents"
    IMPLEMENTATION_NOT_STARTED = "implementation_not_started"
    INTEGRATION_FAILED = "integration_failed"


class AlertSeverity(StrEnum):
    INFO = "info"
    WARNING = "warning"
    CRITICAL = "critical"
