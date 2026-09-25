/**
 * Обмен с LMS и сайтом ИТ Школы (п. 5 функциональных требований ТЗ).
 *
 * Из LMS приходят программы, потоки и обучающиеся; с сайта - заявки.
 * Новая заявка вуза заводит черновик договора и запускает процесс -
 * существующие данные обновляются, дублей нет. Ответ источника можно
 * загрузить и файлом JSON, пока сетевой доступ к API не открыт.
 */
import { useQuery } from "@tanstack/react-query";
import { FileJson, PlugZap, RefreshCw } from "lucide-react";
import { useState } from "react";
import { listRuns, listSources, syncAll, syncSource, updateSource, uploadSourcePayload } from "../api/endpoints";
import { useApiMutation } from "../api/mutations";
import { invalidateContractData, keys, queryClient, useLabel } from "../api/queries";
import type { IntegrationRun, IntegrationSource } from "../api/types";
import { useSession } from "../auth/session";
import { DataTable, type Column } from "../components/DataTable";
import { FilePicker } from "../components/FilePicker";
import { Modal } from "../components/Modal";
import { Button, Card, EmptyState, ErrorState, Loading, PageHeader, StatusBadge, Switch } from "../components/ui";
import { formatDateTime, formatNumber } from "../lib/format";
import { usePageTitle } from "../lib/usePageTitle";

const DESCRIPTIONS: Record<string, string> = {
  lms: "ИТ-программы, потоки и обучающиеся. Из анкеты обучающегося берутся только нужные для статистики поля - паспорт, СНИЛС и адрес не сохраняются.",
  site: "Заявки на обучение: курс, поток, контакты заявителя. Заявка от вуза без договора заводит черновик договора и запускает процесс.",
};

function describeRun(run: IntegrationRun): string {
  return `получено ${formatNumber(run.records_received)}, добавлено ${formatNumber(run.records_created)}, обновлено ${formatNumber(
    run.records_updated,
  )}${run.records_failed ? `, с ошибками ${formatNumber(run.records_failed)}` : ""}`;
}

function afterSync() {
  invalidateContractData();
  void queryClient.invalidateQueries({ queryKey: keys.runs });
  void queryClient.invalidateQueries({ queryKey: keys.sources });
  void queryClient.invalidateQueries({ queryKey: ["catalog"] });
}

export default function IntegrationsPage() {
  const { can } = useSession();
  const label = useLabel();
  const [uploadFor, setUploadFor] = useState<IntegrationSource | null>(null);
  const [files, setFiles] = useState<File[]>([]);
  usePageTitle("LMS и сайт");

  const sources = useQuery({ queryKey: keys.sources, queryFn: listSources });
  const runs = useQuery({ queryKey: keys.runs, queryFn: () => listRuns({ limit: 50 }) });

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
          <strong>{sourceName(row.source_code)}</strong>
          <small>{formatDateTime(row.started_at)}</small>
        </div>
      ),
    },
    {
      key: "status",
      title: "Результат",
      render: (row) => (
        <StatusBadge tone={row.status === "success" ? "success" : row.status === "failed" ? "error" : "info"}>
          {label("integration_run_status", row.status)}
        </StatusBadge>
      ),
    },
    { key: "received", title: "Получено", className: "col-num", render: (row) => formatNumber(row.records_received) },
    { key: "created", title: "Добавлено", className: "col-num", render: (row) => formatNumber(row.records_created) },
    { key: "updated", title: "Обновлено", className: "col-num", render: (row) => formatNumber(row.records_updated) },
    { key: "failed", title: "Ошибки", className: "col-num", render: (row) => formatNumber(row.records_failed) },
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

  return (
    <div className="page">
      <PageHeader
        title="LMS и сайт"
        description="Загрузка данных из LMS и с сайта ИТ Школы в существующий или новый рабочий процесс. Повторная загрузка не создаёт дублей."
        actions={
          can("sync_integrations") && (
            <Button icon={RefreshCw} loading={syncEverything.isPending} onClick={() => syncEverything.mutate(undefined)}>
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
        <div className="grid-2" style={{ marginBottom: 20 }}>
          {sources.data.map((source) => {
            const last = runs.data?.find((run) => run.source_code === source.code);
            return (
              <Card
                key={source.code}
                title={source.name}
                actions={
                  source.is_enabled ? <StatusBadge tone="success">Включён</StatusBadge> : <StatusBadge>Выключен</StatusBadge>
                }
              >
                <div className="stack-s">
                  <p className="soft">{DESCRIPTIONS[source.code] || ""}</p>
                  <p className="muted" style={{ fontSize: 13 }}>
                    {source.uses_fixture
                      ? "Адрес API не задан - используются тестовые данные. Ответ API можно загрузить файлом JSON."
                      : `Адрес API: ${source.base_url}`}
                  </p>
                  {last && (
                    <p style={{ fontSize: 13 }}>
                      Последний обмен {formatDateTime(last.started_at)}:{" "}
                      {last.status === "failed" ? <span className="field__error">{last.error_message}</span> : describeRun(last)}
                    </p>
                  )}
                  <div className="row" style={{ marginTop: 8 }}>
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
                        <Button variant="outline" icon={FileJson} onClick={() => setUploadFor(source)}>
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

      <Card title="Журнал обмена" description="Каждый запуск: сколько записей получено и что изменилось." flush>
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
            empty={<EmptyState title="Обменов ещё не было">Запустите синхронизацию или загрузите файл JSON.</EmptyState>}
          />
        )}
      </Card>

      <Modal
        open={uploadFor !== null}
        onClose={() => setUploadFor(null)}
        title={`Загрузка ответа: ${uploadFor?.name || ""}`}
        description={
          uploadFor?.code === "site"
            ? "Файл JSON - список заявок с полями «Номер заявки», «Курс», «Фамилия», «Имя», «Отчество», «Телефон», «Email», «Номер потока» (как в выгрузке сайта)."
            : "Файл JSON в формате ответа API LMS: программы, потоки и обучающиеся."
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
