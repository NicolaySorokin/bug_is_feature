/**
 * Реестр договоров.
 *
 * Фильтры - в адресе страницы и запоминаются между сеансами. В строке
 * виден текущий этап процесса и сколько дней договор на нём стоит.
 */
import { keepPreviousData, useQuery } from "@tanstack/react-query";
import { FileText, Plus, RotateCcw, SlidersHorizontal } from "lucide-react";
import { useEffect, useState } from "react";
import { Link, useNavigate, useSearchParams } from "react-router-dom";
import { listContracts } from "../api/endpoints";
import {
  keys,
  useDirections,
  useLabel,
  usePrograms,
  useProducts,
  useStageNames,
  useUniversities,
  useUsers,
} from "../api/queries";
import type { ContractListItem } from "../api/types";
import { useSession } from "../auth/session";
import { DataTable, Pager, type Column } from "../components/DataTable";
import {
  Button,
  Card,
  EmptyState,
  ErrorState,
  Loading,
  PageHeader,
  SearchInput,
  SelectField,
  StatusBadge,
  Tag,
} from "../components/ui";
import { countLabel, DAYS, daysUntil, formatDate, formatDateTime } from "../lib/format";
import { CONTRACT_STATUS_TONE, WORKFLOW_TONE } from "../lib/labels";
import { usePageTitle } from "../lib/usePageTitle";
import { useUrlFilters } from "../lib/useUrlFilters";
import { ContractFormModal } from "./contract/ContractForm";

const LIMIT = 25;
const FILTER_KEYS = [
  "search",
  "status",
  "process",
  "university_id",
  "manager_id",
  "unassigned",
  "direction_id",
  "program_id",
  "product_id",
  "stage",
  "order",
  "offset",
];

const ORDERS = [
  { value: "created", label: "Сначала новые" },
  { value: "updated", label: "Недавно изменённые" },
  { value: "valid_to", label: "Срок заканчивается раньше" },
  { value: "university", label: "По вузу" },
  { value: "number", label: "По номеру" },
];

export function StageCell({ row }: { row: Pick<ContractListItem, "process"> }) {
  const label = useLabel();
  const process = row.process;
  if (!process) return <span className="muted">Процесс не запущен</span>;
  const overdue =
    process.sla_days &&
    process.days_on_stage !== null &&
    process.days_on_stage !== undefined &&
    process.days_on_stage > process.sla_days;
  return (
    <div className="cell-title">
      <span>{process.stage_name || "—"}</span>
      <small>
        {process.status !== "in_progress" ? (
          <StatusBadge tone={WORKFLOW_TONE[process.status]}>{label("workflow_status", process.status)}</StatusBadge>
        ) : process.days_on_stage !== null && process.days_on_stage !== undefined ? (
          <span className={overdue ? "field__error" : undefined}>
            {countLabel(process.days_on_stage, DAYS)} на этапе{process.sla_days ? ` · норма ${process.sla_days}` : ""}
          </span>
        ) : null}
      </small>
    </div>
  );
}

export function ValidTo({ value, status }: { value?: string | null; status?: string }) {
  if (!value) return <span className="muted">—</span>;
  const left = daysUntil(value);
  const watch = status === "active" && left !== null;
  return (
    <div className="cell-title">
      <span className="nowrap">{formatDate(value)}</span>
      {watch && left! < 0 && <small className="field__error">истёк</small>}
      {watch && left! >= 0 && left! <= 60 && <small className="field__error">осталось {countLabel(left!, DAYS)}</small>}
    </div>
  );
}

export default function ContractsPage() {
  const { me } = useSession();
  const label = useLabel();
  const navigate = useNavigate();
  const [params, setParams] = useSearchParams();
  const [filters, update, reset] = useUrlFilters("contracts", FILTER_KEYS);
  const [search, setSearch] = useState(filters.search || "");
  const [creating, setCreating] = useState(params.get("create") === "1");
  const [filtersOpen, setFiltersOpen] = useState(false);
  usePageTitle("Договоры");

  const universities = useUniversities();
  const users = useUsers();
  const directions = useDirections();
  const programs = usePrograms();
  const products = useProducts();
  const stages = useStageNames();

  // Поиск применяется, когда пользователь перестал печатать.
  useEffect(() => {
    const timer = window.setTimeout(() => {
      if ((filters.search || "") !== search.trim()) update({ search: search.trim() });
    }, 350);
    return () => window.clearTimeout(timer);
  }, [search, filters.search, update]);

  useEffect(() => {
    if (params.get("create") === "1") {
      setCreating(true);
      const next = new URLSearchParams(params);
      next.delete("create");
      setParams(next, { replace: true });
    }
  }, [params, setParams]);

  const offset = Number(filters.offset || 0);
  const query = { ...filters, limit: LIMIT, offset, unassigned: filters.unassigned === "true" ? true : undefined };
  const contracts = useQuery({
    queryKey: [...keys.contracts, query],
    queryFn: () => listContracts(query),
    placeholderData: keepPreviousData,
  });

  const active = FILTER_KEYS.filter((key) => !["order", "offset", "search"].includes(key) && filters[key]).length;

  const columns: Column<ContractListItem>[] = [
    {
      key: "number",
      title: "Договор",
      primary: true,
      render: (row) => (
        <div className="cell-title">
          <Link to={`/contracts/${row.id}`}>
            <strong>{row.number}</strong>
          </Link>
          <small>{row.title || "Без предмета"}</small>
        </div>
      ),
    },
    {
      key: "university",
      title: "Вуз",
      render: (row) =>
        row.university ? (
          <Link to={`/universities/${row.university_id}`} title={row.university.name}>
            {row.university.short_name || row.university.name}
          </Link>
        ) : (
          "—"
        ),
    },
    {
      key: "manager",
      title: "Ответственный",
      render: (row) => row.manager?.full_name || <Tag tone="warn">Не назначен</Tag>,
    },
    {
      key: "status",
      title: "Статус",
      render: (row) => <StatusBadge tone={CONTRACT_STATUS_TONE[row.status]}>{label("contract_status", row.status)}</StatusBadge>,
    },
    { key: "stage", title: "Этап процесса", render: (row) => <StageCell row={row} /> },
    { key: "valid_to", title: "Действует по", render: (row) => <ValidTo value={row.valid_to} status={row.status} /> },
    {
      key: "updated",
      title: "Изменён",
      className: "nowrap",
      render: (row) => <span className="muted">{formatDateTime(row.updated_at || row.created_at)}</span>,
    },
  ];

  const managerOptions = (users.data || [])
    .filter((user) => (user.roles || []).includes("manager"))
    .map((user) => ({ value: user.id, label: user.id === me.id ? `${user.full_name} (я)` : user.full_name }));

  return (
    <div className="page">
      <PageHeader
        title="Договоры"
        description={
          me.sees_all_contracts
            ? "Все договоры ИТ Школы с вузами: статус, этап рабочего процесса, сроки."
            : "Договоры ваших вузов: статус, этап рабочего процесса, сроки."
        }
        actions={
          <Button icon={Plus} onClick={() => setCreating(true)}>
            Новый договор
          </Button>
        }
      />

      <div className="filters-toggle">
        <Button variant="outline" size="s" icon={SlidersHorizontal} onClick={() => setFiltersOpen((value) => !value)}>
          {filtersOpen ? "Скрыть фильтры" : `Фильтры${active ? ` (${active})` : ""}`}
        </Button>
      </div>
      <div className={`toolbar toolbar--collapsible ${filtersOpen ? "is-open" : ""}`}>
        <div className="field field--grow">
          <span className="field__label">Поиск</span>
          <SearchInput value={search} onChange={setSearch} placeholder="Номер, предмет или вуз" />
        </div>
        <SelectField
          label="Статус договора"
          value={filters.status || ""}
          onChange={(value) => update({ status: value })}
          placeholder="Все"
          options={["draft", "active", "suspended", "closed"].map((value) => ({ value, label: label("contract_status", value) }))}
        />
        <SelectField
          label="Процесс"
          value={filters.process || ""}
          onChange={(value) => update({ process: value })}
          placeholder="Любой"
          options={[
            { value: "in_progress", label: "В работе" },
            { value: "blocked", label: "Заблокирован" },
            { value: "completed", label: "Завершён" },
            { value: "none", label: "Не запущен" },
          ]}
        />
        <SelectField
          label="Этап"
          value={filters.stage || ""}
          onChange={(value) => update({ stage: value })}
          placeholder="Любой"
          options={(stages.data || []).map((name) => ({ value: name, label: name }))}
        />
        <SelectField
          label="Вуз"
          value={filters.university_id || ""}
          onChange={(value) => update({ university_id: value })}
          placeholder="Все"
          options={(universities.data || []).map((item) => ({ value: item.id, label: item.short_name || item.name }))}
        />
        {me.sees_all_contracts && (
          <SelectField
            label="Ответственный"
            value={filters.unassigned === "true" ? "__none" : filters.manager_id || ""}
            onChange={(value) =>
              value === "__none" ? update({ unassigned: "true", manager_id: "" }) : update({ manager_id: value, unassigned: "" })
            }
            placeholder="Все"
            options={[{ value: "__none", label: "Не назначен" }, ...managerOptions]}
          />
        )}
        <SelectField
          label="ИТ-направление"
          value={filters.direction_id || ""}
          onChange={(value) => update({ direction_id: value })}
          placeholder="Все"
          options={(directions.data || []).map((item) => ({ value: item.id, label: item.name }))}
        />
        <SelectField
          label="ИТ-программа"
          value={filters.program_id || ""}
          onChange={(value) => update({ program_id: value })}
          placeholder="Все"
          options={(programs.data || []).map((item) => ({ value: item.id, label: item.name }))}
        />
        <SelectField
          label="ИТ-продукт"
          value={filters.product_id || ""}
          onChange={(value) => update({ product_id: value })}
          placeholder="Все"
          options={(products.data || []).map((item) => ({ value: item.id, label: item.name }))}
        />
        <SelectField
          label="Сортировка"
          value={filters.order || "created"}
          onChange={(value) => update({ order: value === "created" ? "" : value })}
          options={ORDERS}
        />
      </div>
      {(active > 0 || filters.search) && (
        <div className="filters-summary">
          <span>Фильтров: {active + (filters.search ? 1 : 0)}</span>
          <button
            type="button"
            className="link-btn"
            onClick={() => {
              setSearch("");
              reset();
            }}
          >
            <RotateCcw size={13} /> Сбросить
          </button>
        </div>
      )}

      <Card flush>
        {contracts.isPending ? (
          <Loading />
        ) : contracts.isError ? (
          <ErrorState error={contracts.error} onRetry={() => void contracts.refetch()} />
        ) : (
          <>
            <DataTable
              caption="Реестр договоров"
              columns={columns}
              rows={contracts.data.items}
              rowKey={(row) => row.id}
              onRowClick={(row) => navigate(`/contracts/${row.id}`)}
              refreshing={contracts.isFetching && contracts.isPlaceholderData}
              empty={
                <EmptyState
                  icon={FileText}
                  title={active || filters.search ? "Ничего не найдено" : "Договоров пока нет"}
                  action={
                    active || filters.search ? (
                      <Button variant="secondary" onClick={() => (setSearch(""), reset())}>
                        Сбросить фильтры
                      </Button>
                    ) : (
                      <Button icon={Plus} onClick={() => setCreating(true)}>
                        Новый договор
                      </Button>
                    )
                  }
                >
                  {active || filters.search
                    ? "Измените условия поиска или сбросьте фильтры."
                    : "Заведите первый договор с вузом."}
                </EmptyState>
              }
            />
            <Pager
              total={contracts.data.total}
              limit={LIMIT}
              offset={offset}
              onChange={(next) => update({ offset: next ? String(next) : "" })}
              forms={["договор", "договора", "договоров"]}
            />
          </>
        )}
      </Card>

      <ContractFormModal open={creating} onClose={() => setCreating(false)} />
    </div>
  );
}
