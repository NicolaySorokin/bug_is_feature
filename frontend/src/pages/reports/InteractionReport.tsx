/**
 * Отчёт о взаимодействии с вузами. Строка: взаимодействие в разрезе ИТ-программы. Отчёт
 * пересчитывается при смене фильтров, выгрузка берёт те же фильтры и колонки.
 */
import { keepPreviousData, useQuery } from "@tanstack/react-query";
import { Download, FileJson, FileSpreadsheet, FileText, RotateCcw, SlidersHorizontal } from "lucide-react";
import { useEffect, useMemo, useState } from "react";
import { Link } from "react-router-dom";
import { exportReport, exportReportChart, listReportColumns, previewReport } from "../../api/endpoints";
import { useDownload } from "../../api/mutations";
import {
  useDirectory,
  useDirections,
  useLabel,
  usePrograms,
  useProducts,
  useStageIndex,
  useUniversities,
} from "../../api/queries";
import type {
  ClosureReason,
  ContractStatus,
  ExportFormat,
  InteractionOutcome,
  InteractionSource,
  InteractionStatus,
  PeriodBasis,
  ReportColumn,
  ReportRequest,
  ReportRow,
} from "../../api/types";
import { ChartCard } from "../../charts/ChartCard";
import { Modal } from "../../components/Modal";
import { FilterSelect, MultiSelect } from "../../components/MultiSelect";
import { PeriodPicker, type Period } from "../../components/PeriodPicker";
import {
  Button,
  Card,
  Checkbox,
  EmptyState,
  ErrorState,
  Kpi,
  KpiRow,
  Loading,
  TextField,
} from "../../components/ui";
import { formatDate, formatDateTime, formatNumber } from "../../lib/format";
import { CLOSURE_REASONS, INTERACTION_STATUSES, PERIOD_BASIS_LABELS } from "../../lib/labels";
import { usePersistentState } from "../../lib/storage";

interface Saved {
  title: string;
  columns: ReportColumn[];
  period: Period;
  period_basis: PeriodBasis;
  university_ids: string[];
  direction_ids: string[];
  program_ids: string[];
  product_ids: string[];
  manager_ids: string[];
  statuses: InteractionStatus[];
  outcomes: InteractionOutcome[];
  closure_reasons: ClosureReason[];
  sources: InteractionSource[];
  contract_statuses: ContractStatus[];
  stages: string[];
}

const DEFAULTS: Saved = {
  title: "Отчёт о взаимодействии с вузами",
  columns: [],
  period: { date_from: "", date_to: "" },
  period_basis: "created",
  university_ids: [],
  direction_ids: [],
  program_ids: [],
  product_ids: [],
  manager_ids: [],
  statuses: [],
  outcomes: [],
  closure_reasons: [],
  sources: [],
  contract_statuses: [],
  stages: [],
};

const PREVIEW_ROWS = 300;

function useDebounced<T>(value: T, delay = 300): T {
  const [debounced, setDebounced] = useState(value);
  useEffect(() => {
    const timer = window.setTimeout(() => setDebounced(value), delay);
    return () => window.clearTimeout(timer);
  }, [value, delay]);
  return debounced;
}

function Cell({ row, column }: { row: ReportRow; column: ReportColumn }) {
  switch (column) {
    case "university":
      return (
        <Link to={`/universities/${row.university_id}`} title={row.university_full || undefined}>
          {row.university}
        </Link>
      );
    case "interaction":
      return <Link to={`/interactions/${row.interaction_id}`}>{row.interaction || "Взаимодействие"}</Link>;
    case "contract_number":
      return row.contract_number ? (
        <Link to={`/interactions/${row.interaction_id}?tab=contract`}>{row.contract_number}</Link>
      ) : (
        <span className="muted">нет</span>
      );
    case "contract_status":
      return <>{row.contract_status_label || row.contract_status || "—"}</>;
    case "status":
      return <>{row.status_label || row.status}</>;
    case "outcome":
      return <>{row.outcome_label || "—"}</>;
    case "closure_reason":
      return <>{row.closure_reason_label || "—"}</>;
    case "source":
      return <>{row.source_label || row.source}</>;
    case "created_at":
      return <>{formatDate(row.created_at)}</>;
    case "closed_at":
      return <>{formatDate(row.closed_at)}</>;
    case "implementation_status":
      return <>{row.implementation_status_label || "—"}</>;
    case "signed_at":
      return <>{formatDate(row.signed_at)}</>;
    case "valid_to":
      return <>{formatDate(row.valid_to)}</>;
    case "days_on_stage":
      return <>{row.days_on_stage ?? "—"}</>;
    default: {
      const value = row[column as keyof ReportRow];
      return <>{value === null || value === undefined || value === "" ? "—" : String(value)}</>;
    }
  }
}

export function InteractionReport() {
  const label = useLabel();
  const [saved, setSaved] = usePersistentState<Saved>("report.interaction.v2", DEFAULTS);
  const state = { ...DEFAULTS, ...saved };
  const [chooser, setChooser] = useState(false);
  const [filtersOpen, setFiltersOpen] = useState(false);
  const [download, downloading] = useDownload();
  const columnsInfo = useQuery({ queryKey: ["report-columns"], queryFn: listReportColumns, staleTime: Infinity });
  const universities = useUniversities();
  const directions = useDirections();
  const programs = usePrograms();
  const products = useProducts();
  const directory = useDirectory();
  const stageIndex = useStageIndex();

  // Колонки по умолчанию предлагает сервер.
  useEffect(() => {
    if (columnsInfo.data && state.columns.length === 0) {
      setSaved((current) => ({
        ...DEFAULTS,
        ...current,
        columns: columnsInfo.data.filter((item) => item.default).map((item) => item.key),
      }));
    }
  }, [columnsInfo.data, state.columns.length, setSaved]);

  const set = <K extends keyof Saved>(key: K, value: Saved[K]) =>
    setSaved((current) => ({ ...DEFAULTS, ...current, [key]: value }));

  const request: ReportRequest = useMemo(
    () => ({
      title: state.title.trim() || DEFAULTS.title,
      columns: state.columns,
      filters: {
        date_from: state.period.date_from || null,
        date_to: state.period.date_to || null,
        period_basis: state.period_basis,
        university_ids: state.university_ids,
        direction_ids: state.direction_ids,
        program_ids: state.program_ids,
        product_ids: state.product_ids,
        manager_ids: state.manager_ids,
        statuses: state.statuses,
        outcomes: state.outcomes,
        closure_reasons: state.closure_reasons,
        sources: state.sources,
        contract_statuses: state.contract_statuses,
        stage_ids: state.stages.flatMap((name) => stageIndex.data?.ids[name] || []),
      },
    }),
    // state пересоздаётся на каждый рендер, сравниваем по сохранённому значению.
    // eslint-disable-next-line react-hooks/exhaustive-deps
    [saved, stageIndex.data],
  );
  const debounced = useDebounced(request);
  const previewRequest = { ...debounced, title: DEFAULTS.title };

  const report = useQuery({
    queryKey: ["report", previewRequest],
    queryFn: () => previewReport(previewRequest),
    enabled: (debounced.columns || []).length > 0,
    placeholderData: keepPreviousData,
  });

  const exportAs = (format: ExportFormat) => download(() => exportReport(request, format));
  const filtersCount =
    [
      state.university_ids,
      state.direction_ids,
      state.program_ids,
      state.product_ids,
      state.manager_ids,
      state.statuses,
      state.outcomes,
      state.closure_reasons,
      state.sources,
      state.contract_statuses,
      state.stages,
    ].filter((list) => list.length > 0).length + (state.period.date_from || state.period.date_to ? 1 : 0);

  return (
    <div className="stack">
      <Card>
        <div className="toolbar" style={{ marginBottom: 12 }}>
          <PeriodPicker value={state.period} onChange={(value) => set("period", value)} />
          <FilterSelect
            label="Период считать"
            value={state.period_basis}
            onChange={(value) => set("period_basis", value as PeriodBasis)}
            options={Object.entries(PERIOD_BASIS_LABELS).map(([value, text]) => ({ value, label: text }))}
          />
        </div>
        <div className="filters-toggle">
          <Button variant="outline" size="s" icon={SlidersHorizontal} onClick={() => setFiltersOpen((value) => !value)}>
            {filtersOpen ? "Скрыть фильтры" : "Фильтры"}
          </Button>
        </div>
        <div className={`toolbar toolbar--collapsible ${filtersOpen ? "is-open" : ""}`} style={{ marginBottom: 0 }}>
          <MultiSelect
            label="Вузы"
            value={state.university_ids}
            onChange={(value) => set("university_ids", value)}
            options={(universities.data || []).map((item) => ({
              value: item.id,
              label: item.short_name || item.name,
              hint: item.short_name ? item.name : undefined,
            }))}
          />
          <MultiSelect
            label="ИТ-направления"
            value={state.direction_ids}
            onChange={(value) => set("direction_ids", value)}
            options={(directions.data || []).map((item) => ({ value: item.id, label: item.name }))}
          />
          <MultiSelect
            label="ИТ-программы"
            value={state.program_ids}
            onChange={(value) => set("program_ids", value)}
            options={(programs.data || []).map((item) => ({ value: item.id, label: item.name }))}
          />
          <MultiSelect
            label="ИТ-продукты"
            value={state.product_ids}
            onChange={(value) => set("product_ids", value)}
            options={(products.data || []).map((item) => ({ value: item.id, label: item.name }))}
          />
          <MultiSelect
            label="Ответственные"
            value={state.manager_ids}
            onChange={(value) => set("manager_ids", value)}
            options={(directory.data || []).map((user) => ({ value: user.id, label: user.full_name }))}
          />
          <MultiSelect
            label="Статус взаимодействия"
            value={state.statuses}
            onChange={(value) => set("statuses", value as InteractionStatus[])}
            options={INTERACTION_STATUSES.map((value) => ({ value, label: label("interaction_status", value) }))}
          />
          <MultiSelect
            label="Результат"
            value={state.outcomes}
            onChange={(value) => set("outcomes", value as InteractionOutcome[])}
            options={(["successful", "partial", "unsuccessful"] as const).map((value) => ({
              value,
              label: label("interaction_outcome", value),
            }))}
          />
          <MultiSelect
            label="Причина закрытия"
            value={state.closure_reasons}
            onChange={(value) => set("closure_reasons", value as ClosureReason[])}
            options={CLOSURE_REASONS.map((value) => ({ value, label: label("closure_reason", value) }))}
          />
          <MultiSelect
            label="Источник"
            value={state.sources}
            onChange={(value) => set("sources", value as InteractionSource[])}
            options={(["manual", "site", "import", "lms"] as const).map((value) => ({
              value,
              label: label("interaction_source", value),
            }))}
          />
          <MultiSelect
            label="Статус договора"
            value={state.contract_statuses}
            onChange={(value) => set("contract_statuses", value as ContractStatus[])}
            options={(["draft", "active", "suspended", "closed", "cancelled"] as const).map((value) => ({
              value,
              label: label("contract_status", value),
            }))}
          />
          <MultiSelect
            label="Этапы процесса"
            value={state.stages}
            onChange={(value) => set("stages", value)}
            options={(stageIndex.data?.names || []).map((name) => ({ value: name, label: name }))}
          />
        </div>
        <div className="row-between" style={{ marginTop: 16 }}>
          <div className="row">
            <Button variant="outline" icon={SlidersHorizontal} onClick={() => setChooser(true)}>
              Колонки: {state.columns.length}
            </Button>
            {filtersCount > 0 && (
              <Button
                variant="ghost"
                icon={RotateCcw}
                onClick={() => setSaved((current) => ({ ...DEFAULTS, title: current.title, columns: current.columns }))}
              >
                Сбросить фильтры
              </Button>
            )}
          </div>
          <div className="row">
            <span className="muted">Скачать:</span>
            <Button variant="secondary" icon={FileSpreadsheet} disabled={downloading} onClick={() => exportAs("xlsx")}>
              XLSX
            </Button>
            <Button variant="secondary" icon={FileSpreadsheet} disabled={downloading} onClick={() => exportAs("xls")}>
              XLS
            </Button>
            <Button variant="secondary" icon={FileText} disabled={downloading} onClick={() => exportAs("pdf")}>
              PDF
            </Button>
            <Button variant="secondary" icon={FileJson} disabled={downloading} onClick={() => exportAs("json")}>
              JSON
            </Button>
          </div>
        </div>
      </Card>

      {report.isPending ? (
        <Loading text="Формируем отчёт" />
      ) : report.isError ? (
        <ErrorState error={report.error} onRetry={() => void report.refetch()} />
      ) : (
        <div className={`stack ${report.isFetching && report.isPlaceholderData ? "is-refreshing" : ""}`}>
          <KpiRow>
            <Kpi label="Взаимодействия" value={formatNumber(report.data.totals.interactions)} />
            <Kpi label="Вузы" value={formatNumber(report.data.totals.universities)} />
            <Kpi
              label="Договоры"
              value={formatNumber(report.data.totals.contracts)}
              detail={
                report.data.totals.unsigned_excluded
                  ? `без подписанного договора не вошло: ${formatNumber(report.data.totals.unsigned_excluded)}`
                  : undefined
              }
            />
            <Kpi label="ИТ-программы" value={formatNumber(report.data.totals.programs)} />
            <Kpi label="ИТ-продукты" value={formatNumber(report.data.totals.products)} />
            <Kpi label="Строк в отчёте" value={formatNumber(report.data.totals.rows)} />
          </KpiRow>

          <Card
            title={state.title || DEFAULTS.title}
            description={`Сформирован ${formatDateTime(report.data.generated_at)}${
              report.data.rows.length > PREVIEW_ROWS ? ` · на экране первые ${PREVIEW_ROWS} строк, полностью - в выгрузке` : ""
            }`}
            flush
            actions={
              <Button variant="ghost" size="s" icon={Download} disabled={downloading} onClick={() => exportAs("xlsx")}>
                Скачать XLSX
              </Button>
            }
          >
            {report.data.rows.length === 0 ? (
              <EmptyState title="По условиям отчёта ничего нет">Расширьте период или уберите часть фильтров.</EmptyState>
            ) : (
              <div className="table-wrap" style={{ maxHeight: 560, overflowY: "auto" }}>
                <table className="data-table">
                  <thead>
                    <tr>
                      {report.data.columns.map((column) => (
                        <th key={column} scope="col" className={column === "days_on_stage" ? "col-num" : undefined}>
                          {report.data.column_titles[column] || column}
                        </th>
                      ))}
                    </tr>
                  </thead>
                  <tbody>
                    {report.data.rows.slice(0, PREVIEW_ROWS).map((row, index) => (
                      <tr key={`${row.interaction_id}-${index}`}>
                        {report.data.columns.map((column) => (
                          <td key={column} className={column === "days_on_stage" ? "col-num" : undefined}>
                            <Cell row={row} column={column} />
                          </td>
                        ))}
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}
          </Card>

          <div className="grid-2">
            {report.data.charts.map((chart) => (
              <ChartCard
                key={chart.key}
                chart={chart}
                onExport={(format) => download(() => exportReportChart(request, chart.key, format))}
              />
            ))}
          </div>
        </div>
      )}

      <Modal
        open={chooser}
        onClose={() => setChooser(false)}
        title="Колонки отчёта"
        description="Выбранные колонки попадут и на экран, и в выгрузку. Порядок - как в списке."
        footer={
          <>
            <Button
              variant="ghost"
              onClick={() =>
                set(
                  "columns",
                  (columnsInfo.data || []).filter((item) => item.default).map((item) => item.key),
                )
              }
            >
              По умолчанию
            </Button>
            <Button onClick={() => setChooser(false)}>Готово</Button>
          </>
        }
      >
        <div className="stack-s">
          <TextField
            label="Название отчёта"
            value={state.title}
            onChange={(value) => set("title", value)}
            maxLength={200}
            hint="Заголовок файла выгрузки"
          />
          {(columnsInfo.data || []).map((column) => (
            <Checkbox
              key={column.key}
              label={column.title}
              checked={state.columns.includes(column.key)}
              onChange={(checked) =>
                set(
                  "columns",
                  (columnsInfo.data || [])
                    .map((item) => item.key)
                    .filter((key) => (key === column.key ? checked : state.columns.includes(key))),
                )
              }
            />
          ))}
          {state.columns.length === 0 && <span className="field__error">Выберите хотя бы одну колонку</span>}
        </div>
      </Modal>
    </div>
  );
}
