/**
 * Журнал изменений: кто, что и когда поменял.
 *
 * Изменения прав и доступа сотрудников, справочников, договоров и
 * процессов (приказ ФСТЭК № 117: регистрация событий безопасности).
 * Персональные данные в журнале замаскированы.
 */
import { keepPreviousData, useQuery } from "@tanstack/react-query";
import { ChevronDown, ChevronRight } from "lucide-react";
import { useState } from "react";
import { Link } from "react-router-dom";
import { listAudit } from "../../api/endpoints";
import { useUsers } from "../../api/queries";
import type { AuditEntry } from "../../api/types";
import { Pager } from "../../components/DataTable";
import { PeriodPicker, type Period } from "../../components/PeriodPicker";
import { Card, EmptyState, ErrorState, Loading, PageHeader, SelectField, StatusBadge } from "../../components/ui";
import { formatDateTime } from "../../lib/format";
import { usePersistentState } from "../../lib/storage";
import { usePageTitle } from "../../lib/usePageTitle";

export const ENTITY_LABELS: Record<string, string> = {
  contracts: "Договор",
  contract_programs: "Программа в договоре",
  contract_products: "Продукт в договоре",
  contract_contacts: "Контакт по договору",
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
  contracts: (id) => `/contracts/${id}`,
  universities: (id) => `/universities/${id}`,
};

function show(value: unknown): string {
  if (value === null || value === undefined || value === "") return "—";
  if (typeof value === "boolean") return value ? "да" : "нет";
  if (typeof value === "object") return JSON.stringify(value);
  return String(value);
}

function Changes({ entry }: { entry: AuditEntry }) {
  const before = entry.before_data || {};
  const after = entry.after_data || {};
  const fields = Array.from(new Set([...Object.keys(before), ...Object.keys(after)])).filter(
    (key) => entry.action !== "update" || show(before[key]) !== show(after[key]),
  );
  if (fields.length === 0) return <p className="muted">Подробностей нет.</p>;
  return (
    <div className="diff">
      <div className="diff__head">Поле</div>
      <div className="diff__head">Было</div>
      <div className="diff__head">Стало</div>
      {fields.map((field) => (
        <div key={field} style={{ display: "contents" }}>
          <div className="mono">{field}</div>
          <div className="diff__old">{show(before[field])}</div>
          <div className="diff__new">{show(after[field])}</div>
        </div>
      ))}
    </div>
  );
}

export function AuditEntries({ entries, compact }: { entries: AuditEntry[]; compact?: boolean }) {
  const [open, setOpen] = useState<string | null>(null);
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
                  {!compact && entry.entity_id ? <span className="muted mono"> · {entry.entity_id.slice(0, 8)}</span> : null}
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
      <PageHeader
        title="Журнал изменений"
        description="Кто и когда менял данные, права и настройки. Персональные данные в журнале замаскированы. Нажмите на запись, чтобы увидеть изменения."
      />
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
