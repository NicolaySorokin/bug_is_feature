/**
 * Подписи значений перечислений.
 *
 * Источник истины - сервер (GET /meta/enums), чтобы интерфейс и выгрузки
 * называли статусы одинаково. Здесь - запасной словарь на время загрузки.
 */
import type { MetaEnums } from "../api/types";

export const FALLBACK_LABELS: MetaEnums["labels"] = {
  role: { manager: "Пользователь / КАМ", head: "Руководитель", admin: "Администратор" },
  contract_status: { draft: "Черновик", active: "Действует", suspended: "Приостановлен", closed: "Закрыт" },
  license_status: { active: "Действует", expired: "Истекла", revoked: "Отозвана" },
  implementation_status: {
    not_started: "Не начато",
    in_progress: "В работе",
    implemented: "Внедрено",
    suspended: "Приостановлено",
  },
  workflow_status: { in_progress: "В работе", blocked: "Заблокирован", completed: "Завершён", cancelled: "Отменён" },
  stage_state: {
    not_started: "Не начат",
    active: "Активен",
    completed: "Завершён",
    skipped: "Пропущен",
    blocked: "Заблокирован",
  },
  workflow_event_type: {
    started: "Процесс запущен",
    forward: "Переход вперёд",
    backward: "Возврат назад",
    skipped: "Этап пропущен",
    blocked: "Процесс заблокирован",
    unblocked: "Блокировка снята",
    completed: "Процесс завершён",
    commented: "Комментарий",
  },
  integration_run_status: { running: "Выполняется", success: "Успешно", failed: "Ошибка" },
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
  signed: "по дате подписания",
  created: "по дате заведения",
  activity: "по движениям процесса",
};

/** Цветовая схема статуса для бейджа: одна логика во всех разделах. */
export type Tone = "success" | "warning" | "error" | "info" | "neutral" | "accent";

export const CONTRACT_STATUS_TONE: Record<string, Tone> = {
  active: "success",
  draft: "info",
  suspended: "warning",
  closed: "neutral",
};

export const IMPLEMENTATION_TONE: Record<string, Tone> = {
  not_started: "neutral",
  in_progress: "info",
  implemented: "success",
  suspended: "warning",
};

export const WORKFLOW_TONE: Record<string, Tone> = {
  in_progress: "accent",
  blocked: "error",
  completed: "success",
  cancelled: "neutral",
};

export const SEVERITY_TONE: Record<string, Tone> = { info: "info", warning: "warning", critical: "error" };

export const LICENSE_TONE: Record<string, Tone> = { active: "success", expired: "error", revoked: "neutral" };
