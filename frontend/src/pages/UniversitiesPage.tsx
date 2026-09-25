/**
 * Вузы.
 *
 * Руководитель назначает, меняет и снимает ответственного за вуз прямо
 * в строке списка (раздел «Роли» ТЗ). Остальные видят, кто отвечает.
 */
import { keepPreviousData, useQuery } from "@tanstack/react-query";
import { Building2, Plus, RotateCcw } from "lucide-react";
import { useEffect, useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import { listUniversities, updateUniversity } from "../api/endpoints";
import { useApiMutation } from "../api/mutations";
import { invalidateContractData, keys, useUsers } from "../api/queries";
import type { UniversityListItem } from "../api/types";
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
import { formatNumber } from "../lib/format";
import { usePageTitle } from "../lib/usePageTitle";
import { useUrlFilters } from "../lib/useUrlFilters";
import { UniversityFormModal } from "./UniversityForm";

const LIMIT = 25;
const KEYS = ["search", "manager_id", "unassigned", "is_active", "offset"];

export default function UniversitiesPage() {
  const { can, me } = useSession();
  const navigate = useNavigate();
  const users = useUsers();
  const [filters, update, reset] = useUrlFilters("universities", KEYS);
  const [search, setSearch] = useState(filters.search || "");
  const [creating, setCreating] = useState(false);
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
    is_active: filters.is_active === "" || filters.is_active === undefined ? undefined : filters.is_active === "true",
    limit: LIMIT,
    offset,
  };
  const universities = useQuery({
    queryKey: [...keys.universities, "page", query],
    queryFn: () => listUniversities(query),
    placeholderData: keepPreviousData,
  });

  const assign = useApiMutation(
    ({ id, managerId }: { id: string; managerId: string }) => updateUniversity(id, { manager_id: managerId || null }),
    {
      success: (saved) =>
        saved.manager ? `Ответственный за ${saved.short_name || saved.name}: ${saved.manager.full_name}` : "Ответственный снят",
      onSuccess: () => invalidateContractData(),
    },
  );

  const managers = (users.data || [])
    .filter((user) => user.is_active && (user.roles || []).includes("manager"))
    .map((user) => ({ value: user.id, label: user.full_name }));

  const columns: Column<UniversityListItem>[] = [
    {
      key: "name",
      title: "Вуз",
      primary: true,
      render: (row) => (
        <div className="cell-title">
          <Link to={`/universities/${row.id}`}>
            <strong>{row.short_name || row.name}</strong>
          </Link>
          {row.short_name && <small>{row.name}</small>}
        </div>
      ),
    },
    { key: "city", title: "Город", render: (row) => row.city || "—" },
    {
      key: "manager",
      title: "Ответственный",
      render: (row) =>
        can("assign_responsible") ? (
          <SelectField
            size="s"
            label={<span className="visually-hidden">Ответственный за {row.name}</span>}
            value={row.manager_id || ""}
            onChange={(value) => assign.mutate({ id: row.id, managerId: value })}
            placeholder="— не назначен —"
            options={managers}
          />
        ) : (
          row.manager?.full_name || <Tag tone="warn">Не назначен</Tag>
        ),
    },
    {
      key: "contracts",
      title: "Договоры",
      className: "col-num",
      render: (row) => (
        <span title="Действующие / все">
          {formatNumber(row.active_contracts_count || 0)} / {formatNumber(row.contracts_count || 0)}
        </span>
      ),
    },
    {
      key: "state",
      title: "Состояние",
      render: (row) =>
        row.is_active ? <StatusBadge tone="success">В работе</StatusBadge> : <StatusBadge>Не активен</StatusBadge>,
    },
  ];

  const hasFilters = Boolean(filters.manager_id || filters.unassigned || filters.is_active || filters.search);

  return (
    <div className="page">
      <PageHeader
        title="Вузы"
        description={
          can("assign_responsible")
            ? "Вузы и школы-партнёры ИТ Школы. Ответственного можно назначить или снять прямо в списке."
            : "Вузы и школы-партнёры ИТ Школы и ответственные за них."
        }
        actions={
          can("edit_university") && (
            <Button icon={Plus} onClick={() => setCreating(true)}>
              Добавить вуз
            </Button>
          )
        }
      />
      <div className="toolbar">
        <div className="field field--grow">
          <span className="field__label">Поиск</span>
          <SearchInput value={search} onChange={setSearch} placeholder="Название, сокращение или город" />
        </div>
        <SelectField
          label="Ответственный"
          value={filters.unassigned === "true" ? "__none" : filters.manager_id || ""}
          onChange={(value) =>
            value === "__none" ? update({ unassigned: "true", manager_id: "" }) : update({ manager_id: value, unassigned: "" })
          }
          placeholder="Все"
          options={[
            { value: me.id, label: "Мои вузы" },
            { value: "__none", label: "Не назначен" },
            ...managers.filter((item) => item.value !== me.id),
          ]}
        />
        <SelectField
          label="Состояние"
          value={filters.is_active || ""}
          onChange={(value) => update({ is_active: value })}
          placeholder="Все"
          options={[
            { value: "true", label: "В работе" },
            { value: "false", label: "Не активные" },
          ]}
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
