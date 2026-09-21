import type { Contract, Dashboard, Report, University, User, WorkflowView } from "./types";

export const mockUsers: User[] = [
  { id: "u-petrov", username: "petrov", full_name: "Пётр Петров", email: "petrov@example.com", is_active: true, roles: ["manager"] },
  { id: "u-ivanova", username: "ivanova", full_name: "Мария Иванова", email: "ivanova@example.com", is_active: true, roles: ["manager"] },
  { id: "u-orlova", username: "orlova", full_name: "Ольга Орлова", email: "orlova@example.com", is_active: true, roles: ["manager", "head"] },
  { id: "u-admin", username: "admin", full_name: "Администратор платформы", email: "admin@example.com", is_active: true, roles: ["manager", "head", "admin"] },
];

export const mockUniversities: University[] = [
  { id: "univ-mtusi", name: "Московский технический университет связи и информатики", short_name: "МТУСИ", city: "Москва", manager_id: "u-petrov", is_active: true, contacts: [{ id: "contact-1", full_name: "Анна Соколова", position: "Проректор по учебной работе", email: "sokolova@example.edu" }] },
  { id: "univ-spbgut", name: "Санкт-Петербургский университет телекоммуникаций", short_name: "СПбГУТ", city: "Санкт-Петербург", manager_id: "u-petrov", is_active: true, contacts: [{ id: "contact-2", full_name: "Дмитрий Орехов", position: "Начальник учебного управления", email: "orehov@example.edu" }] },
  { id: "univ-kai", name: "Казанский национальный исследовательский технический университет", short_name: "КНИТУ-КАИ", city: "Казань", manager_id: "u-ivanova", is_active: true },
  { id: "univ-urfu", name: "Уральский федеральный университет", short_name: "УрФУ", city: "Екатеринбург", manager_id: "u-orlova", is_active: true },
];

const programs = [
  { id: "program-python", name: "Python-разработчик", direction_id: "direction-dev", direction: { id: "direction-dev", name: "Разработка" } },
  { id: "program-qa", name: "Инженер по тестированию", direction_id: "direction-qa", direction: { id: "direction-qa", name: "QA" } },
  { id: "program-data", name: "Аналитик данных", direction_id: "direction-data", direction: { id: "direction-data", name: "Аналитика данных" } },
  { id: "program-sec", name: "Специалист по защите информации", direction_id: "direction-sec", direction: { id: "direction-sec", name: "Информационная безопасность" } },
];

const products = [
  { id: "product-platform", name: "Платформа онлайн-обучения", vendor_id: "vendor-rt", vendor: { id: "vendor-rt", name: "Ростелеком" } },
  { id: "product-devops", name: "Песочница DevOps", vendor_id: "vendor-rt", vendor: { id: "vendor-rt", name: "Ростелеком" } },
  { id: "product-cyber", name: "Стенд киберполигона", vendor_id: "vendor-rt", vendor: { id: "vendor-rt", name: "Ростелеком" } },
];

export const mockContracts: Contract[] = [
  { id: "contract-1", university_id: "univ-mtusi", university: mockUniversities[0], manager_id: "u-petrov", number: "ДГ-2025-001", title: "Основной договор о сотрудничестве", signed_at: "2025-09-15", valid_from: "2025-09-15", valid_to: "2026-10-30", status: "active", comment: "Лицензия передана в вуз.", programs: [{ id: "cp-1", program_id: "program-python", implementation_status: "implemented", program: programs[0] }], products: [{ id: "cprod-1", product_id: "product-platform", transfer_status: "in_progress", product: products[0] }] },
  { id: "contract-2", university_id: "univ-spbgut", university: mockUniversities[1], manager_id: "u-petrov", number: "ДГ-2025-047", title: "Подготовка инженеров по тестированию", signed_at: "2026-02-03", valid_from: "2026-02-03", valid_to: "2027-07-18", status: "active", comment: "Вуз попросил добавить второй поток.", programs: [{ id: "cp-2", program_id: "program-qa", implementation_status: "in_progress", program: programs[1] }], products: [{ id: "cprod-2", product_id: "product-platform", transfer_status: "implemented", product: products[0] }] },
  { id: "contract-3", university_id: "univ-kai", university: mockUniversities[2], manager_id: "u-ivanova", number: "ДГ-2026-003", title: "DevOps и облачная инфраструктура", signed_at: "2026-05-24", valid_from: "2026-05-24", valid_to: "2027-05-26", status: "active", comment: "Ждём подтверждение программы.", programs: [{ id: "cp-3", program_id: "program-python", implementation_status: "in_progress", program: programs[0] }], products: [{ id: "cprod-3", product_id: "product-devops", transfer_status: "in_progress", product: products[1] }] },
  { id: "contract-4", university_id: "univ-urfu", university: mockUniversities[3], manager_id: "u-orlova", number: "ДГ-2026-021", title: "Киберполигон и защита информации", signed_at: "2026-08-01", valid_from: "2026-08-01", valid_to: "2027-08-01", status: "active", comment: "Лицензия требует продления.", programs: [{ id: "cp-4", program_id: "program-sec", implementation_status: "not_started", program: programs[3] }], products: [{ id: "cprod-4", product_id: "product-cyber", transfer_status: "suspended", product: products[2] }] },
  { id: "contract-5", university_id: "univ-mtusi", university: mockUniversities[0], manager_id: "u-petrov", number: "ДГ-2026-014", title: "Расширение состава программ", signed_at: null, valid_from: null, valid_to: null, status: "draft", comment: "Нужно согласовать состав программ.", programs: [{ id: "cp-5", program_id: "program-data", implementation_status: "not_started", program: programs[2] }], products: [] },
  { id: "contract-6", university_id: "univ-kai", university: mockUniversities[2], manager_id: "u-ivanova", number: "ДГ-2026-033", title: "Пилот по аналитике данных", signed_at: null, valid_from: null, valid_to: null, status: "draft", comment: "Ответственный пока не назначен.", programs: [{ id: "cp-6", program_id: "program-data", implementation_status: "not_started", program: programs[2] }], products: [] },
];

const stage = (id: string, code: string, name: string, x: number, y: number, state: string): { id: string; code: string; name: string; description: string; sort_order: number; is_optional: boolean; is_final: boolean; sla_days: number; layout_x: number; layout_y: number; state: string } => ({ id, code, name, description: "Контрольный этап взаимодействия с вузом", sort_order: x, is_optional: code === "revision", is_final: code === "signing", sla_days: code === "meeting" ? 14 : 7, layout_x: x * 160, layout_y: y, state });

export function mockWorkflow(contractId: string): WorkflowView {
  const stages = [
    stage("stage-contact", "contact", "Контакт", 1, 0, "completed"),
    stage("stage-meeting", "meeting", "Встреча", 2, 0, "completed"),
    stage("stage-documents", "documents", "Документы", 3, 0, "active"),
    stage("stage-approval", "approval", "Согласование", 4, 0, "not_started"),
    stage("stage-revision", "revision", "Доработка", 4, 1, "not_started"),
    stage("stage-signing", "signing", "Подписание", 5, 0, "not_started"),
  ];
  const transitions = [
    { id: "transition-1", from_stage_id: "stage-contact", to_stage_id: "stage-meeting", name: "Назначена встреча", is_backward: false, requires_comment: false },
    { id: "transition-2", from_stage_id: "stage-meeting", to_stage_id: "stage-documents", name: "Собрать документы", is_backward: false, requires_comment: false },
    { id: "transition-3", from_stage_id: "stage-documents", to_stage_id: "stage-approval", name: "Отправить на согласование", is_backward: false, requires_comment: false },
    { id: "transition-4", from_stage_id: "stage-documents", to_stage_id: "stage-meeting", name: "Вернуть к встрече", is_backward: true, requires_comment: true },
    { id: "transition-5", from_stage_id: "stage-approval", to_stage_id: "stage-signing", name: "Согласовано, на подписание", is_backward: false, requires_comment: false },
    { id: "transition-6", from_stage_id: "stage-approval", to_stage_id: "stage-revision", name: "Отправить на доработку", is_backward: true, requires_comment: true },
    { id: "transition-7", from_stage_id: "stage-revision", to_stage_id: "stage-approval", name: "Вернуть на согласование", is_backward: false, requires_comment: false },
  ];
  const event = (id: string, from: string | null, to: string, type: string, comment: string, createdAt: string): WorkflowView["events"][number] => ({ id, from_stage_id: from, to_stage_id: to, user_id: "u-petrov", event_type: type, comment, created_at: createdAt });
  return {
    id: `workflow-${contractId}`,
    contract_id: contractId,
    workflow_version_id: "version-1",
    current_stage_id: "stage-documents",
    status: "in_progress",
    current_stage_started_at: "2026-09-16T09:30:00Z",
    started_at: "2026-08-25T08:00:00Z",
    completed_at: null,
    version: { id: "version-1", template_id: "template-1", version_number: 1, published_at: "2026-08-01T10:00:00Z", stages: stages.map(({ state: _state, ...item }) => item), transitions },
    stage_states: stages.map(({ id, state }) => ({ stage_id: id, state: state as WorkflowView["stage_states"][number]["state"] })),
    available_transitions: transitions.filter((item) => item.from_stage_id === "stage-documents"),
    events: [
      event("event-1", null, "stage-contact", "started", "Процесс запущен", "2026-08-25T08:00:00Z"),
      event("event-2", "stage-contact", "stage-meeting", "forward", "Встреча назначена", "2026-08-28T12:00:00Z"),
      event("event-3", "stage-meeting", "stage-documents", "forward", "Вуз подтвердил состав документов", "2026-09-16T09:30:00Z"),
    ],
  };
}

export const mockDashboard: Dashboard = {
  role: "manager",
  generated_at: "2026-09-21T09:00:00Z",
  counters: { contracts: 8, contracts_active: 5, contracts_draft: 3, universities: 6, my_contracts: 4, processes_in_progress: 5, processes_blocked: 1, processes_completed: 2, alerts: 5 },
  alerts: [
    { kind: "stage_stale", kind_label: "Задержка этапа", severity: "warning", severity_label: "Внимание", message: "Договор ДГ-2026-003 находится на согласовании 19 дней", contract_id: "contract-3", contract_number: "ДГ-2026-003", university_name: "КНИТУ-КАИ", manager_name: "Мария Иванова", days: 19 },
    { kind: "license_expiring", kind_label: "Истекает лицензия", severity: "critical", severity_label: "Критично", message: "Лицензия по ДГ-2026-021 истекла 5 дней назад", contract_id: "contract-4", contract_number: "ДГ-2026-021", university_name: "УрФУ", manager_name: "Ольга Орлова", days: -5 },
    { kind: "no_manager", kind_label: "Нет ответственного", severity: "warning", severity_label: "Внимание", message: "По договору ДГ-2026-033 не назначен ответственный", contract_id: "contract-6", contract_number: "ДГ-2026-033", university_name: "КНИТУ-КАИ", days: 1 },
  ],
  alerts_summary: [{ kind: "stage_stale", label: "Задержка этапа", count: 2 }, { kind: "license_expiring", label: "Истекает лицензия", count: 1 }, { kind: "no_manager", label: "Нет ответственного", count: 2 }],
  charts: [
    { key: "by_status", title: "Договоры по статусам", items: [{ label: "Активные", value: 5 }, { label: "Черновики", value: 3 }] },
    { key: "by_stage", title: "Процессы по этапам", items: [{ label: "Документы", value: 3 }, { label: "Согласование", value: 1 }, { label: "Встреча", value: 1 }] },
  ],
  manager_load: [{ manager_id: "u-petrov", manager_name: "Пётр Петров", contracts: 4, active: 3, blocked: 0 }, { manager_id: "u-ivanova", manager_name: "Мария Иванова", contracts: 2, active: 1, blocked: 1 }, { manager_id: "u-orlova", manager_name: "Ольга Орлова", contracts: 2, active: 1, blocked: 0 }],
  recent: [{ entity_type: "contracts", entity_id: "contract-1", action: "update", user_name: "Пётр Петров", created_at: "2026-09-21T08:30:00Z", summary: "Обновлён статус передачи продукта" }, { entity_type: "workflow_events", entity_id: "event-3", action: "create", user_name: "Пётр Петров", created_at: "2026-09-20T16:45:00Z", summary: "ДГ-2025-047 переведён на этап «Документы»" }, { entity_type: "attachments", entity_id: "file-7", action: "create", user_name: "Мария Иванова", created_at: "2026-09-20T14:20:00Z", summary: "Загружен файл «Протокол встречи.pdf»" }],
};

export const mockReport: Report = {
  title: "Отчёт по взаимодействию с вузами",
  generated_at: "2026-09-21T09:00:00Z",
  filters: {},
  columns: ["university", "program", "contract_number", "contract_status", "stage", "manager"],
  column_titles: { university: "Вуз", program: "ИТ-программа", contract_number: "Номер договора", contract_status: "Статус", stage: "Этап", manager: "Ответственный" },
  totals: { rows: 6, contracts: 6, universities: 4, programs: 4, products: 3 },
  rows: mockContracts.map((contract, index) => ({ contract_id: contract.id, university: contract.university?.short_name ?? "—", direction: contract.programs?.[0]?.program?.direction?.name ?? "—", program: contract.programs?.[0]?.program?.name ?? "—", product: contract.products?.[0]?.product?.name ?? "—", contract_number: contract.number, contract_status: contract.status, stage: ["Документы", "Документы", "Согласование", "Согласование", "Встреча", "Контакт"][index], days_on_stage: [5, 11, 19, 8, 21, 2][index], manager: ["Пётр Петров", "Пётр Петров", "Мария Иванова", "Ольга Орлова", "Пётр Петров", "Мария Иванова"][index], valid_to: contract.valid_to })),
  charts: [{ key: "by_status", title: "Договоры по статусам", measure: "contracts", items: [{ label: "Активные", value: 4 }, { label: "Черновики", value: 2 }] }, { key: "by_stage", title: "Этапы процессов", measure: "contracts", items: [{ label: "Документы", value: 2 }, { label: "Согласование", value: 2 }, { label: "Встреча", value: 1 }, { label: "Контакт", value: 1 }] }],
};
