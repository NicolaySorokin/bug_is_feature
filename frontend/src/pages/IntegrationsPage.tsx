/**
 * Обмен с LMS и сайтом ИТ Школы (п. 5 функциональных требований ТЗ).
 *
 * Технический раздел (пункт 28 перечня исправлений): журнал обмена
 * и очередь сопоставления видят администратор и сотрудники с отдельным
 * правом, бизнес-ролям он не нужен.
 *
 * Из LMS приходят программы, продукты и обучающиеся, с сайта - вузы,
 * заявки вузов на сотрудничество и заявки студентов на обучение. Запись
 * без связи по одному названию не сопоставляется: если в системе есть
 * похожая, внешняя ждёт решения в очереди. Новый вуз приходит «на
 * проверку». Заявка вуза добавляется в открытое взаимодействие или заводит
 * взаимодействие-черновик - процесс запускает ответственный. Заявка
 * студента - только статистика. Ошибка отдельной записи не роняет обмен:
 * запуск получает статус «Частично», а ошибка - строку в журнале.
 */
import { useQuery } from "@tanstack/react-query";
import { Ban, FileJson, GitMerge, PlugZap, Plus, RefreshCw } from "lucide-react";
import { useState } from "react";
import { useSearchParams } from "react-router-dom";
import {
  createFromMapping,
  getRun,
  getSettings,
  ignoreMapping,
  listMappings,
  listRuns,
  listSources,
  resolveMapping,
  syncAll,
  syncSource,
  updateSource,
  uploadSourcePayload,
} from "../api/endpoints";
import { useApiMutation } from "../api/mutations";
import { invalidateInteractionData, keys, queryClient, useLabel } from "../api/queries";
import type { IntegrationMapping, IntegrationRun, IntegrationSource } from "../api/types";
import { useSession } from "../auth/session";
import { DataTable, type Column } from "../components/DataTable";
import { FilePicker } from "../components/FilePicker";
import { Drawer, Modal } from "../components/Modal";
import {
  Button,
  Card,
  DescriptionList,
  EmptyState,
  ErrorState,
  Loading,
  PageHeader,
  StatusBadge,
  Switch,
  Tabs,
} from "../components/ui";
import { countLabel, formatDateTime, formatNumber } from "../lib/format";
import { RUN_TONE } from "../lib/labels";
import { usePageTitle } from "../lib/usePageTitle";

const DESCRIPTIONS: Record<string, string> = {
  lms: "ИТ-программы, продукты и обучающиеся. Из анкеты обучающегося берутся только нужные для статистики поля - паспорт, СНИЛС и адрес не сохраняются.",
  site: "Вузы, заявки вузов на сотрудничество и заявки студентов на обучение. Заявка вуза дополняет открытое взаимодействие или заводит черновик; заявка студента - только статистика.",
};

const TRIGGERS: Record<string, string> = { manual: "вручную", schedule: "по расписанию", file: "файлом" };

function describeRun(run: IntegrationRun): string {
  return `получено ${formatNumber(run.records_received)}, добавлено ${formatNumber(run.records_created)}, обновлено ${formatNumber(
    run.records_updated,
  )}${run.records_failed ? `, с ошибками ${formatNumber(run.records_failed)}` : ""}${
    run.records_pending ? `, ждут сопоставления ${formatNumber(run.records_pending)}` : ""
  }`;
}

function afterSync() {
  invalidateInteractionData();
  void queryClient.invalidateQueries({ queryKey: keys.runs });
  void queryClient.invalidateQueries({ queryKey: keys.sources });
  void queryClient.invalidateQueries({ queryKey: keys.mappings });
  void queryClient.invalidateQueries({ queryKey: ["catalog"] });
}

/** Запуск целиком: счётчики, пояснения и ошибки по отдельным записям. */
function RunDrawer({ runId, onClose }: { runId: string | null; onClose: () => void }) {
  const label = useLabel();
  const run = useQuery({ queryKey: ["run", runId], queryFn: () => getRun(runId!), enabled: Boolean(runId) });
  return (
    <Drawer
      open={runId !== null}
      onClose={onClose}
      title="Запуск обмена"
      description={run.data ? formatDateTime(run.data.started_at) : undefined}
    >
      {run.isPending ? (
        <Loading />
      ) : run.isError ? (
        <ErrorState error={run.error} />
      ) : (
        <div className="stack">
          <DescriptionList
            items={[
              [
                "Результат",
                <StatusBadge key="s" tone={RUN_TONE[run.data.status]}>
                  {label("integration_run_status", run.data.status)}
                </StatusBadge>,
              ],
              ["Как запущен", TRIGGERS[run.data.trigger || "manual"] || run.data.trigger],
              ["Попыток обращения", run.data.attempts ?? 1],
              ["Записи", describeRun(run.data)],
              ["Завершён", formatDateTime(run.data.finished_at)],
            ]}
          />
          {run.data.error_message && <p className="field__error">{run.data.error_message}</p>}
          {run.data.notes && (
            <Card title="Пояснения">
              <p className="soft" style={{ whiteSpace: "pre-wrap" }}>
                {run.data.notes}
              </p>
            </Card>
          )}
          <Card title="Ошибки по записям" flush>
            {(run.data.errors || []).length === 0 ? (
              <p className="muted" style={{ padding: 16 }}>
                Ошибок нет.
              </p>
            ) : (
              <div className="list">
                {(run.data.errors || []).map((item) => (
                  <div key={item.id} className="list-item">
                    <div className="list-item__main">
                      <strong>{item.external_id || "Запись без идентификатора"}</strong>
                      <small>{item.message}</small>
                    </div>
                  </div>
                ))}
              </div>
            )}
          </Card>
        </div>
      )}
    </Drawer>
  );
}

/** Очередь ручного сопоставления внешних записей. */
function MappingQueue() {
  const { can } = useSession();
  const label = useLabel();
  const mappings = useQuery({ queryKey: keys.mappings, queryFn: () => listMappings() });
  const resolve = useApiMutation(({ id, entityId }: { id: string; entityId: string }) => resolveMapping(id, entityId), {
    success: "Запись сопоставлена - следующий обмен её подхватит",
    onSuccess: afterSync,
  });
  const create = useApiMutation((id: string) => createFromMapping(id), {
    success: "Заведена новая запись",
    onSuccess: afterSync,
  });
  const ignore = useApiMutation((id: string) => ignoreMapping(id), {
    success: "Запись источника больше не загружается",
    onSuccess: afterSync,
  });
  const decide = can("resolve_mappings");

  const columns: Column<IntegrationMapping>[] = [
    {
      key: "record",
      title: "Запись источника",
      primary: true,
      render: (row) => (
        <div className="cell-title">
          <strong>{row.external_name}</strong>
          <small>
            {row.entity_title} · {row.source_code.toUpperCase()} · {row.external_id}
          </small>
        </div>
      ),
    },
    {
      key: "suggested",
      title: "Похожая запись в системе",
      render: (row) =>
        row.status === "resolved" ? (
          <span>{row.entity_name || "—"}</span>
        ) : row.suggested_name ? (
          <span>{row.suggested_name}</span>
        ) : (
          <span className="muted">нет</span>
        ),
    },
    {
      key: "status",
      title: "Решение",
      render: (row) => (
        <StatusBadge tone={row.status === "pending" ? "warning" : row.status === "resolved" ? "success" : "neutral"}>
          {label("mapping_status", row.status)}
        </StatusBadge>
      ),
    },
    {
      key: "actions",
      title: "",
      className: "col-actions",
      render: (row) =>
        decide && row.status === "pending" ? (
          <div className="row" style={{ gap: 6, flexWrap: "wrap" }}>
            {row.suggested_entity_id && (
              <Button
                size="s"
                icon={GitMerge}
                loading={resolve.isPending && resolve.variables?.id === row.id}
                onClick={() => resolve.mutate({ id: row.id, entityId: row.suggested_entity_id! })}
              >
                Это та же запись
              </Button>
            )}
            <Button
              size="s"
              variant="outline"
              icon={Plus}
              loading={create.isPending && create.variables === row.id}
              onClick={() => create.mutate(row.id)}
            >
              Завести новую
            </Button>
            <Button
              size="s"
              variant="ghost"
              icon={Ban}
              loading={ignore.isPending && ignore.variables === row.id}
              onClick={() => ignore.mutate(row.id)}
            >
              Не загружать
            </Button>
          </div>
        ) : row.resolved_at ? (
          <small className="muted">{formatDateTime(row.resolved_at)}</small>
        ) : null,
    },
  ];

  return (
    <Card
      title="Сопоставление"
      description="Запись источника без связи, но с похожим названием в системе: по одному названию система не решает - выберите сами."
      flush
    >
      {mappings.isPending ? (
        <Loading />
      ) : mappings.isError ? (
        <ErrorState error={mappings.error} onRetry={() => void mappings.refetch()} />
      ) : (
        <DataTable
          caption="Очередь сопоставления"
          columns={columns}
          rows={mappings.data}
          rowKey={(row) => row.id}
          empty={<EmptyState title="Очередь пуста">Все записи источников сопоставлены.</EmptyState>}
        />
      )}
    </Card>
  );
}

export default function IntegrationsPage() {
  const { can } = useSession();
  const label = useLabel();
  const [params, setParams] = useSearchParams();
  const tab = (params.get("tab") === "mappings" && can("resolve_mappings")) || !can("view_integration_log") ? "mappings" : "runs";
  const [uploadFor, setUploadFor] = useState<IntegrationSource | null>(null);
  const [files, setFiles] = useState<File[]>([]);
  const [runId, setRunId] = useState<string | null>(null);
  usePageTitle("LMS и сайт");

  const sources = useQuery({ queryKey: keys.sources, queryFn: listSources });
  const settings = useQuery({ queryKey: keys.settings, queryFn: getSettings });
  const interval = settings.data?.find((item) => item.key === "integration_sync_interval_hours")?.value ?? 0;
  const runs = useQuery({ queryKey: keys.runs, queryFn: () => listRuns({ limit: 50 }), enabled: can("view_integration_log") });
  const pending = useQuery({
    queryKey: [...keys.mappings, "pending"],
    queryFn: () => listMappings("pending"),
    enabled: can("resolve_mappings"),
  });

  const sync = useApiMutation((code: string) => syncSource(code), {
    success: (run) => `Синхронизация: ${describeRun(run)}`,
    onSuccess: afterSync,
    errorTitle: "Синхронизация не выполнена",
  });
  const syncEverything = useApiMutation(() => syncAll(), {
    success: (items) => `Синхронизировано источников: ${items.length}`,
    onSuccess: afterSync,
  });
  const toggle = useApiMutation(({ code, enabled }: { code: string; enabled: boolean }) => updateSource(code, enabled), {
    success: (source) => (source.is_enabled ? `${source.name}: обмен включён` : `${source.name}: обмен выключен`),
    onSuccess: () => void queryClient.invalidateQueries({ queryKey: keys.sources }),
  });
  const upload = useApiMutation(({ code, file }: { code: string; file: File }) => uploadSourcePayload(code, file), {
    success: (run) =>
      run.status === "failed" ? `Файл обработан с ошибкой: ${run.error_message}` : `Файл обработан: ${describeRun(run)}`,
    onSuccess: () => {
      afterSync();
      setUploadFor(null);
      setFiles([]);
    },
  });

  const sourceName = (code?: string) => sources.data?.find((item) => item.code === code)?.name || code || "—";

  const columns: Column<IntegrationRun>[] = [
    {
      key: "source",
      title: "Источник",
      primary: true,
      render: (row) => (
        <div className="cell-title">
          <button type="button" className="link-btn" onClick={() => setRunId(row.id)}>
            {sourceName(row.source_code)}
          </button>
          <small>
            {formatDateTime(row.started_at)} · {TRIGGERS[row.trigger || "manual"] || row.trigger}
          </small>
        </div>
      ),
    },
    {
      key: "status",
      title: "Результат",
      render: (row) => <StatusBadge tone={RUN_TONE[row.status]}>{label("integration_run_status", row.status)}</StatusBadge>,
    },
    { key: "received", title: "Получено", className: "col-num", render: (row) => formatNumber(row.records_received) },
    { key: "created", title: "Добавлено", className: "col-num", render: (row) => formatNumber(row.records_created) },
    { key: "updated", title: "Обновлено", className: "col-num", render: (row) => formatNumber(row.records_updated) },
    { key: "failed", title: "Ошибки", className: "col-num", render: (row) => formatNumber(row.records_failed) },
    {
      key: "pending",
      title: "Ждут решения",
      className: "col-num",
      render: (row) => formatNumber(row.records_pending || 0),
    },
    {
      key: "notes",
      title: "Подробности",
      render: (row) =>
        row.error_message ? (
          <span className="field__error">{row.error_message}</span>
        ) : (
          <span className="muted" style={{ whiteSpace: "pre-wrap" }}>
            {row.notes || "—"}
          </span>
        ),
    },
  ];

  const setTab = (key: string) => {
    const next = new URLSearchParams(params);
    next.set("tab", key);
    setParams(next, { replace: true });
  };

  return (
    <div className="page">
      <PageHeader
        title="LMS и сайт"
        description={`${
          interval > 0
            ? `Обмен идёт по расписанию - раз в ${countLabel(interval, ["час", "часа", "часов"])}, и вручную`
            : "Обмен запускается вручную; расписание включает администратор в «Настройках»"
        }. Повторный запуск обновляет те же записи и не плодит дубли.`}
        actions={
          can("sync_integrations") && (
            <Button
              icon={RefreshCw}
              disabled={!sources.data?.some((source) => source.is_enabled)}
              loading={syncEverything.isPending}
              onClick={() => syncEverything.mutate(undefined)}
            >
              Синхронизировать всё
            </Button>
          )
        }
      />
      {sources.isPending ? (
        <Loading />
      ) : sources.isError ? (
        <ErrorState error={sources.error} onRetry={() => void sources.refetch()} />
      ) : (
        <div className="grid-2 sources" style={{ marginBottom: 20 }}>
          {sources.data.map((source) => {
            const last = runs.data?.find((run) => run.source_code === source.code);
            return (
              <Card
                key={source.code}
                className="card--fill source-card"
                title={source.name}
                actions={
                  source.is_enabled ? <StatusBadge tone="success">Включён</StatusBadge> : <StatusBadge>Выключен</StatusBadge>
                }
              >
                <div className="stack-s">
                  <p className="soft">{DESCRIPTIONS[source.code] || ""}</p>
                  <p className="muted" style={{ fontSize: 13 }}>
                    {source.uses_fixture
                      ? "Тестовый режим: адрес API не задан, обмен идёт на примере ответа в формате источника. Ответ настоящего API можно загрузить файлом JSON."
                      : `Адрес API: ${source.base_url}`}
                  </p>
                  {last && (
                    <div className="source-card__last">
                      <p className="source-card__summary">
                        Последний обмен {formatDateTime(last.started_at)}:{" "}
                        {last.status === "failed" ? (
                          <span className="field__error">{last.error_message}</span>
                        ) : (
                          describeRun(last)
                        )}
                      </p>
                      <button
                        type="button"
                        className="link-btn"
                        aria-label={`Подробнее о последнем обмене: ${source.name}`}
                        onClick={() => setRunId(last.id)}
                      >
                        Подробнее
                      </button>
                    </div>
                  )}
                  <div className="row source-card__actions">
                    {can("sync_integrations") && (
                      <>
                        <Button
                          variant="secondary"
                          icon={PlugZap}
                          disabled={!source.is_enabled}
                          loading={sync.isPending && sync.variables === source.code}
                          onClick={() => sync.mutate(source.code)}
                        >
                          Синхронизировать
                        </Button>
                        <Button
                          variant="outline"
                          icon={FileJson}
                          disabled={!source.is_enabled}
                          onClick={() => setUploadFor(source)}
                        >
                          Загрузить JSON
                        </Button>
                      </>
                    )}
                    {can("edit_settings") && (
                      <Switch
                        label="Обмен включён"
                        checked={source.is_enabled}
                        onChange={(enabled) => toggle.mutate({ code: source.code, enabled })}
                      />
                    )}
                  </div>
                </div>
              </Card>
            );
          })}
        </div>
      )}

      <Tabs
        value={tab}
        onChange={setTab}
        items={[
          { key: "runs", label: "Журнал обмена", hidden: !can("view_integration_log") },
          {
            key: "mappings",
            label: "Сопоставление",
            hidden: !can("resolve_mappings"),
            count: pending.data?.length || undefined,
            dot: Boolean(pending.data?.length),
          },
        ]}
      />

      {tab === "runs" && can("view_integration_log") && (
        <Card
          title="Журнал обмена"
          description="Каждый запуск: что получено, что изменилось и какие записи не загрузились."
          flush
        >
          {runs.isPending ? (
            <Loading />
          ) : runs.isError ? (
            <ErrorState error={runs.error} onRetry={() => void runs.refetch()} />
          ) : (
            <DataTable
              caption="Журнал обмена"
              columns={columns}
              rows={runs.data}
              rowKey={(row) => row.id}
              onRowClick={(row) => setRunId(row.id)}
              empty={<EmptyState title="Обменов ещё не было">Запустите синхронизацию или загрузите файл JSON.</EmptyState>}
            />
          )}
        </Card>
      )}
      {tab === "mappings" && can("resolve_mappings") && <MappingQueue />}

      <RunDrawer runId={runId} onClose={() => setRunId(null)} />
      <Modal
        open={uploadFor !== null}
        onClose={() => setUploadFor(null)}
        title={`Загрузка ответа: ${uploadFor?.name || ""}`}
        description={
          uploadFor?.code === "site"
            ? "Файл JSON - список заявок с полями «Номер заявки», «Курс», «Фамилия», «Имя», «Отчество», «Телефон», «Email», «Номер потока» (как в выгрузке сайта)."
            : "Файл JSON в формате ответа API LMS: программы, продукты и анкеты обучающихся."
        }
        footer={
          <>
            <Button variant="outline" onClick={() => setUploadFor(null)}>
              Отмена
            </Button>
            <Button
              disabled={files.length === 0}
              loading={upload.isPending}
              onClick={() => uploadFor && files[0] && upload.mutate({ code: uploadFor.code, file: files[0] })}
            >
              Загрузить
            </Button>
          </>
        }
      >
        <FilePicker
          files={files}
          onChange={setFiles}
          multiple={false}
          accept={["json"]}
          title="Перетащите файл JSON или выберите на компьютере"
        />
      </Modal>
    </div>
  );
}
