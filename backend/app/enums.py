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
