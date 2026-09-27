/**
 * Подписи значений перечислений.
 *
 * Источник истины - сервер (GET /meta/enums), чтобы интерфейс и выгрузки
 * называли статусы одинаково. Словарь разбит по сущностям: у взаимодействия,
 * этапа, договора, программы и продукта свои статусы, даже если коды
 * совпадают. Здесь - запасной словарь на время загрузки.
 */
import type { MetaEnums } from "../api/types";

export const FALLBACK_LABELS: MetaEnums["labels"] = {
  role: { manager: "Менеджер", head: "Руководитель", admin: "Администратор" },
  data_scope: { default: "По ролям", own: "Свои", team: "Команда", all: "Все", none: "Нет доступа" },
  permission: {
    sync_integrations: "Запуск обмена с LMS и сайтом",
    view_integration_log: "Журнал обмена с LMS и сайтом",
    view_personal_data: "Персональные данные студентов",
    edit_workflow_presentation: "Названия этапов и расположение схемы",
  },
  university_status: { pending: "На проверке", confirmed: "Подтверждён", archived: "В архиве" },
  interaction_status: {
    draft: "Черновик",
    in_progress: "В работе",
    blocked: "Заблокировано",
    completed: "Завершено",
    cancelled: "Отменено",
  },
  interaction_outcome: { successful: "Успешно", partial: "Частично успешно", unsuccessful: "Неуспешно" },
  closure_reason: {
    university_refused: "Отказ вуза",
    school_refused: "Отказ ИТ Школы",
    no_contact: "Нет контакта",
    lost_relevance: "Потеря актуальности",
    duplicate: "Дубль",
    other: "Иное",
  },
  interaction_source: { manual: "Заведено сотрудником", site: "Заявка вуза с сайта", lms: "LMS", import: "Загрузка из Excel" },
  workflow_version_status: {
    draft: "Черновик",
    active: "Действующая",
    deprecated: "Устаревшая",
    retired: "Выведена из использования",
  },
  contract_status: {
    draft: "Черновик",
    active: "Действует",
    suspended: "Приостановлен",
    closed: "Закрыт",
    cancelled: "Отменён до вступления в силу",
  },
  contract_closure_reason: { fulfilled: "Исполнен", expired: "Истёк срок", terminated: "Расторгнут" },
  license_status: { active: "Действует", expired: "Истекла", revoked: "Отозвана" },
  program_status: { not_started: "Не начата", in_progress: "Внедряется", implemented: "Внедрена", suspended: "Приостановлена" },
  product_status: { not_started: "Не начата", in_progress: "Выполняется", transferred: "Передан", suspended: "Приостановлена" },
  stage_state: {
    not_started: "Не начат",
    active: "Активен",
    completed: "Завершён",
    skipped: "Пропущен",
    blocked: "Заблокирован",
  },
  workflow_event_type: {
    created: "Взаимодействие заведено",
    started: "Процесс запущен",
    forward: "Переход вперёд",
    backward: "Возврат назад",
    skipped: "Этап пропущен",
    blocked: "Заблокировано",
    unblocked: "Блокировка снята",
    completed: "Взаимодействие завершено",
    cancelled: "Взаимодействие отменено",
    reassigned: "Сменён ответственный",
    commented: "Комментарий",
  },
  document_type: {
    contract: "Договор",
    contract_draft: "Проект договора",
    agreement: "Дополнительное соглашение",
    license: "Лицензия",
    act: "Акт приёма-передачи",
    letter: "Письмо или протокол",
    curriculum: "Учебный план",
    presentation: "Презентация",
    other: "Прочее",
  },
  integration_run_status: { running: "Выполняется", success: "Успешно", partial: "Частично", failed: "Ошибка" },
  mapping_status: { pending: "Ждёт решения", resolved: "Сопоставлено", ignored: "Не загружается" },
  import_run_status: { uploaded: "Файл загружен", validated: "Проверен", completed: "Импортирован", failed: "Ошибка" },
  alert_kind: {},
  alert_severity: { info: "Информация", warning: "Требует внимания", critical: "Критично" },
};

export const ROLE_SHORT: Record<string, string> = { manager: "Менеджер", head: "Руководитель", admin: "Администратор" };

export const IMPORT_TYPE_LABELS: Record<string, string> = {
  catalog: "Сводный каталог",
  universities: "Вузы",
  contacts: "Ответственные от вузов",
  programs: "ИТ-программы",
  products: "ИТ-продукты",
  vendors: "Вендоры",
  learners: "Обучающиеся (LMS)",
};

export const PERIOD_BASIS_LABELS: Record<string, string> = {
  created: "по дате начала взаимодействия",
  activity: "по движениям процесса",
  signed: "по дате подписания договора",
  closed: "по дате закрытия",
};

/** Цветовая схема статуса для бейджа: одна логика во всех разделах. */
export type Tone = "success" | "warning" | "error" | "info" | "neutral" | "accent";

export const INTERACTION_TONE: Record<string, Tone> = {
  draft: "info",
  in_progress: "accent",
  blocked: "error",
  completed: "success",
  cancelled: "neutral",
};

export const OUTCOME_TONE: Record<string, Tone> = { successful: "success", partial: "warning", unsuccessful: "neutral" };

export const CONTRACT_STATUS_TONE: Record<string, Tone> = {
  active: "success",
  draft: "info",
  suspended: "warning",
  closed: "neutral",
  cancelled: "neutral",
};

export const PROGRAM_TONE: Record<string, Tone> = {
  not_started: "neutral",
  in_progress: "info",
  implemented: "success",
  suspended: "warning",
};

export const PRODUCT_TONE: Record<string, Tone> = {
  not_started: "neutral",
  in_progress: "info",
  transferred: "success",
  suspended: "warning",
};

export const UNIVERSITY_TONE: Record<string, Tone> = { pending: "warning", confirmed: "success", archived: "neutral" };

export const VERSION_TONE: Record<string, Tone> = { draft: "info", active: "success", deprecated: "warning", retired: "neutral" };

export const RUN_TONE: Record<string, Tone> = { running: "info", success: "success", partial: "warning", failed: "error" };

export const SEVERITY_TONE: Record<string, Tone> = { info: "info", warning: "warning", critical: "error" };

export const LICENSE_TONE: Record<string, Tone> = { active: "success", expired: "error", revoked: "neutral" };

export const PROGRAM_STATUSES = ["not_started", "in_progress", "implemented", "suspended"] as const;
export const PRODUCT_STATUSES = ["not_started", "in_progress", "transferred", "suspended"] as const;
export const INTERACTION_STATUSES = ["draft", "in_progress", "blocked", "completed", "cancelled"] as const;
export const CLOSURE_REASONS = [
  "university_refused",
  "school_refused",
  "no_contact",
  "lost_relevance",
  "duplicate",
  "other",
] as const;
export const DOCUMENT_TYPES = [
  "contract",
  "contract_draft",
  "agreement",
  "license",
  "act",
  "letter",
  "curriculum",
  "presentation",
  "other",
] as const;
