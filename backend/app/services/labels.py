"""Человеческие названия для значений перечислений.

Нужны в трёх местах: заголовки и ячейки выгрузок XLSX и PDF, подписи на
диаграммах и словарь для клиентской части (``GET /api/v1/meta/enums``).
Держим их в одном месте, чтобы отчёт и интерфейс не разъехались.
"""

from app.enums import (
    AlertKind,
    AlertSeverity,
    ContractStatus,
    ImplementationStatus,
    ImportRunStatus,
    IntegrationRunStatus,
    LicenseStatus,
    Role,
    StageState,
    WorkflowEventType,
    WorkflowInstanceStatus,
)

ROLE_LABELS = {
    Role.MANAGER: "Пользователь / КАМ",
    Role.HEAD: "Руководитель",
    Role.ADMIN: "Администратор",
}

CONTRACT_STATUS_LABELS = {
    ContractStatus.DRAFT: "Черновик",
    ContractStatus.ACTIVE: "Действует",
    ContractStatus.SUSPENDED: "Приостановлен",
    ContractStatus.CLOSED: "Закрыт",
}

LICENSE_STATUS_LABELS = {
    LicenseStatus.ACTIVE: "Действует",
    LicenseStatus.EXPIRED: "Истекла",
    LicenseStatus.REVOKED: "Отозвана",
}

IMPLEMENTATION_STATUS_LABELS = {
    ImplementationStatus.NOT_STARTED: "Не начато",
    ImplementationStatus.IN_PROGRESS: "В работе",
    ImplementationStatus.IMPLEMENTED: "Внедрено",
    ImplementationStatus.SUSPENDED: "Приостановлено",
}

WORKFLOW_STATUS_LABELS = {
    WorkflowInstanceStatus.IN_PROGRESS: "В работе",
    WorkflowInstanceStatus.BLOCKED: "Заблокирован",
    WorkflowInstanceStatus.COMPLETED: "Завершён",
    WorkflowInstanceStatus.CANCELLED: "Отменён",
}

STAGE_STATE_LABELS = {
    StageState.NOT_STARTED: "Не начат",
    StageState.ACTIVE: "Активен",
    StageState.COMPLETED: "Завершён",
    StageState.SKIPPED: "Пропущен",
    StageState.BLOCKED: "Заблокирован",
}

EVENT_TYPE_LABELS = {
    WorkflowEventType.STARTED: "Процесс запущен",
    WorkflowEventType.FORWARD: "Переход вперёд",
    WorkflowEventType.BACKWARD: "Возврат назад",
    WorkflowEventType.SKIPPED: "Этап пропущен",
    WorkflowEventType.BLOCKED: "Процесс заблокирован",
    WorkflowEventType.UNBLOCKED: "Блокировка снята",
    WorkflowEventType.COMPLETED: "Процесс завершён",
    WorkflowEventType.COMMENTED: "Комментарий",
}

INTEGRATION_RUN_STATUS_LABELS = {
    IntegrationRunStatus.RUNNING: "Выполняется",
    IntegrationRunStatus.SUCCESS: "Успешно",
    IntegrationRunStatus.FAILED: "Ошибка",
}

IMPORT_RUN_STATUS_LABELS = {
    ImportRunStatus.UPLOADED: "Файл загружен",
    ImportRunStatus.VALIDATED: "Проверен",
    ImportRunStatus.COMPLETED: "Импортирован",
    ImportRunStatus.FAILED: "Ошибка",
}

ALERT_KIND_LABELS = {
    AlertKind.STAGE_STALE: "Этап долго не менялся",
    AlertKind.PROCESS_BLOCKED: "Процесс заблокирован",
    AlertKind.PROCESS_NOT_STARTED: "Процесс не запущен",
    AlertKind.CONTRACT_EXPIRING: "Заканчивается срок договора",
    AlertKind.LICENSE_EXPIRING: "Заканчивается срок лицензии",
    AlertKind.NO_MANAGER: "Не назначен ответственный",
    AlertKind.NO_DOCUMENTS: "Не загружены документы",
    AlertKind.IMPLEMENTATION_NOT_STARTED: "Не начато внедрение",
    AlertKind.INTEGRATION_FAILED: "Ошибка синхронизации",
}

ALERT_SEVERITY_LABELS = {
    AlertSeverity.INFO: "Информация",
    AlertSeverity.WARNING: "Требует внимания",
    AlertSeverity.CRITICAL: "Критично",
}

# Всё вместе - в таком виде словарь уезжает на клиент.
ENUM_LABELS: dict[str, dict[str, str]] = {
    "role": {key.value: value for key, value in ROLE_LABELS.items()},
    "contract_status": {k.value: v for k, v in CONTRACT_STATUS_LABELS.items()},
    "license_status": {k.value: v for k, v in LICENSE_STATUS_LABELS.items()},
    "implementation_status": {k.value: v for k, v in IMPLEMENTATION_STATUS_LABELS.items()},
    "workflow_status": {k.value: v for k, v in WORKFLOW_STATUS_LABELS.items()},
    "stage_state": {k.value: v for k, v in STAGE_STATE_LABELS.items()},
    "workflow_event_type": {k.value: v for k, v in EVENT_TYPE_LABELS.items()},
    "integration_run_status": {k.value: v for k, v in INTEGRATION_RUN_STATUS_LABELS.items()},
    "import_run_status": {k.value: v for k, v in IMPORT_RUN_STATUS_LABELS.items()},
    "alert_kind": {k.value: v for k, v in ALERT_KIND_LABELS.items()},
    "alert_severity": {k.value: v for k, v in ALERT_SEVERITY_LABELS.items()},
}


def label(mapping: dict, value: object, default: str = "") -> str:
    """Подпись значения. Неизвестное значение отдаём как есть, а не прячем."""
    if value is None:
        return default
    return mapping.get(value, str(value))
