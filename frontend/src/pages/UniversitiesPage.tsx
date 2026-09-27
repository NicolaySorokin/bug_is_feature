/**
 * Вузы.
 *
 * У записи единый жизненный цикл: «На проверке» (заведён импортом, обменом
 * с сайтом или менеджером) -> «Подтверждён» -> «В архиве». Руководитель
 * подтверждает новые вузы и объединяет дубли - список возможных дублей
 * показан отдельно. В списке - краткое название, полное - в подсказке.
 */
import { keepPreviousData, useQuery } from "@tanstack/react-query";
import { Building2, CopyCheck, Plus, RotateCcw } from "lucide-react";
import { useEffect, useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import { listDuplicates, listUniversities } from "../api/endpoints";
import { keys, useDirectory, useLabel } from "../api/queries";
import type { UniversityListItem } from "../api/types";
import { useSession } from "../auth/session";
import { DataTable, Pager, type Column } from "../components/DataTable";
import {
  Button,
  Card,
  EmptyState,
  ErrorState,
  Hint,
  KpiRow,
  Loading,
  PageHeader,
  SearchInput,
  SelectField,
  StatusBadge,
  Tag,
} from "../components/ui";
import { formatNumber } from "../lib/format";
import { UNIVERSITY_TONE } from "../lib/labels";
import { usePageTitle } from "../lib/usePageTitle";
import { useUrlFilters } from "../lib/useUrlFilters";
import { UniversityFormModal } from "./UniversityForm";

const LIMIT = 25;
const KEYS = ["search", "manager_id", "unassigned", "status", "offset"];

export default function UniversitiesPage() {
  const { can, me, roles } = useSession();
  const label = useLabel();
  const navigate = useNavigate();
  const directory = useDirectory();
  const [filters, update, reset] = useUrlFilters("universities", KEYS);
  const [search, setSearch] = useState(filters.search || "");
  const [creating, setCreating] = useState(false);
  const manages = can("manage_universities");
  usePageTitle("Вузы");

  useEffect(() => {
    const timer = window.setTimeout(() => {
      if ((filters.search || "") !== search.trim()) update({ search: search.trim() });
    }, 350);
    return () => window.clearTimeout(timer);
  }, [search, filters.search, update]);

  const offset = Number(filters.offset || 0);
  const query = {
    search: filters.search,
    manager_id: filters.manager_id,
    unassigned: filters.unassigned === "true" ? true : undefined,
    status: filters.status ? [filters.status] : undefined,
    limit: LIMIT,
    offset,
  };
  const universities = useQuery({
    queryKey: [...keys.universities, "page", query],
    queryFn: () => listUniversities(query),
    placeholderData: keepPreviousData,
  });
  const pending = useQuery({
    queryKey: [...keys.universities, "pending-count"],
    queryFn: () => listUniversities({ status: ["pending"], limit: 1 }),
    enabled: manages,
  });
  const duplicates = useQuery({ queryKey: ["university-duplicates"], queryFn: listDuplicates, enabled: manages });

  const columns: Column<UniversityListItem>[] = [
    {
      key: "name",
      title: "Вуз",
      primary: true,
      render: (row) => (
        <div className="cell-title">
          <Link to={`/universities/${row.id}`} title={row.name}>
            <strong>{row.short_name || row.name}</strong>
          </Link>
          {row.short_name && <small>{row.name}</small>}
        </div>
      ),
    },
    { key: "city", title: "Город", render: (row) => row.city || "—" },
    {
      key: "manager",
      title: "Менеджер по умолчанию",
      render: (row) => row.manager?.full_name || <Tag tone="warn">Не назначен</Tag>,
    },
    {
      key: "interactions",
      title: "Взаимодействия",
      className: "col-num",
      render: (row) => {
        if (row.in_scope === false) {
          return (
            <Hint
              content="Вуз вне вашей области данных - его взаимодействия вам не видны."
              label="Взаимодействия не показываются: вуз вне вашей области данных"
            >
              <span className="muted">—</span>
            </Hint>
          );
        }
        const active = row.active_interactions_count || 0;
        const total = row.interactions_count || 0;
        const summary = `Активных ${formatNumber(active)} из ${formatNumber(total)}`;
        return (
          <Hint title="Взаимодействия" content={summary} label={summary}>
            <span className="num">
              {formatNumber(active)} / {formatNumber(total)}
            </span>
          </Hint>
        );
      },
    },
    {
      key: "status",
      title: "Статус",
      render: (row) => <StatusBadge tone={UNIVERSITY_TONE[row.status]}>{label("university_status", row.status)}</StatusBadge>,
    },
  ];

  const hasFilters = Boolean(filters.manager_id || filters.unassigned || filters.status || filters.search);
  const pendingCount = pending.data?.total || 0;
  const duplicateCount = duplicates.data?.length || 0;

  return (
    <div className="page">
      <PageHeader
        title="Вузы"
        description={
          manages
            ? "Подтверждайте новые вузы и объединяйте дубли: у каждого вуза одна запись и один путь создания."
            : "Вузы вашей работы. Новый вуз можно предложить - его проверит руководитель."
        }
        actions={
          (manages || can("propose_university")) && (
            <Button icon={Plus} onClick={() => setCreating(true)}>
              {manages ? "Добавить вуз" : "Предложить вуз"}
            </Button>
          )
        }
      />
      {manages && (pendingCount > 0 || duplicateCount > 0) && (
        <KpiRow style={{ marginBottom: 16 }}>
          {pendingCount > 0 && (
            <button type="button" className="kpi kpi--alert" onClick={() => update({ status: "pending", offset: "" })}>
              <span className="kpi__label">
                <Building2 size={16} /> Ждут проверки
              </span>
              <span className="kpi__value">{formatNumber(pendingCount)}</span>
              <span className="kpi__detail">подтвердите вуз или объедините с существующим</span>
            </button>
          )}
          {duplicateCount > 0 && (
            <div className="kpi">
              <span className="kpi__label">
                <CopyCheck size={16} /> Возможные дубли
              </span>
              <span className="kpi__value">{formatNumber(duplicateCount)}</span>
              <span className="kpi__detail">
                {(duplicates.data || []).slice(0, 2).map((item, index) => (
                  <span key={index} style={{ display: "block" }}>
                    <Link to={`/universities/${item.second.id}`}>{item.second.short_name || item.second.name}</Link> и{" "}
                    <Link to={`/universities/${item.first.id}`}>{item.first.short_name || item.first.name}</Link>: {item.reason}
                  </span>
                ))}
              </span>
            </div>
          )}
        </KpiRow>
      )}
      <div className="toolbar">
        <div className="field field--grow">
          <span className="field__label">Поиск</span>
          <SearchInput value={search} onChange={setSearch} placeholder="Название, сокращение, город или ИНН" />
        </div>
        <SelectField
          label="Менеджер по умолчанию"
          value={filters.unassigned === "true" ? "__none" : filters.manager_id || ""}
          onChange={(value) =>
            value === "__none" ? update({ unassigned: "true", manager_id: "" }) : update({ manager_id: value, unassigned: "" })
          }
          placeholder="Все"
          options={[
            ...(roles.includes("manager") ? [{ value: me.id, label: "Мои вузы" }] : []),
            { value: "__none", label: "Не назначен" },
            ...(directory.data || [])
              .filter((item) => item.id !== me.id)
              .map((item) => ({ value: item.id, label: item.full_name })),
          ]}
        />
        <SelectField
          label="Статус"
          value={filters.status || ""}
          onChange={(value) => update({ status: value })}
          placeholder="Все, кроме архива"
          options={(["pending", "confirmed", "archived"] as const).map((value) => ({
            value,
            label: label("university_status", value),
          }))}
        />
        {hasFilters && (
          <div className="toolbar__actions">
            <Button variant="ghost" icon={RotateCcw} onClick={() => (setSearch(""), reset())}>
              Сбросить
            </Button>
          </div>
        )}
      </div>
      <Card flush>
        {universities.isPending ? (
          <Loading />
        ) : universities.isError ? (
          <ErrorState error={universities.error} onRetry={() => void universities.refetch()} />
        ) : (
          <>
            <DataTable
              caption="Вузы"
              columns={columns}
              rows={universities.data.items}
              rowKey={(row) => row.id}
              onRowClick={(row) => navigate(`/universities/${row.id}`)}
              refreshing={universities.isFetching && universities.isPlaceholderData}
              empty={
                <EmptyState icon={Building2} title="Вузы не найдены">
                  Измените условия поиска.
                </EmptyState>
              }
            />
            <Pager
              total={universities.data.total}
              limit={LIMIT}
              offset={offset}
              onChange={(next) => update({ offset: next ? String(next) : "" })}
              forms={["вуз", "вуза", "вузов"]}
            />
          </>
        )}
      </Card>
      <UniversityFormModal open={creating} onClose={() => setCreating(false)} />
    </div>
  );
}
