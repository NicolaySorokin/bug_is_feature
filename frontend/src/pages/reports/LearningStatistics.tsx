/**
 * Статистика обучения: рейтинг ИТ-программ по заявкам с сайта и
 * обучающимся из LMS, потоки, конверсия заявок в обучение.
 */
import { keepPreviousData, useQuery } from "@tanstack/react-query";
import { FileJson, FileSpreadsheet, FileText, RotateCcw } from "lucide-react";
import { useMemo, useState } from "react";
import { exportStatistics, exportStatisticsChart, getProgramStreams, getStatistics } from "../../api/endpoints";
import { useDownload } from "../../api/mutations";
import { useDirections, usePrograms, useUniversities } from "../../api/queries";
import type { ExportFormat, ProgramStatistics, StatisticsFilters } from "../../api/types";
import { ChartCard } from "../../charts/ChartCard";
import { Drawer } from "../../components/Modal";
import { MultiSelect } from "../../components/MultiSelect";
import { PeriodPicker, type Period } from "../../components/PeriodPicker";
import { Button, Card, EmptyState, ErrorState, Kpi, KpiRow, Loading } from "../../components/ui";
import { formatDate, formatDateTime, formatNumber } from "../../lib/format";
import { usePersistentState } from "../../lib/storage";

interface Saved {
  period: Period;
  direction_ids: string[];
  program_ids: string[];
  university_ids: string[];
}

const DEFAULTS: Saved = { period: { date_from: "", date_to: "" }, direction_ids: [], program_ids: [], university_ids: [] };

function Streams({ program, onClose }: { program: ProgramStatistics | null; onClose: () => void }) {
  const streams = useQuery({
    queryKey: ["statistics", "streams", program?.program_id],
    queryFn: () => getProgramStreams(program!.program_id!),
    enabled: Boolean(program?.program_id),
  });
  return (
    <Drawer
      open={program !== null}
      onClose={onClose}
      title={program?.program || ""}
      description={`Потоки программы · ${program?.direction || ""}`}
    >
      {streams.isPending ? (
        <Loading />
      ) : streams.isError ? (
        <ErrorState error={streams.error} />
      ) : streams.data.length === 0 ? (
        <EmptyState title="Потоков нет" />
      ) : (
        <table className="data-table">
          <thead>
            <tr>
              <th scope="col">Поток</th>
              <th scope="col" className="col-num">
                Заявки
              </th>
              <th scope="col" className="col-num">
                Обучаются
              </th>
              <th scope="col" className="col-num">
                Конверсия
              </th>
            </tr>
          </thead>
          <tbody>
            {streams.data.map((item, index) => (
              <tr key={index}>
                <td>{item.stream ? `№ ${item.stream}` : "Без номера"}</td>
                <td className="col-num">{formatNumber(item.applications)}</td>
                <td className="col-num">{formatNumber(item.learners)}</td>
                <td className="col-num">
                  {item.applications
                    ? `${Math.round(((item.learners || 0) / item.applications) * 1000) / 10}%`.replace(".", ",")
                    : "—"}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
    </Drawer>
  );
}

export function LearningStatistics() {
  const [saved, setSaved] = usePersistentState<Saved>("report.learning", DEFAULTS);
  const state = { ...DEFAULTS, ...saved };
  const [download, downloading] = useDownload();
  const [program, setProgram] = useState<ProgramStatistics | null>(null);
  const directions = useDirections();
  const programs = usePrograms();
  const universities = useUniversities();

  const filters: StatisticsFilters = useMemo(
    () => ({
      date_from: state.period.date_from || null,
      date_to: state.period.date_to || null,
      direction_ids: state.direction_ids,
      program_ids: state.program_ids,
      university_ids: state.university_ids,
    }),
    // eslint-disable-next-line react-hooks/exhaustive-deps
    [saved],
  );
  const statistics = useQuery({
    queryKey: ["statistics", filters],
    queryFn: () => getStatistics(filters),
    placeholderData: keepPreviousData,
  });
  const set = <K extends keyof Saved>(key: K, value: Saved[K]) =>
    setSaved((current) => ({ ...DEFAULTS, ...current, [key]: value }));
  const exportAs = (format: ExportFormat) => download(() => exportStatistics(filters, format));
  const hasFilters =
    state.direction_ids.length + state.program_ids.length + state.university_ids.length > 0 ||
    Boolean(state.period.date_from || state.period.date_to);

  return (
    <div className="stack">
      <Card>
        <div className="toolbar" style={{ marginBottom: 0 }}>
          <PeriodPicker value={state.period} onChange={(value) => set("period", value)} />
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
            label="Вузы"
            value={state.university_ids}
            onChange={(value) => set("university_ids", value)}
            options={(universities.data || []).map((item) => ({ value: item.id, label: item.short_name || item.name }))}
          />
        </div>
        <div className="row-between" style={{ marginTop: 16 }}>
          <div>
            {hasFilters && (
              <Button variant="ghost" icon={RotateCcw} onClick={() => setSaved(DEFAULTS)}>
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

      {statistics.isPending ? (
        <Loading text="Считаем статистику" />
      ) : statistics.isError ? (
        <ErrorState error={statistics.error} onRetry={() => void statistics.refetch()} />
      ) : (
        <div className={`stack ${statistics.isFetching && statistics.isPlaceholderData ? "is-refreshing" : ""}`}>
          <KpiRow>
            <Kpi label="Заявки с сайта" value={formatNumber(statistics.data.totals.applications)} />
            <Kpi
              label="Обучаются (LMS)"
              value={formatNumber(statistics.data.totals.learners)}
              detail={
                statistics.data.totals.applications
                  ? `${Math.round((statistics.data.totals.learners / statistics.data.totals.applications) * 100)}% от заявок`
                  : undefined
              }
            />
            <Kpi label="Потоки" value={formatNumber(statistics.data.totals.streams)} />
            <Kpi label="ИТ-программы" value={formatNumber(statistics.data.totals.programs)} />
            <Kpi label="ИТ-направления" value={formatNumber(statistics.data.totals.directions)} />
          </KpiRow>

          <Card
            title="Рейтинг ИТ-программ"
            description={`По числу заявок · данные на ${formatDateTime(statistics.data.generated_at)} · нажмите на строку, чтобы увидеть потоки`}
            flush
          >
            {statistics.data.rows.length === 0 ? (
              <EmptyState title="Нет заявок за период">
                Заявки приходят с сайта ИТ Школы, обучающиеся - из LMS (раздел «LMS и сайт»).
              </EmptyState>
            ) : (
              <div className="table-wrap">
                <table className="data-table data-table--cards">
                  <thead>
                    <tr>
                      <th scope="col" className="col-num">
                        №
                      </th>
                      <th scope="col">ИТ-программа</th>
                      <th scope="col">Направление</th>
                      <th scope="col" className="col-num">
                        Заявки
                      </th>
                      <th scope="col" className="col-num">
                        Обучаются
                      </th>
                      <th scope="col" className="col-num">
                        Конверсия
                      </th>
                      <th scope="col" className="col-num">
                        Потоки
                      </th>
                      <th scope="col" className="col-num">
                        Вузы
                      </th>
                      <th scope="col">Последняя заявка</th>
                    </tr>
                  </thead>
                  <tbody>
                    {statistics.data.rows.map((row) => (
                      <tr
                        key={row.program_id || row.program}
                        className={row.program_id ? "clickable" : undefined}
                        onClick={() => row.program_id && setProgram(row)}
                      >
                        <td className="col-num" data-label="Место">
                          {row.rank}
                        </td>
                        <td className="cell-primary">
                          <strong>{row.program}</strong>
                        </td>
                        <td data-label="Направление">{row.direction}</td>
                        <td className="col-num" data-label="Заявки">
                          {formatNumber(row.applications)}
                        </td>
                        <td className="col-num" data-label="Обучаются">
                          {formatNumber(row.learners)}
                        </td>
                        <td className="col-num" data-label="Конверсия">
                          {`${row.conversion}%`.replace(".", ",")}
                        </td>
                        <td className="col-num" data-label="Потоки">
                          {formatNumber(row.streams)}
                        </td>
                        <td className="col-num" data-label="Вузы">
                          {formatNumber(row.universities)}
                        </td>
                        <td data-label="Последняя заявка">{formatDate(row.last_application)}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}
          </Card>

          {statistics.data.charts
            .filter((chart) => chart.key === "applications_by_month")
            .map((chart) => (
              <ChartCard
                key={chart.key}
                chart={chart}
                kind="trend"
                onExport={(format) => download(() => exportStatisticsChart(filters, chart.key, format))}
              />
            ))}
          <div className="grid-2">
            {statistics.data.charts
              .filter((chart) => chart.key !== "applications_by_month")
              .map((chart) => (
                <ChartCard
                  key={chart.key}
                  chart={chart}
                  onExport={(format) => download(() => exportStatisticsChart(filters, chart.key, format))}
                />
              ))}
          </div>
        </div>
      )}
      <Streams program={program} onClose={() => setProgram(null)} />
    </div>
  );
}
