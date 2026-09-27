/**
 * Загрузка каталогов из Excel (п. 1 функциональных требований ТЗ).
 *
 * Четыре шага: что загружаем → файл → сопоставление колонок → проверка и
 * загрузка. Колонки файла сопоставляются с полями системы автоматически
 * по названиям; сопоставление можно поправить. Проверка ничего не
 * записывает - показывает, что будет добавлено, обновлено и где ошибки.
 */
import { useQuery } from "@tanstack/react-query";
import { CheckCircle2, Download, FileSpreadsheet, Upload } from "lucide-react";
import { useState } from "react";
import {
  commitImport,
  downloadImportTemplate,
  listImportRuns,
  listImportTypes,
  uploadImport,
  validateImport,
} from "../../api/endpoints";
import { useApiMutation, useDownload } from "../../api/mutations";
import { invalidateInteractionData, keys, queryClient, useLabel } from "../../api/queries";
import type { ImportPreview, ImportResult, ImportType } from "../../api/types";
import { FilePicker } from "../../components/FilePicker";
import { Button, Card, EmptyState, ErrorState, Loading, PageHeader, StatusBadge } from "../../components/ui";
import { formatDateTime, formatNumber } from "../../lib/format";
import { IMPORT_TYPE_LABELS } from "../../lib/labels";
import { usePageTitle } from "../../lib/usePageTitle";

type Step = 1 | 2 | 3 | 4;

function Steps({ step }: { step: Step }) {
  const items = ["Что загружаем", "Файл", "Колонки", "Проверка и загрузка"];
  return (
    <ol className="steps">
      {items.map((item, index) => {
        const number = (index + 1) as Step;
        return (
          <li key={item} className={number < step ? "done" : number === step ? "current" : undefined}>
            <span>{number < step ? <CheckCircle2 size={14} /> : number}</span>
            {item}
          </li>
        );
      })}
    </ol>
  );
}

function ResultSummary({ result, committed }: { result: ImportResult; committed: boolean }) {
  const run = result.run;
  return (
    <div className="stack">
      <div className="kpi-row">
        <div className="kpi">
          <span className="kpi__label">Строк в файле</span>
          <span className="kpi__value">{formatNumber(run.rows_total)}</span>
        </div>
        <div className="kpi">
          <span className="kpi__label">{committed ? "Добавлено" : "Будет добавлено"}</span>
          <span className="kpi__value">{formatNumber(run.rows_created)}</span>
        </div>
        <div className="kpi">
          <span className="kpi__label">{committed ? "Обновлено" : "Будет обновлено"}</span>
          <span className="kpi__value">{formatNumber(run.rows_updated)}</span>
        </div>
        <div className={`kpi ${run.rows_failed ? "kpi--alert" : ""}`}>
          <span className="kpi__label">С ошибками</span>
          <span className="kpi__value">{formatNumber(run.rows_failed)}</span>
        </div>
      </div>
      {(result.errors || []).length > 0 && (
        <Card
          title="Замечания по строкам"
          description="Строки с ошибками пропускаются, остальные загружаются. Предупреждения (например, «сотрудник не найден») загрузке строки не мешают."
          flush
        >
          <div className="table-wrap" style={{ maxHeight: 320, overflowY: "auto" }}>
            <table className="data-table">
              <thead>
                <tr>
                  <th scope="col" className="col-num">
                    Строка
                  </th>
                  <th scope="col">Поле</th>
                  <th scope="col">Что не так</th>
                </tr>
              </thead>
              <tbody>
                {(result.errors || []).map((error, index) => (
                  <tr key={index}>
                    <td className="col-num">{error.row_number}</td>
                    <td>{error.field_name || "—"}</td>
                    <td>{error.message}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </Card>
      )}
    </div>
  );
}

export default function ImportsPage() {
  const label = useLabel();
  const [download] = useDownload();
  const [step, setStep] = useState<Step>(1);
  const [type, setType] = useState<ImportType | null>(null);
  const [files, setFiles] = useState<File[]>([]);
  const [preview, setPreview] = useState<ImportPreview | null>(null);
  const [mapping, setMapping] = useState<Record<string, string | null>>({});
  const [result, setResult] = useState<ImportResult | null>(null);
  const [committed, setCommitted] = useState(false);
  usePageTitle("Загрузка из Excel");

  const types = useQuery({ queryKey: ["import-types"], queryFn: listImportTypes, staleTime: Infinity });
  const runs = useQuery({ queryKey: keys.imports, queryFn: listImportRuns });

  const restart = () => {
    setStep(1);
    setType(null);
    setFiles([]);
    setPreview(null);
    setMapping({});
    setResult(null);
    setCommitted(false);
  };

  const upload = useApiMutation(() => uploadImport(files[0], type!), {
    onSuccess: (data) => {
      setPreview(data);
      setMapping(data.suggested_mapping);
      setStep(3);
      void queryClient.invalidateQueries({ queryKey: keys.imports });
    },
    errorTitle: "Файл не прочитан",
  });
  const validate = useApiMutation(() => validateImport(preview!.run.id, mapping), {
    onSuccess: (data) => {
      setResult(data);
      setCommitted(false);
      setStep(4);
    },
    errorTitle: "Проверка не выполнена",
  });
  const commit = useApiMutation(() => commitImport(preview!.run.id, mapping), {
    success: (data) => `Загружено: добавлено ${data.run.rows_created}, обновлено ${data.run.rows_updated}`,
    onSuccess: (data) => {
      setResult(data);
      setCommitted(true);
      void queryClient.invalidateQueries({ queryKey: keys.imports });
      void queryClient.invalidateQueries({ queryKey: ["catalog"] });
      invalidateInteractionData();
    },
    errorTitle: "Загрузка не выполнена",
  });

  const info = types.data?.find((item) => item.import_type === type);
  const missingRequired = (preview?.fields || []).filter((field) => field.required && !mapping[field.key]);

  return (
    <div className="page">
      <PageHeader
        title="Загрузка из Excel"
        actions={
          step > 1 && (
            <Button variant="outline" onClick={restart}>
              Начать заново
            </Button>
          )
        }
      />
      <Steps step={step} />

      {step === 1 && (
        <>
          {types.isPending ? (
            <Loading />
          ) : types.isError ? (
            <ErrorState error={types.error} />
          ) : (
            <div className="grid-3">
              {types.data.map((item) => (
                <Card
                  key={item.import_type}
                  title={item.title || IMPORT_TYPE_LABELS[item.import_type]}
                  footer={
                    <>
                      <Button
                        variant="ghost"
                        size="s"
                        icon={Download}
                        onClick={() => void download(() => downloadImportTemplate(item.import_type))}
                      >
                        Образец
                      </Button>
                      <Button
                        size="s"
                        onClick={() => {
                          setType(item.import_type);
                          setStep(2);
                        }}
                      >
                        Выбрать
                      </Button>
                    </>
                  }
                >
                  <p className="soft">{item.description}</p>
                  <p className="muted" style={{ marginTop: 8, fontSize: 12 }}>
                    Поля: {item.fields.map((field) => (field.required ? `${field.title}*` : field.title)).join(", ")}
                  </p>
                </Card>
              ))}
            </div>
          )}
        </>
      )}

      {step === 2 && type && (
        <Card
          title={`Файл: ${info?.title || IMPORT_TYPE_LABELS[type]}`}
          description="Первая строка листа - заголовки колонок. Колонки можно называть по-своему: на следующем шаге их сопоставим с полями."
          footer={
            <>
              <Button variant="ghost" icon={Download} onClick={() => void download(() => downloadImportTemplate(type))}>
                Скачать образец
              </Button>
              <Button variant="outline" onClick={() => setStep(1)}>
                Назад
              </Button>
              <Button
                icon={Upload}
                disabled={files.length === 0}
                loading={upload.isPending}
                onClick={() => upload.mutate(undefined)}
              >
                Прочитать файл
              </Button>
            </>
          }
        >
          <FilePicker
            files={files}
            onChange={setFiles}
            multiple={false}
            accept={["xlsx", "xls"]}
            title="Перетащите файл XLSX или XLS"
          />
        </Card>
      )}

      {step === 3 && preview && (
        <div className="stack">
          <Card
            title="Сопоставление колонок"
            description={`Файл «${preview.run.filename}»: ${formatNumber(preview.rows_total)} строк. Поля со звёздочкой обязательны.`}
            footer={
              <>
                <Button variant="outline" onClick={() => setStep(2)}>
                  Назад
                </Button>
                <Button
                  disabled={missingRequired.length > 0}
                  loading={validate.isPending}
                  onClick={() => validate.mutate(undefined)}
                >
                  Проверить
                </Button>
              </>
            }
          >
            <div className="table-wrap">
              <table className="data-table mapping-table">
                <thead>
                  <tr>
                    <th scope="col">Поле системы</th>
                    <th scope="col">Колонка файла</th>
                  </tr>
                </thead>
                <tbody>
                  {preview.fields.map((field) => (
                    <tr key={field.key}>
                      <td>
                        {field.title}
                        {field.required && <span className="field__error"> *</span>}
                        {(field.aliases || []).length > 0 && (
                          <div className="muted" style={{ fontSize: 12 }}>
                            узнаём по: {(field.aliases || []).slice(0, 4).join(", ")}
                          </div>
                        )}
                      </td>
                      <td>
                        <select
                          className={`control control--s ${field.required && !mapping[field.key] ? "control--invalid" : ""}`}
                          aria-label={`Колонка для поля ${field.title}`}
                          value={mapping[field.key] || ""}
                          onChange={(event) => setMapping((current) => ({ ...current, [field.key]: event.target.value || null }))}
                        >
                          <option value="">— не загружать —</option>
                          {preview.headers.map((header) => (
                            <option key={header} value={header}>
                              {header}
                            </option>
                          ))}
                        </select>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
            {missingRequired.length > 0 && (
              <p className="field__error" style={{ marginTop: 12 }}>
                Укажите колонки для обязательных полей: {missingRequired.map((field) => field.title).join(", ")}
              </p>
            )}
          </Card>
          <Card title="Первые строки файла" flush>
            <div className="sample">
              <table>
                <thead>
                  <tr>
                    {preview.headers.map((header) => (
                      <th key={header}>{header}</th>
                    ))}
                  </tr>
                </thead>
                <tbody>
                  {preview.sample_rows.map((row, index) => (
                    <tr key={index}>
                      {row.map((cell, column) => (
                        <td key={column}>{cell}</td>
                      ))}
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </Card>
        </div>
      )}

      {step === 4 && result && (
        <div className="stack">
          <ResultSummary result={result} committed={committed} />
          <div className="row">
            {committed ? (
              <>
                <StatusBadge tone="success">Загрузка завершена</StatusBadge>
                <Button variant="secondary" icon={FileSpreadsheet} onClick={restart}>
                  Загрузить другой файл
                </Button>
              </>
            ) : (
              <>
                <Button variant="outline" onClick={() => setStep(3)}>
                  Изменить сопоставление
                </Button>
                <Button
                  loading={commit.isPending}
                  disabled={result.run.rows_created + result.run.rows_updated === 0}
                  onClick={() => commit.mutate(undefined)}
                >
                  Загрузить в систему
                </Button>
              </>
            )}
          </div>
        </div>
      )}

      <Card title="История загрузок" flush className="mt-l" id="history">
        {runs.isPending ? (
          <Loading />
        ) : runs.isError ? (
          <ErrorState error={runs.error} onRetry={() => void runs.refetch()} />
        ) : runs.data.length === 0 ? (
          <EmptyState title="Загрузок не было" />
        ) : (
          <div className="table-wrap">
            <table className="data-table data-table--cards">
              <thead>
                <tr>
                  <th scope="col">Файл</th>
                  <th scope="col">Что</th>
                  <th scope="col">Результат</th>
                  <th scope="col" className="col-num">
                    Добавлено
                  </th>
                  <th scope="col" className="col-num">
                    Обновлено
                  </th>
                  <th scope="col" className="col-num">
                    Ошибки
                  </th>
                  <th scope="col">Когда</th>
                </tr>
              </thead>
              <tbody>
                {runs.data.map((run) => (
                  <tr key={run.id}>
                    <td className="cell-primary">
                      <strong style={{ overflowWrap: "anywhere" }}>{run.filename}</strong>
                    </td>
                    <td data-label="Что">{IMPORT_TYPE_LABELS[run.import_type] || run.import_type}</td>
                    <td data-label="Результат">
                      <StatusBadge tone={run.status === "completed" ? "success" : run.status === "failed" ? "error" : "info"}>
                        {label("import_run_status", run.status)}
                      </StatusBadge>
                    </td>
                    <td className="col-num" data-label="Добавлено">
                      {formatNumber(run.rows_created)}
                    </td>
                    <td className="col-num" data-label="Обновлено">
                      {formatNumber(run.rows_updated)}
                    </td>
                    <td className="col-num" data-label="Ошибки">
                      {formatNumber(run.rows_failed)}
                    </td>
                    <td data-label="Когда">{formatDateTime(run.created_at)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </Card>
    </div>
  );
}
