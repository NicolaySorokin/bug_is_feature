"""Человеческие названия для значений перечислений.

Раздел 11 «Решений по бизнес-модели»: в базе и API - стабильный английский
код, в интерфейсе и выгрузках - подпись из одного словаря. Словарь
разбит по сущностям: один и тот же код у разных сущностей называется
по-разному («Черновик» у договора и «Черновик» у взаимодействия совпадают,
а «Завершён» этап и «Завершено» взаимодействие - уже нет), поэтому общий
словарь «код -> подпись» без сущности не используется.

Нужны в трёх местах: заголовки и ячейки выгрузок XLSX и PDF, подписи на
диаграммах и словарь для клиентской части (``GET /api/v1/meta/enums``).
"""

from app.enums import (
    AlertKind,
    AlertSeverity,
    ClosureReason,
    ContractClosureReason,
    ContractStatus,
    DataScope,
    DocumentType,
    ImportRunStatus,
    IntegrationRunStatus,
    InteractionOutcome,
    InteractionSource,
    InteractionStatus,
    LicenseStatus,
    MappingStatus,
    Permission,
    ProductTransferStatus,
    ProgramImplementationStatus,
    Role,
    StageState,
    UniversityStatus,
    WorkflowEventType,
    WorkflowVersionStatus,
)

ROLE_LABELS = {
    Role.MANAGER: "Менеджер",
    Role.HEAD: "Руководитель",
    Role.ADMIN: "Администратор",
}

DATA_SCOPE_LABELS = {
    DataScope.DEFAULT: "По ролям",
    DataScope.OWN: "Свои",
    DataScope.TEAM: "Команда",
    DataScope.ALL: "Все",
    DataScope.NONE: "Нет доступа",
}

PERMISSION_LABELS = {
    Permission.SYNC_INTEGRATIONS: "Запуск обмена с LMS и сайтом",
    Permission.VIEW_INTEGRATION_LOG: "Журнал обмена с LMS и сайтом",
    Permission.VIEW_PERSONAL_DATA: "Персональные данные студентов",
    Permission.EDIT_WORKFLOW_PRESENTATION: "Названия этапов и расположение схемы",
}

UNIVERSITY_STATUS_LABELS = {
    UniversityStatus.PENDING: "На проверке",
    UniversityStatus.CONFIRMED: "Подтверждён",
    UniversityStatus.ARCHIVED: "В архиве",
}

INTERACTION_STATUS_LABELS = {
    InteractionStatus.DRAFT: "Черновик",
    InteractionStatus.IN_PROGRESS: "В работе",
    InteractionStatus.BLOCKED: "Заблокировано",
    InteractionStatus.COMPLETED: "Завершено",
    InteractionStatus.CANCELLED: "Отменено",
}

OUTCOME_LABELS = {
    InteractionOutcome.SUCCESSFUL: "Успешно",
    InteractionOutcome.PARTIAL: "Частично успешно",
    InteractionOutcome.UNSUCCESSFUL: "Неуспешно",
}

CLOSURE_REASON_LABELS = {
    ClosureReason.UNIVERSITY_REFUSED: "Отказ вуза",
    ClosureReason.SCHOOL_REFUSED: "Отказ ИТ Школы",
    ClosureReason.NO_CONTACT: "Нет контакта",
    ClosureReason.LOST_RELEVANCE: "Потеря актуальности",
    ClosureReason.DUPLICATE: "Дубль",
    ClosureReason.OTHER: "Иное",
}

SOURCE_LABELS = {
    InteractionSource.MANUAL: "Заведено сотрудником",
    InteractionSource.SITE: "Заявка вуза с сайта",
    InteractionSource.LMS: "LMS",
    InteractionSource.IMPORT: "Загрузка из Excel",
}

VERSION_STATUS_LABELS = {
    WorkflowVersionStatus.DRAFT: "Черновик",
    WorkflowVersionStatus.ACTIVE: "Действующая",
    WorkflowVersionStatus.DEPRECATED: "Устаревшая",
    WorkflowVersionStatus.RETIRED: "Выведена из использования",
}

TEMPLATE_STATUS_LABELS = {"enabled": "Активен", "disabled": "Отключён"}

CONTRACT_STATUS_LABELS = {
    ContractStatus.DRAFT: "Черновик",
    ContractStatus.ACTIVE: "Действует",
    ContractStatus.SUSPENDED: "Приостановлен",
    ContractStatus.CLOSED: "Закрыт",
    ContractStatus.CANCELLED: "Отменён до вступления в силу",
}

CONTRACT_CLOSURE_LABELS = {
    ContractClosureReason.FULFILLED: "Исполнен",
    ContractClosureReason.EXPIRED: "Истёк срок",
    ContractClosureReason.TERMINATED: "Расторгнут",
}

LICENSE_STATUS_LABELS = {
    LicenseStatus.ACTIVE: "Действует",
    LicenseStatus.EXPIRED: "Истекла",
    LicenseStatus.REVOKED: "Отозвана",
}

PROGRAM_STATUS_LABELS = {
    ProgramImplementationStatus.NOT_STARTED: "Не начата",
    ProgramImplementationStatus.IN_PROGRESS: "Внедряется",
    ProgramImplementationStatus.IMPLEMENTED: "Внедрена",
    ProgramImplementationStatus.SUSPENDED: "Приостановлена",
}
# Прежнее имя.
IMPLEMENTATION_STATUS_LABELS = PROGRAM_STATUS_LABELS

PRODUCT_STATUS_LABELS = {
    ProductTransferStatus.NOT_STARTED: "Не начата",
    ProductTransferStatus.IN_PROGRESS: "Выполняется",
    ProductTransferStatus.TRANSFERRED: "Передан",
    ProductTransferStatus.SUSPENDED: "Приостановлена",
}

STAGE_STATE_LABELS = {
    StageState.NOT_STARTED: "Не начат",
    StageState.ACTIVE: "Активен",
    StageState.COMPLETED: "Завершён",
    StageState.SKIPPED: "Пропущен",
    StageState.BLOCKED: "Заблокирован",
}

EVENT_TYPE_LABELS = {
    WorkflowEventType.CREATED: "Взаимодействие заведено",
    WorkflowEventType.STARTED: "Процесс запущен",
    WorkflowEventType.FORWARD: "Переход вперёд",
    WorkflowEventType.BACKWARD: "Возврат назад",
    WorkflowEventType.SKIPPED: "Этап пропущен",
    WorkflowEventType.BLOCKED: "Заблокировано",
    WorkflowEventType.UNBLOCKED: "Блокировка снята",
    WorkflowEventType.COMPLETED: "Взаимодействие завершено",
    WorkflowEventType.CANCELLED: "Взаимодействие отменено",
    WorkflowEventType.REASSIGNED: "Сменён ответственный",
    WorkflowEventType.COMMENTED: "Комментарий",
}

DOCUMENT_TYPE_LABELS = {
    DocumentType.CONTRACT: "Договор",
    DocumentType.CONTRACT_DRAFT: "Проект договора",
    DocumentType.AGREEMENT: "Дополнительное соглашение",
    DocumentType.LICENSE: "Лицензия",
    DocumentType.ACT: "Акт приёма-передачи",
    DocumentType.LETTER: "Письмо или протокол",
    DocumentType.CURRICULUM: "Учебный план",
    DocumentType.PRESENTATION: "Презентация",
    DocumentType.OTHER: "Прочее",
}

INTEGRATION_RUN_STATUS_LABELS = {
    IntegrationRunStatus.RUNNING: "Выполняется",
    IntegrationRunStatus.SUCCESS: "Успешно",
    IntegrationRunStatus.PARTIAL: "Частично",
    IntegrationRunStatus.FAILED: "Ошибка",
}

MAPPING_STATUS_LABELS = {
    MappingStatus.PENDING: "Ждёт решения",
    MappingStatus.RESOLVED: "Сопоставлено",
    MappingStatus.IGNORED: "Не загружается",
}

IMPORT_RUN_STATUS_LABELS = {
    ImportRunStatus.UPLOADED: "Файл загружен",
    ImportRunStatus.VALIDATED: "Проверен",
    ImportRunStatus.COMPLETED: "Импортирован",
    ImportRunStatus.FAILED: "Ошибка",
}

ALERT_KIND_LABELS = {
    AlertKind.STAGE_STALE: "Просрочен срок этапа",
    AlertKind.PROCESS_BLOCKED: "Взаимодействие заблокировано",
    AlertKind.PROCESS_NOT_STARTED: "Процесс не запущен",
    AlertKind.CONTRACT_EXPIRING: "Заканчивается срок договора",
    AlertKind.LICENSE_EXPIRING: "Заканчивается срок лицензии",
    AlertKind.NO_MANAGER: "Не назначен ответственный",
    AlertKind.NO_DOCUMENTS: "Не загружен обязательный документ",
    AlertKind.IMPLEMENTATION_NOT_STARTED: "Не начато внедрение",
    AlertKind.PRODUCT_WITHOUT_PROGRAM: "Продукт без программы",
    AlertKind.INTEGRATION_FAILED: "Ошибка синхронизации",
    AlertKind.MAPPING_PENDING: "Ждут сопоставления",
    AlertKind.UNIVERSITY_PENDING: "Вузы на проверке",
}

ALERT_SEVERITY_LABELS = {
    AlertSeverity.INFO: "Информация",
    AlertSeverity.WARNING: "Требует внимания",
    AlertSeverity.CRITICAL: "Критично",
}


def _plain(mapping: dict) -> dict[str, str]:
    return {str(key): value for key, value in mapping.items()}


# Всё вместе - в таком виде словарь уезжает на клиент: сущность.код -> подпись.
ENUM_LABELS: dict[str, dict[str, str]] = {
    "role": _plain(ROLE_LABELS),
    "data_scope": _plain(DATA_SCOPE_LABELS),
    "permission": _plain(PERMISSION_LABELS),
    "university_status": _plain(UNIVERSITY_STATUS_LABELS),
    "interaction_status": _plain(INTERACTION_STATUS_LABELS),
    "interaction_outcome": _plain(OUTCOME_LABELS),
    "closure_reason": _plain(CLOSURE_REASON_LABELS),
    "interaction_source": _plain(SOURCE_LABELS),
    "workflow_version_status": _plain(VERSION_STATUS_LABELS),
    "workflow_template_status": dict(TEMPLATE_STATUS_LABELS),
    "contract_status": _plain(CONTRACT_STATUS_LABELS),
    "contract_closure_reason": _plain(CONTRACT_CLOSURE_LABELS),
    "license_status": _plain(LICENSE_STATUS_LABELS),
    "program_status": _plain(PROGRAM_STATUS_LABELS),
    "product_status": _plain(PRODUCT_STATUS_LABELS),
    "stage_state": _plain(STAGE_STATE_LABELS),
    "workflow_event_type": _plain(EVENT_TYPE_LABELS),
    "document_type": _plain(DOCUMENT_TYPE_LABELS),
    "integration_run_status": _plain(INTEGRATION_RUN_STATUS_LABELS),
    "mapping_status": _plain(MAPPING_STATUS_LABELS),
    "import_run_status": _plain(IMPORT_RUN_STATUS_LABELS),
    "alert_kind": _plain(ALERT_KIND_LABELS),
    "alert_severity": _plain(ALERT_SEVERITY_LABELS),
}


def label(mapping: dict, value: object, default: str = "") -> str:
    """Подпись значения. Неизвестное значение отдаём как есть, а не прячем."""
    if value is None:
        return default
    return mapping.get(value, str(value))
