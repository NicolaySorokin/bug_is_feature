/**
 * Заявки с сайта. В списке персональные данные, поэтому он открыт только по праву
 * «Персональные данные студентов». Сервер проверяет то же самое.
 */
import { keepPreviousData, useQuery } from "@tanstack/react-query";
import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { listApplications } from "../../api/endpoints";
import { usePrograms, useUniversities } from "../../api/queries";
import type { Application } from "../../api/types";
import { DataTable, Pager, type Column } from "../../components/DataTable";
import { Card, EmptyState, ErrorState, Field, Loading, SearchInput, SelectField, StatusBadge } from "../../components/ui";
import { formatDateTime } from "../../lib/format";
import { usePersistentState } from "../../lib/storage";

const LIMIT = 50;

export function ApplicationsList() {
  const programs = usePrograms();
  const universities = useUniversities();
  const [filters, setFilters] = usePersistentState("applications.filters", {
    program_id: "",
    university_id: "",
    enrolled: "",
    search: "",
  });
  const [search, setSearch] = useState(filters.search);
  const [offset, setOffset] = useState(0);

  useEffect(() => {
    const timer = window.setTimeout(() => {
      setFilters((current) => ({ ...current, search: search.trim() }));
      setOffset(0);
    }, 350);
    return () => window.clearTimeout(timer);
  }, [search, setFilters]);

  const query = {
    program_id: filters.program_id || undefined,
    university_id: filters.university_id || undefined,
    enrolled: filters.enrolled === "" ? undefined : filters.enrolled === "true",
    search: filters.search || undefined,
    limit: LIMIT,
    offset,
  };
  const applications = useQuery({
    queryKey: ["statistics", "applications", query],
    queryFn: () => listApplications(query),
    placeholderData: keepPreviousData,
  });

  const update = (patch: Partial<typeof filters>) => {
    setFilters((current) => ({ ...current, ...patch }));
    setOffset(0);
  };

  const columns: Column<Application>[] = [
    {
      key: "person",
      title: "Заявитель",
      primary: true,
      render: (row) => (
        <div className="cell-title">
          <strong>{row.full_name}</strong>
          <small>{[row.phone, row.email].filter(Boolean).join(" · ") || "Контакты не указаны"}</small>
        </div>
      ),
    },
    {
      key: "course",
      title: "Курс",
      render: (row) => (
        <div className="cell-title">
          <span>{row.course_name}</span>
          <small>{row.stream_number ? `поток № ${row.stream_number}` : "поток не указан"}</small>
        </div>
      ),
    },
    {
      key: "university",
      title: "Вуз заявителя",
      render: (row) =>
        row.university_id ? (
          <Link to={`/universities/${row.university_id}`}>{row.university_name || "—"}</Link>
        ) : (
          <span className="muted">Не указан</span>
        ),
    },
    {
      key: "enrolled",
      title: "Обучение",
      render: (row) => (row.enrolled ? <StatusBadge tone="success">Учится</StatusBadge> : <StatusBadge>Не начато</StatusBadge>),
    },
    { key: "submitted", title: "Подана", className: "nowrap", render: (row) => formatDateTime(row.submitted_at) },
    { key: "external", title: "Номер заявки", render: (row) => <span className="mono">{row.external_id}</span> },
  ];

  return (
    <div className="stack">
      <div className="toolbar" style={{ marginBottom: 0 }}>
        <Field label="Поиск" className="field--grow">
          <SearchInput value={search} onChange={setSearch} placeholder="ФИО, почта, телефон или номер заявки" />
        </Field>
        <SelectField
          label="ИТ-программа"
          value={filters.program_id}
          onChange={(value) => update({ program_id: value })}
          placeholder="Все"
          options={(programs.data || []).map((item) => ({ value: item.id, label: item.name }))}
        />
        <SelectField
          label="Вуз"
          value={filters.university_id}
          onChange={(value) => update({ university_id: value })}
          placeholder="Все"
          options={(universities.data || []).map((item) => ({ value: item.id, label: item.short_name || item.name }))}
        />
        <SelectField
          label="Обучение"
          value={filters.enrolled}
          onChange={(value) => update({ enrolled: value })}
          placeholder="Все"
          options={[
            { value: "true", label: "Учатся" },
            { value: "false", label: "Не начали" },
          ]}
        />
      </div>
      <p className="muted" style={{ fontSize: 13 }}>
        Персональные данные заявителей: используйте только для работы с заявками (152-ФЗ). Просмотр - по отдельному праву
        «Персональные данные студентов», выданному администратором.
      </p>
      <Card flush>
        {applications.isPending ? (
          <Loading />
        ) : applications.isError ? (
          <ErrorState error={applications.error} onRetry={() => void applications.refetch()} />
        ) : (
          <>
            <DataTable
              caption="Заявки с сайта"
              columns={columns}
              rows={applications.data.items}
              rowKey={(row) => row.id}
              refreshing={applications.isFetching && applications.isPlaceholderData}
              empty={<EmptyState title="Заявок нет">Заявки загружаются из API сайта в разделе «LMS и сайт».</EmptyState>}
            />
            <Pager
              total={applications.data.total}
              limit={LIMIT}
              offset={offset}
              onChange={setOffset}
              forms={["заявка", "заявки", "заявок"]}
            />
          </>
        )}
      </Card>
    </div>
  );
}
