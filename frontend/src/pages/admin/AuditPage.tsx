/**
 * Журнал изменений: кто, что и когда поменял. Персональные данные замаскированы.
 */
import { keepPreviousData, useQuery } from "@tanstack/react-query";
import { ChevronDown, ChevronRight } from "lucide-react";
import { useMemo, useState } from "react";
import { Link } from "react-router-dom";
import { listAudit } from "../../api/endpoints";
import { useDirections, useLabel, usePrograms, useProducts, useUniversities, useUsers, useVendors } from "../../api/queries";
import type { AuditEntry } from "../../api/types";
import { Pager } from "../../components/DataTable";
import { PeriodPicker, type Period } from "../../components/PeriodPicker";
import { Card, EmptyState, ErrorState, Loading, PageHeader, SelectField, StatusBadge } from "../../components/ui";
import { formatDateTime } from "../../lib/format";
import { usePersistentState } from "../../lib/storage";
import { usePageTitle } from "../../lib/usePageTitle";

export const ENTITY_LABELS: Record<string, string> = {
  workflow_instances: "Взаимодействие",
  interaction_programs: "Программа во взаимодействии",
  interaction_products: "Продукт во взаимодействии",
  interaction_program_products: "Продукт в программе",
  interaction_contacts: "Контакт по взаимодействию",
  contracts: "Договор",
  contract_templates: "Шаблон договора",
  licenses: "Лицензия",
  universities: "Вуз",
  university_contacts: "Контакт вуза",
  it_directions: "ИТ-направление",
  it_programs: "ИТ-программа",
  vendors: "Вендор",
  vendor_contacts: "Контакт вендора",
  it_products: "ИТ-продукт",
  workflow_templates: "Шаблон процесса",
  workflow_versions: "Версия шаблона",
  workflow_stages: "Этап процесса",
  workflow_transitions: "Переход процесса",
  integration_sources: "Источник данных",
  integration_mappings: "Сопоставление записи",
  learning_streams: "Поток обучения",
  enrollments: "Зачисление",
  users: "Пользователь",
  user_university_access: "Доступ к вузу",
  app_settings: "Настройка",
  learning_applications: "Заявка на обучение",
  learners: "Обучающийся",
};

const ACTIONS: Record<string, { label: string; tone: "success" | "info" | "error" }> = {
  create: { label: "Создание", tone: "success" },
  update: { label: "Изменение", tone: "info" },
  delete: { label: "Удаление", tone: "error" },
};

// Ссылки на карточки для сущностей, у которых они есть.
const LINKS: Record<string, (id: string) => string> = {
  workflow_instances: (id) => `/interactions/${id}`,
  universities: (id) => `/universities/${id}`,
};

// Названия полей по-русски, неизвестные остаются как есть.
const FIELD_LABELS: Record<string, string> = {
  name: "Название",
  short_name: "Краткое название",
  full_name: "ФИО",
  description: "Описание",
  city: "Город",
  website: "Сайт",
  number: "Номер",
  title: "Предмет",
  status: "Статус",
  comment: "Комментарий",
  manager_id: "Ответственный",
  university_id: "Вуз",
  program_id: "ИТ-программа",
  product_id: "ИТ-продукт",
  direction_id: "ИТ-направление",
  vendor_id: "Вендор",
  contact_id: "Контакт",
  user_id: "Сотрудник",
  signed_at: "Подписан",
  valid_from: "Действует с",
  valid_to: "Действует по",
  implementation_status: "Статус внедрения",
  transfer_status: "Статус передачи",
  outcome: "Результат",
  closure_reason: "Причина закрытия",
  closure_comment: "Комментарий к закрытию",
  blocked_reason: "Причина блокировки",
  head_id: "Руководитель",
  permissions: "Дополнительные права",
  data_scope_reason: "Основание доступа",
  data_scope_expires_at: "Доступ до",
  reason: "Основание",
  expires_at: "Действует до",
  revoked_at: "Отозван",
  inn: "ИНН",
  requisites: "Реквизиты для договора",
  signatory_name: "Подписант от вуза",
  signatory_position: "Должность подписанта",
  signatory_basis: "Основание полномочий подписанта",
  body: "Текст шаблона",
  updated_by_id: "Кто изменил",
  is_initial: "Стартовый",
  required_documents: "Обязательные документы",
  document_type: "Тип документа",
  is_exception: "Исключение",
  exception_comment: "Комментарий к исключению",
  source: "Источник",
  is_active: "Используется",
  is_primary: "Основной контакт",
  role: "Роль",
  roles: "Роли",
  data_scope: "Область данных",
  email: "Почта",
  phone: "Телефон",
  position: "Должность",
  seats: "Мест",
  sla_days: "Норма, дней",
  is_optional: "Необязательный",
  is_final: "Завершающий",
  value: "Значение",
  key: "Параметр",
};

// Статусы у разных сущностей свои: подпись ищется по таблице записи.
const STATUS_GROUPS: Record<string, string> = {
  implementation_status: "program_status",
  transfer_status: "product_status",
  outcome: "interaction_outcome",
  closure_reason: "closure_reason",
  data_scope: "data_scope",
  document_type: "document_type",
};
const STATUS_BY_ENTITY: Record<string, string> = {
  contracts: "contract_status",
  licenses: "license_status",
  workflow_instances: "interaction_status",
  universities: "university_status",
  workflow_versions: "workflow_version_status",
  integration_mappings: "mapping_status",
};

/** Идентификаторы в журнале показываются именами: кого назначили, какой вуз. */
function useNames(): Record<string, Record<string, string>> {
  const users = useUsers();
  const universities = useUniversities();
  const programs = usePrograms();
  const products = useProducts();
  const directions = useDirections();
  const vendors = useVendors();
  return useMemo(() => {
    const byId = <T extends { id: string }>(items: T[] | undefined, label: (item: T) => string) =>
      Object.fromEntries((items || []).map((item) => [item.id, label(item)]));
    const people = byId(users.data, (item) => item.full_name);
    return {
      manager_id: people,
      user_id: people,
      university_id: byId(universities.data, (item) => item.short_name || item.name),
      program_id: byId(programs.data, (item) => item.name),
      product_id: byId(products.data, (item) => item.name),
      direction_id: byId(directions.data, (item) => item.name),
      vendor_id: byId(vendors.data, (item) => item.name),
    };
  }, [users.data, universities.data, programs.data, products.data, directions.data, vendors.data]);
}

function show(value: unknown): string {
  if (value === null || value === undefined || value === "") return "—";
  if (typeof value === "boolean") return value ? "да" : "нет";
  if (typeof value === "object") return JSON.stringify(value);
  return String(value);
}

function Changes({ entry }: { entry: AuditEntry }) {
  const names = useNames();
  const label = useLabel();
  const before = entry.before_data || {};
  const after = entry.after_data || {};
  const fields = Array.from(new Set([...Object.keys(before), ...Object.keys(after)])).filter(
    (key) => entry.action !== "update" || show(before[key]) !== show(after[key]),
  );
  const value = (field: string, raw: unknown) => {
    const text = show(raw);
    if (typeof raw === "string" && names[field]?.[raw]) return names[field][raw];
    const group = field === "status" ? STATUS_BY_ENTITY[entry.entity_type] : STATUS_GROUPS[field];
    if (typeof raw === "string" && group) return label(group, raw);
    return text;
  };
  if (fields.length === 0) return <p className="muted">Подробностей нет.</p>;
  return (
    <div className="diff">
      <div className="diff__head">Поле</div>
      <div className="diff__head">Было</div>
      <div className="diff__head">Стало</div>
      {fields.map((field) => (
        <div key={field} style={{ display: "contents" }}>
          <div title={field}>{FIELD_LABELS[field] || <span className="mono">{field}</span>}</div>
          <div className="diff__old">{value(field, before[field])}</div>
          <div className="diff__new">{value(field, after[field])}</div>
        </div>
      ))}
    </div>
  );
}

export function AuditEntries({ entries, compact }: { entries: AuditEntry[]; compact?: boolean }) {
  const [open, setOpen] = useState<string | null>(null);
  const names = useNames();
  if (entries.length === 0) return <EmptyState title="Изменений нет" />;
  return (
    <div className="list">
      {entries.map((entry) => {
        const action = ACTIONS[entry.action] || { label: entry.action, tone: "info" as const };
        const expanded = open === entry.id;
        const link = entry.entity_id && LINKS[entry.entity_type]?.(entry.entity_id);
        return (
          <div key={entry.id} className="list-item" style={{ flexDirection: "column", alignItems: "stretch", gap: 8 }}>
            <button
              type="button"
              className="row"
              style={{ border: 0, background: "none", padding: 0, textAlign: "left", flexWrap: "nowrap" }}
              aria-expanded={expanded}
              onClick={() => setOpen(expanded ? null : entry.id)}
            >
              {expanded ? <ChevronDown size={16} /> : <ChevronRight size={16} />}
              <span className="list-item__main">
                <strong style={{ whiteSpace: "normal" }}>
                  {ENTITY_LABELS[entry.entity_type] || entry.entity_type}
                  {!compact && entry.entity_id ? (
                    <span className="muted">
                      {" · "}
                      {(entry.entity_type === "universities" && names.university_id[entry.entity_id]) || (
                        <span className="mono">{entry.entity_id.slice(0, 8)}</span>
                      )}
                    </span>
                  ) : null}
                </strong>
                <small>
                  {entry.user_name || "Система"} · {formatDateTime(entry.created_at)}
                </small>
              </span>
              <StatusBadge tone={action.tone}>{action.label}</StatusBadge>
            </button>
            {expanded && (
              <div className="stack-s">
                <Changes entry={entry} />
                {link && !compact && <Link to={link}>Открыть карточку</Link>}
              </div>
            )}
          </div>
        );
      })}
    </div>
  );
}

const LIMIT = 50;

export default function AuditPage() {
  const users = useUsers();
  const [filters, setFilters] = usePersistentState("audit.filters", {
    entity_type: "",
    action: "",
    user_id: "",
    period: { date_from: "", date_to: "" } as Period,
  });
  const [offset, setOffset] = useState(0);
  usePageTitle("Журнал изменений");
  const query = {
    entity_type: filters.entity_type || undefined,
    action: filters.action || undefined,
    user_id: filters.user_id || undefined,
    date_from: filters.period.date_from || undefined,
    date_to: filters.period.date_to || undefined,
    limit: LIMIT,
    offset,
  };
  const audit = useQuery({ queryKey: ["audit", query], queryFn: () => listAudit(query), placeholderData: keepPreviousData });
  const update = (patch: Partial<typeof filters>) => {
    setFilters((current) => ({ ...current, ...patch }));
    setOffset(0);
  };

  return (
    <div className="page">
      <PageHeader title="Журнал изменений" />
      <div className="toolbar">
        <SelectField
          label="Что менялось"
          value={filters.entity_type}
          onChange={(value) => update({ entity_type: value })}
          placeholder="Всё"
          options={Object.entries(ENTITY_LABELS).map(([value, label]) => ({ value, label }))}
        />
        <SelectField
          label="Действие"
          value={filters.action}
          onChange={(value) => update({ action: value })}
          placeholder="Любое"
          options={Object.entries(ACTIONS).map(([value, item]) => ({ value, label: item.label }))}
        />
        <SelectField
          label="Кто"
          value={filters.user_id}
          onChange={(value) => update({ user_id: value })}
          placeholder="Все"
          options={(users.data || []).map((user) => ({ value: user.id, label: user.full_name }))}
        />
        <PeriodPicker value={filters.period} onChange={(period) => update({ period })} />
      </div>
      <Card flush>
        {audit.isPending ? (
          <Loading />
        ) : audit.isError ? (
          <ErrorState error={audit.error} onRetry={() => void audit.refetch()} />
        ) : (
          <div className={audit.isFetching && audit.isPlaceholderData ? "is-refreshing" : undefined}>
            <AuditEntries entries={audit.data.items} />
            <Pager total={audit.data.total} limit={LIMIT} offset={offset} onChange={setOffset} />
          </div>
        )}
      </Card>
    </div>
  );
}
