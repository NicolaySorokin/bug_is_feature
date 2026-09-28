/**
 * Реестр взаимодействий. Статус, этап и срок этапа идут отдельными колонками, договора может
 * ещё не быть. Фильтры хранятся в адресе и запоминаются.
 */
import { keepPreviousData, useQuery } from "@tanstack/react-query";
import { ChevronDown, ChevronUp, Handshake, Plus, RotateCcw, SlidersHorizontal } from "lucide-react";
import { useEffect, useState } from "react";
import { Link, useNavigate, useSearchParams } from "react-router-dom";
import { listInteractions } from "../api/endpoints";
import {
  keys,
  useDirectory,
  useDirections,
  useLabel,
  usePrograms,
  useProducts,
  useStageNames,
  useUniversities,
} from "../api/queries";
import type { InteractionListItem } from "../api/types";
import { useSession } from "../auth/session";
import { DataTable, Pager, type Column } from "../components/DataTable";
import { MultiSelect } from "../components/MultiSelect";
import { Button, Card, EmptyState, ErrorState, Loading, PageHeader, SearchInput, SelectField, Tag } from "../components/ui";
import { InteractionFormModal } from "../features/interaction/InteractionForm";
import { ContractCell, interactionTitle, SlaChip, StageCell, StatusCell, UniversityName } from "../features/interaction/parts";
import { formatDateTime } from "../lib/format";
import { INTERACTION_STATUSES } from "../lib/labels";
import { usePageTitle } from "../lib/usePageTitle";
import { useUrlFilters } from "../lib/useUrlFilters";

const LIMIT = 25;
const FILTER_KEYS = [
  "search",
  "status",
  "outcome",
  "source",
  "university_id",
  "manager_id",
  "unassigned",
  "has_contract",
  "contract_status",
  "direction_id",
  "program_id",
  "product_id",
  "stage",
  "overdue",
  "order",
  "offset",
];

// Редкие фильтры спрятаны под «Ещё фильтры», чтобы реестр начинался с таблицы.
const SECONDARY_KEYS = [
  "outcome",
  "stage",
  "has_contract",
  "contract_status",
  "source",
  "direction_id",
  "program_id",
  "product_id",
];

const ORDERS = [
  { value: "updated", label: "Недавно изменённые" },
  { value: "attention", label: "Сначала требующие внимания" },
  { value: "created", label: "Сначала новые" },
  { value: "university", label: "По вузу" },
];

export default function InteractionsPage() {
  const { can, scope } = useSession();
  const label = useLabel();
  const navigate = useNavigate();
  const [params, setParams] = useSearchParams();
  const [filters, update, reset] = useUrlFilters("interactions", FILTER_KEYS);
  const [search, setSearch] = useState(filters.search || "");
  const [creating, setCreating] = useState(params.get("create") === "1");
  const [filtersOpen, setFiltersOpen] = useState(false);
  // null: дополнительные фильтры раскрыты, если среди них есть заданные.
  const [moreOpen, setMoreOpen] = useState<boolean | null>(null);
  usePageTitle("Взаимодействия");

  const universities = useUniversities();
  const directory = useDirectory();
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

  const statuses = (filters.status || "").split(",").filter(Boolean);
  const offset = Number(filters.offset || 0);
  const query = {
    ...filters,
    status: statuses,
    limit: LIMIT,
    offset,
    unassigned: filters.unassigned === "true" ? true : undefined,
    overdue: filters.overdue === "true" ? true : undefined,
    has_contract: filters.has_contract || undefined,
  };
  const interactions = useQuery({
    queryKey: [...keys.interactions, query],
    queryFn: () => listInteractions(query),
    placeholderData: keepPreviousData,
  });

  const active = FILTER_KEYS.filter((key) => !["order", "offset", "search"].includes(key) && filters[key]).length;
  const secondaryKeys = scope === "own" ? SECONDARY_KEYS : [...SECONDARY_KEYS, "university_id"];
  const secondaryActive = secondaryKeys.filter((key) => filters[key]).length;
  const showMore = moreOpen ?? (secondaryActive > 0 || Boolean(filters.order));
  const canCreate = can("create_interaction");

  const columns: Column<InteractionListItem>[] = [
    {
      key: "university",
      title: "Вуз и взаимодействие",
      primary: true,
      render: (row) => (
        <div className="cell-title">
          <strong>
            <UniversityName university={row.university} />
          </strong>
          <Link to={`/interactions/${row.id}`} className="muted-link">
            <small>{interactionTitle(row)}</small>
          </Link>
        </div>
      ),
    },
    {
      key: "status",
      title: "Статус",
      render: (row) => (
        <div className="cell-title">
          <StatusCell status={row.status} outcome={row.outcome} />
          {row.status === "blocked" && row.blocked_reason && <small title={row.blocked_reason}>{row.blocked_reason}</small>}
          {row.closure_reason && <small>{label("closure_reason", row.closure_reason)}</small>}
        </div>
      ),
    },
    {
      key: "stage",
      title: "Этап и следующее действие",
      render: (row) => <StageCell stageName={row.stage?.stage_name} nextActions={row.stage?.next_actions} status={row.status} />,
    },
    { key: "sla", title: "Срок этапа", render: (row) => <SlaChip sla={row.stage?.sla} status={row.status} /> },
    // В области «свои» ответственный всегда сам сотрудник, колонка ничего не добавляет.
    ...(scope === "own"
      ? []
      : [
          {
            key: "manager",
            title: "Ответственный",
            render: (row: InteractionListItem) => row.manager?.full_name || <Tag tone="warn">Не назначен</Tag>,
          },
        ]),
    { key: "contract", title: "Договор", render: (row) => <ContractCell contract={row.contract} /> },
    {
      key: "updated",
      title: "Изменено",
      className: "nowrap",
      render: (row) => <span className="muted">{formatDateTime(row.updated_at || row.created_at)}</span>,
    },
  ];

  const managerOptions = (directory.data || []).map((user) => ({ value: user.id, label: user.full_name }));
  const title = scope === "own" ? "Мои взаимодействия" : "Взаимодействия";
  const universityFilter = (
    <SelectField
      label="Вуз"
      value={filters.university_id || ""}
      onChange={(value) => update({ university_id: value })}
      placeholder="Все"
      options={(universities.data || []).map((item) => ({ value: item.id, label: item.short_name || item.name }))}
    />
  );

  return (
    <div className="page">
      <PageHeader
        title={title}
        description={
          scope === "team"
            ? "Взаимодействия вашей команды и те, что ждут назначения ответственного."
            : scope === "all"
              ? "Все взаимодействия с вузами."
              : undefined
        }
        actions={
          canCreate && (
            <Button icon={Plus} onClick={() => setCreating(true)}>
              Новое взаимодействие
            </Button>
          )
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
          <SearchInput value={search} onChange={setSearch} placeholder="Название, вуз или номер договора" />
        </div>
        <MultiSelect
          label="Статус"
          value={statuses}
          onChange={(value) => update({ status: value.join(",") })}
          options={INTERACTION_STATUSES.map((value) => ({ value, label: label("interaction_status", value) }))}
        />
        <SelectField
          label="Срок этапа"
          value={filters.overdue || ""}
          onChange={(value) => update({ overdue: value })}
          placeholder="Любой"
          options={[{ value: "true", label: "Только просроченные" }]}
        />
        {scope === "own" ? (
          universityFilter
        ) : (
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
      </div>
      {showMore && (
        <div className="toolbar toolbar--secondary" id="interaction-more-filters">
          {scope !== "own" && universityFilter}
          <SelectField
            label="Результат"
            value={filters.outcome || ""}
            onChange={(value) => update({ outcome: value })}
            placeholder="Любой"
            options={(["successful", "partial", "unsuccessful"] as const).map((value) => ({
              value,
              label: label("interaction_outcome", value),
            }))}
          />
          <SelectField
            label="Этап"
            value={filters.stage || ""}
            onChange={(value) => update({ stage: value })}
            placeholder="Любой"
            options={(stages.data || []).map((name) => ({ value: name, label: name }))}
          />
          <SelectField
            label="Договор"
            value={filters.has_contract || ""}
            onChange={(value) => update({ has_contract: value })}
            placeholder="Не важно"
            options={[
              { value: "true", label: "Есть договор" },
              { value: "false", label: "Договора нет" },
            ]}
          />
          <SelectField
            label="Статус договора"
            value={filters.contract_status || ""}
            onChange={(value) => update({ contract_status: value })}
            placeholder="Любой"
            options={(["draft", "active", "suspended", "closed", "cancelled"] as const).map((value) => ({
              value,
              label: label("contract_status", value),
            }))}
          />
          <SelectField
            label="Источник"
            value={filters.source || ""}
            onChange={(value) => update({ source: value })}
            placeholder="Любой"
            options={(["manual", "site", "import", "lms"] as const).map((value) => ({
              value,
              label: label("interaction_source", value),
            }))}
          />
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
            value={filters.order || "updated"}
            onChange={(value) => update({ order: value === "updated" ? "" : value })}
            options={ORDERS}
          />
        </div>
      )}
      <div className="filters-summary">
        <button
          type="button"
          className="link-btn"
          aria-expanded={showMore}
          aria-controls="interaction-more-filters"
          onClick={() => setMoreOpen(!showMore)}
        >
          {showMore ? <ChevronUp size={14} /> : <ChevronDown size={14} />}
          {showMore ? "Меньше фильтров" : `Ещё фильтры${secondaryActive ? ` (${secondaryActive})` : ""}`}
        </button>
        {(active > 0 || filters.search) && (
          <>
            <span aria-hidden="true">·</span>
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
          </>
        )}
      </div>

      <Card flush>
        {interactions.isPending ? (
          <Loading />
        ) : interactions.isError ? (
          <ErrorState error={interactions.error} onRetry={() => void interactions.refetch()} />
        ) : (
          <>
            <DataTable
              caption="Реестр взаимодействий"
              columns={columns}
              rows={interactions.data.items}
              rowKey={(row) => row.id}
              onRowClick={(row) => navigate(`/interactions/${row.id}`)}
              refreshing={interactions.isFetching && interactions.isPlaceholderData}
              empty={
                <EmptyState
                  icon={Handshake}
                  title={active || filters.search ? "Ничего не найдено" : "Взаимодействий пока нет"}
                  action={
                    active || filters.search ? (
                      <Button variant="secondary" onClick={() => (setSearch(""), reset())}>
                        Сбросить фильтры
                      </Button>
                    ) : canCreate ? (
                      <Button icon={Plus} onClick={() => setCreating(true)}>
                        Новое взаимодействие
                      </Button>
                    ) : undefined
                  }
                >
                  {active || filters.search
                    ? "Измените условия поиска или сбросьте фильтры."
                    : "Заведите первое взаимодействие с вузом: договор появится позже, в ходе работы."}
                </EmptyState>
              }
            />
            <Pager
              total={interactions.data.total}
              limit={LIMIT}
              offset={offset}
              onChange={(next) => update({ offset: next ? String(next) : "" })}
              forms={["взаимодействие", "взаимодействия", "взаимодействий"]}
            />
          </>
        )}
      </Card>

      {canCreate && <InteractionFormModal open={creating} onClose={() => setCreating(false)} />}
    </div>
  );
}
