/**
 * Шаблоны рабочих процессов (п. 7 функциональных требований ТЗ:
 * создание и изменение рабочих процессов).
 *
 * Шаблон живёт версиями. Опубликованная версия не меняется - по ней идут
 * договоры; изменения делаются в новой версии-черновике и публикуются.
 * Уже запущенные процессы остаются на своей версии, новые договоры
 * получают последнюю опубликованную.
 */
import { useQuery } from "@tanstack/react-query";
import { ArrowDown, ArrowUp, CopyPlus, Plus, Rocket, Save, Trash2 } from "lucide-react";
import { useEffect, useMemo, useState } from "react";
import {
  createTemplate,
  createVersion,
  deleteVersion,
  getVersion,
  listTemplates,
  listVersions,
  publishVersion,
  saveGraph,
  saveLayout,
  updateTemplate,
} from "../../api/endpoints";
import { useApiMutation } from "../../api/mutations";
import { keys, queryClient } from "../../api/queries";
import type { GraphWrite, StageWrite, TransitionWrite, VersionGraph } from "../../api/types";
import { useSession } from "../../auth/session";
import { useConfirm } from "../../components/Confirm";
import { Modal } from "../../components/Modal";
import {
  Button,
  Card,
  EmptyState,
  ErrorState,
  Loading,
  PageHeader,
  SelectField,
  StatusBadge,
  Switch,
  TextAreaField,
  TextField,
} from "../../components/ui";
import { ProcessCanvas } from "../../features/workflow/ProcessCanvas";
import type { Point } from "../../features/workflow/layout";
import { formatDateTime } from "../../lib/format";
import { usePageTitle } from "../../lib/usePageTitle";

function toWrite(version: VersionGraph): GraphWrite {
  const stages = [...(version.stages || [])].sort((a, b) => a.sort_order - b.sort_order);
  const code = Object.fromEntries(stages.map((stage) => [stage.id, stage.code]));
  return {
    stages: stages.map((stage) => ({
      code: stage.code,
      name: stage.name,
      description: stage.description,
      sla_days: stage.sla_days,
      is_optional: stage.is_optional,
      is_final: stage.is_final,
      sort_order: stage.sort_order,
      layout_x: stage.layout_x,
      layout_y: stage.layout_y,
    })),
    transitions: (version.transitions || []).map((transition) => ({
      from_code: code[transition.from_stage_id],
      to_code: code[transition.to_stage_id],
      is_backward: transition.is_backward,
      requires_comment: transition.requires_comment,
      name: transition.name,
    })),
  };
}

function problems(graph: GraphWrite): string[] {
  const found: string[] = [];
  const codes = graph.stages.map((stage) => stage.code.trim());
  if (graph.stages.length === 0) found.push("Добавьте хотя бы один этап");
  if (codes.some((item) => !item)) found.push("У каждого этапа должен быть код");
  if (new Set(codes).size !== codes.length) found.push("Коды этапов повторяются");
  if (graph.stages.some((stage) => !stage.name.trim())) found.push("У каждого этапа должно быть название");
  if (!graph.stages.some((stage) => stage.is_final)) found.push("Отметьте завершающий этап");
  (graph.transitions || []).forEach((transition) => {
    if (!codes.includes(transition.from_code) || !codes.includes(transition.to_code))
      found.push("Переход ссылается на несуществующий этап");
    if (transition.from_code === transition.to_code) found.push("Переход этапа сам в себя");
  });
  const pairs = (graph.transitions || []).map((item) => `${item.from_code}>${item.to_code}`);
  if (new Set(pairs).size !== pairs.length) found.push("Один и тот же переход задан дважды");
  return Array.from(new Set(found));
}

function newCode(stages: StageWrite[]): string {
  let index = stages.length + 1;
  while (stages.some((stage) => stage.code === `stage_${index}`)) index += 1;
  return `stage_${index}`;
}

function GraphEditor({
  graph,
  onChange,
  readOnly,
}: {
  graph: GraphWrite;
  onChange: (graph: GraphWrite) => void;
  readOnly: boolean;
}) {
  const stages = graph.stages;
  const transitions = graph.transitions || [];
  const setStage = (index: number, patch: Partial<StageWrite>) =>
    onChange({ ...graph, stages: stages.map((stage, position) => (position === index ? { ...stage, ...patch } : stage)) });
  const setTransition = (index: number, patch: Partial<TransitionWrite>) =>
    onChange({ ...graph, transitions: transitions.map((item, position) => (position === index ? { ...item, ...patch } : item)) });
  const move = (index: number, delta: number) => {
    const next = [...stages];
    const [item] = next.splice(index, 1);
    next.splice(index + delta, 0, item);
    onChange({ ...graph, stages: next.map((stage, position) => ({ ...stage, sort_order: (position + 1) * 10 })) });
  };
  const renameCode = (index: number, code: string) => {
    const old = stages[index].code;
    onChange({
      stages: stages.map((stage, position) => (position === index ? { ...stage, code } : stage)),
      transitions: transitions.map((item) => ({
        ...item,
        from_code: item.from_code === old ? code : item.from_code,
        to_code: item.to_code === old ? code : item.to_code,
      })),
    });
  };
  const stageOptions = stages.map((stage) => ({ value: stage.code, label: stage.name || stage.code }));

  return (
    <div className="stack">
      <Card title={`Этапы: ${stages.length}`} flush>
        <div className="table-wrap">
          <table className="data-table">
            <thead>
              <tr>
                <th scope="col">№</th>
                <th scope="col">Название</th>
                <th scope="col">Код</th>
                <th scope="col">Норма, дней</th>
                <th scope="col">Необязательный</th>
                <th scope="col">Завершающий</th>
                {!readOnly && (
                  <th scope="col" className="col-actions">
                    <span className="visually-hidden">Действия</span>
                  </th>
                )}
              </tr>
            </thead>
            <tbody>
              {stages.map((stage, index) => (
                <tr key={index}>
                  <td className="num">{index + 1}</td>
                  <td style={{ minWidth: 220 }}>
                    {readOnly ? (
                      stage.name
                    ) : (
                      <input
                        className="control control--s"
                        aria-label="Название этапа"
                        value={stage.name}
                        maxLength={255}
                        onChange={(event) => setStage(index, { name: event.target.value })}
                      />
                    )}
                  </td>
                  <td style={{ minWidth: 140 }}>
                    {readOnly ? (
                      <span className="mono">{stage.code}</span>
                    ) : (
                      <input
                        className="control control--s mono"
                        aria-label="Код этапа"
                        value={stage.code}
                        maxLength={100}
                        onChange={(event) => renameCode(index, event.target.value.replace(/[^a-zA-Z0-9_-]/g, ""))}
                      />
                    )}
                  </td>
                  <td style={{ width: 110 }}>
                    {readOnly ? (
                      (stage.sla_days ?? "—")
                    ) : (
                      <input
                        className="control control--s"
                        aria-label="Норма в днях"
                        type="number"
                        min={0}
                        value={stage.sla_days ?? ""}
                        onChange={(event) =>
                          setStage(index, { sla_days: event.target.value ? Number(event.target.value) : null })
                        }
                      />
                    )}
                  </td>
                  <td>
                    <input
                      type="checkbox"
                      aria-label="Необязательный этап"
                      checked={Boolean(stage.is_optional)}
                      disabled={readOnly}
                      onChange={(event) => setStage(index, { is_optional: event.target.checked })}
                    />
                  </td>
                  <td>
                    <input
                      type="checkbox"
                      aria-label="Завершающий этап"
                      checked={Boolean(stage.is_final)}
                      disabled={readOnly}
                      onChange={(event) => setStage(index, { is_final: event.target.checked })}
                    />
                  </td>
                  {!readOnly && (
                    <td className="col-actions">
                      <button
                        type="button"
                        className="icon-btn"
                        aria-label="Выше"
                        disabled={index === 0}
                        onClick={() => move(index, -1)}
                      >
                        <ArrowUp size={15} />
                      </button>
                      <button
                        type="button"
                        className="icon-btn"
                        aria-label="Ниже"
                        disabled={index === stages.length - 1}
                        onClick={() => move(index, 1)}
                      >
                        <ArrowDown size={15} />
                      </button>
                      <button
                        type="button"
                        className="icon-btn"
                        aria-label="Удалить этап"
                        onClick={() =>
                          onChange({
                            stages: stages.filter((_, position) => position !== index),
                            transitions: transitions.filter(
                              (item) => item.from_code !== stage.code && item.to_code !== stage.code,
                            ),
                          })
                        }
                      >
                        <Trash2 size={15} />
                      </button>
                    </td>
                  )}
                </tr>
              ))}
            </tbody>
          </table>
        </div>
        {!readOnly && (
          <div className="card__footer" style={{ justifyContent: "flex-start" }}>
            <Button
              variant="secondary"
              icon={Plus}
              onClick={() => {
                const code = newCode(stages);
                const last = stages[stages.length - 1];
                onChange({
                  stages: [
                    ...stages,
                    { code, name: "", is_optional: false, is_final: false, sort_order: (stages.length + 1) * 10, sla_days: 7 },
                  ],
                  // Новый этап сразу связываем с предыдущим - так быстрее собрать цепочку.
                  transitions: last
                    ? [...transitions, { from_code: last.code, to_code: code, is_backward: false, requires_comment: false }]
                    : transitions,
                });
              }}
            >
              Добавить этап
            </Button>
          </div>
        )}
      </Card>

      <Card
        title={`Переходы: ${transitions.length}`}
        description="Куда можно перейти с этапа. Возврат назад рисуется пунктиром."
        flush
      >
        <div className="table-wrap">
          <table className="data-table">
            <thead>
              <tr>
                <th scope="col">Откуда</th>
                <th scope="col">Куда</th>
                <th scope="col">Подпись кнопки</th>
                <th scope="col">Возврат</th>
                <th scope="col">Нужен комментарий</th>
                {!readOnly && (
                  <th scope="col" className="col-actions">
                    <span className="visually-hidden">Действия</span>
                  </th>
                )}
              </tr>
            </thead>
            <tbody>
              {transitions.map((transition, index) => (
                <tr key={index}>
                  <td style={{ minWidth: 180 }}>
                    {readOnly ? (
                      stages.find((stage) => stage.code === transition.from_code)?.name
                    ) : (
                      <SelectField
                        size="s"
                        value={transition.from_code}
                        onChange={(value) => setTransition(index, { from_code: value })}
                        options={stageOptions}
                      />
                    )}
                  </td>
                  <td style={{ minWidth: 180 }}>
                    {readOnly ? (
                      stages.find((stage) => stage.code === transition.to_code)?.name
                    ) : (
                      <SelectField
                        size="s"
                        value={transition.to_code}
                        onChange={(value) => setTransition(index, { to_code: value })}
                        options={stageOptions}
                      />
                    )}
                  </td>
                  <td style={{ minWidth: 160 }}>
                    {readOnly ? (
                      transition.name || "—"
                    ) : (
                      <input
                        className="control control--s"
                        aria-label="Подпись перехода"
                        value={transition.name || ""}
                        placeholder="По умолчанию - название этапа"
                        onChange={(event) => setTransition(index, { name: event.target.value || null })}
                      />
                    )}
                  </td>
                  <td>
                    <input
                      type="checkbox"
                      aria-label="Возврат назад"
                      checked={Boolean(transition.is_backward)}
                      disabled={readOnly}
                      onChange={(event) => setTransition(index, { is_backward: event.target.checked })}
                    />
                  </td>
                  <td>
                    <input
                      type="checkbox"
                      aria-label="Нужен комментарий"
                      checked={Boolean(transition.requires_comment)}
                      disabled={readOnly}
                      onChange={(event) => setTransition(index, { requires_comment: event.target.checked })}
                    />
                  </td>
                  {!readOnly && (
                    <td className="col-actions">
                      <button
                        type="button"
                        className="icon-btn"
                        aria-label="Удалить переход"
                        onClick={() =>
                          onChange({ ...graph, transitions: transitions.filter((_, position) => position !== index) })
                        }
                      >
                        <Trash2 size={15} />
                      </button>
                    </td>
                  )}
                </tr>
              ))}
            </tbody>
          </table>
        </div>
        {!readOnly && stages.length > 1 && (
          <div className="card__footer" style={{ justifyContent: "flex-start" }}>
            <Button
              variant="secondary"
              icon={Plus}
              onClick={() =>
                onChange({
                  ...graph,
                  transitions: [
                    ...transitions,
                    { from_code: stages[0].code, to_code: stages[1].code, is_backward: false, requires_comment: false },
                  ],
                })
              }
            >
              Добавить переход
            </Button>
          </div>
        )}
      </Card>
    </div>
  );
}

function NewTemplateModal({ open, onClose, onCreated }: { open: boolean; onClose: () => void; onCreated: (id: string) => void }) {
  const templates = useQuery({ queryKey: keys.templates, queryFn: listTemplates });
  const [name, setName] = useState("");
  const [description, setDescription] = useState("");
  const [copyFrom, setCopyFrom] = useState("");
  useEffect(() => {
    if (open) {
      setName("");
      setDescription("");
      setCopyFrom("");
    }
  }, [open]);
  const create = useApiMutation(
    async () => {
      let graph: GraphWrite | null = null;
      if (copyFrom) {
        const versions = await listVersions(copyFrom);
        const latest = [...versions].sort((a, b) => b.version_number - a.version_number)[0];
        if (latest) graph = toWrite(await getVersion(latest.id));
      }
      return createTemplate({ name: name.trim(), description: description.trim() || null, graph });
    },
    {
      success: "Шаблон создан - это черновик первой версии",
      onSuccess: (version) => {
        void queryClient.invalidateQueries({ queryKey: keys.templates });
        onCreated(version.template_id);
        onClose();
      },
    },
  );
  return (
    <Modal
      open={open}
      onClose={onClose}
      title="Новый шаблон процесса"
      footer={
        <>
          <Button variant="outline" onClick={onClose}>
            Отмена
          </Button>
          <Button loading={create.isPending} disabled={!name.trim()} onClick={() => create.mutate(undefined)}>
            Создать
          </Button>
        </>
      }
    >
      <div className="stack">
        <TextField
          label="Название"
          required
          value={name}
          onChange={setName}
          maxLength={255}
          placeholder="Например: работа со школой"
        />
        <TextAreaField label="Описание" value={description} onChange={setDescription} rows={2} />
        <SelectField
          label="Скопировать этапы из"
          value={copyFrom}
          onChange={setCopyFrom}
          placeholder="Начать с пустого"
          options={(templates.data || []).map((item) => ({ value: item.id, label: item.name }))}
        />
      </div>
    </Modal>
  );
}

export default function WorkflowsPage() {
  const confirm = useConfirm();
  const { can } = useSession();
  const [templateId, setTemplateId] = useState<string | null>(null);
  const [versionId, setVersionId] = useState<string | null>(null);
  const [graph, setGraph] = useState<GraphWrite | null>(null);
  const [dirty, setDirty] = useState(false);
  const [positions, setPositions] = useState<Record<string, Point> | null>(null);
  const [creating, setCreating] = useState(false);
  const [templateName, setTemplateName] = useState("");
  usePageTitle("Рабочие процессы");

  const templates = useQuery({ queryKey: keys.templates, queryFn: listTemplates });
  const template = templates.data?.find((item) => item.id === templateId) || null;
  const versions = useQuery({
    queryKey: keys.versions(templateId || ""),
    queryFn: () => listVersions(templateId!),
    enabled: Boolean(templateId),
  });
  const version = useQuery({
    queryKey: ["version", versionId],
    queryFn: () => getVersion(versionId!),
    enabled: Boolean(versionId),
  });

  useEffect(() => {
    if (!templateId && templates.data?.length) setTemplateId(templates.data[0].id);
  }, [templateId, templates.data]);
  useEffect(() => {
    if (template) setTemplateName(template.name);
  }, [template]);
  useEffect(() => {
    if (versions.data?.length && !versions.data.some((item) => item.id === versionId)) {
      const latest = [...versions.data].sort((a, b) => b.version_number - a.version_number)[0];
      setVersionId(latest.id);
    }
  }, [versions.data, versionId]);
  useEffect(() => {
    if (version.data) {
      setGraph(toWrite(version.data));
      setDirty(false);
      setPositions(null);
    }
  }, [version.data]);

  const refresh = () => {
    void queryClient.invalidateQueries({ queryKey: keys.templates });
    void queryClient.invalidateQueries({ queryKey: ["versions"] });
    void queryClient.invalidateQueries({ queryKey: ["version"] });
    void queryClient.invalidateQueries({ queryKey: ["stage-names"] });
  };

  const save = useApiMutation(() => saveGraph(versionId!, graph!), {
    success: "Черновик сохранён",
    onSuccess: (saved) => {
      queryClient.setQueryData(["version", versionId], saved);
      refresh();
    },
  });
  const publish = useApiMutation(
    async () => {
      if (dirty) await saveGraph(versionId!, graph!);
      return publishVersion(versionId!);
    },
    {
      success: "Версия опубликована: новые договоры пойдут по ней",
      onSuccess: refresh,
    },
  );
  const newVersion = useApiMutation(() => createVersion(templateId!, versionId || undefined), {
    success: (created) => `Создан черновик версии ${created.version_number}`,
    onSuccess: (created) => {
      refresh();
      setVersionId(created.id);
    },
  });
  const remove = useApiMutation(() => deleteVersion(versionId!), {
    success: "Черновик удалён",
    onSuccess: () => {
      setVersionId(null);
      refresh();
    },
  });
  const patchTemplate = useApiMutation((body: { name?: string; is_active?: boolean }) => updateTemplate(templateId!, body), {
    success: "Шаблон сохранён",
    onSuccess: refresh,
  });
  const layout = useApiMutation(
    () =>
      saveLayout(
        versionId!,
        Object.entries(positions || {}).map(([stageId, point]) => ({ stage_id: stageId, layout_x: point.x, layout_y: point.y })),
      ),
    {
      success: "Расположение схемы сохранено",
      onSuccess: () => {
        setPositions(null);
        refresh();
      },
    },
  );

  const isDraft = Boolean(version.data && !version.data.published_at);
  const issues = graph ? problems(graph) : [];

  // Для предпросмотра черновика: коды вместо id, раскладка из сохранённых координат.
  const preview = useMemo(() => {
    if (!graph) return null;
    if (!dirty && version.data) {
      return { stages: version.data.stages || [], transitions: version.data.transitions || [], saved: true };
    }
    return {
      stages: graph.stages.map((stage, index) => ({
        id: stage.code,
        name: stage.name || stage.code,
        sort_order: stage.sort_order ?? (index + 1) * 10,
        layout_x: stage.layout_x,
        layout_y: stage.layout_y,
        sla_days: stage.sla_days,
        is_optional: stage.is_optional,
        is_final: stage.is_final,
      })),
      transitions: (graph.transitions || []).map((item, index) => ({
        id: `t${index}`,
        from_stage_id: item.from_code,
        to_stage_id: item.to_code,
        is_backward: Boolean(item.is_backward),
        name: item.name,
      })),
      saved: false,
    };
  }, [graph, dirty, version.data]);

  return (
    <div className="page">
      <PageHeader
        title="Рабочие процессы"
        description="Шаблоны процессов работы с вузами: этапы, нормы сроков, разрешённые переходы. Опубликованная версия не меняется - изменения делаются в новой."
        actions={
          <Button icon={Plus} onClick={() => setCreating(true)}>
            Новый шаблон
          </Button>
        }
      />
      {templates.isPending ? (
        <Loading />
      ) : templates.isError ? (
        <ErrorState error={templates.error} onRetry={() => void templates.refetch()} />
      ) : templates.data.length === 0 ? (
        <EmptyState title="Шаблонов нет" action={<Button onClick={() => setCreating(true)}>Создать</Button>} />
      ) : (
        <div className="stack">
          <div className="toolbar" style={{ marginBottom: 0 }}>
            <SelectField
              label="Шаблон"
              value={templateId || ""}
              onChange={(value) => {
                setTemplateId(value);
                setVersionId(null);
              }}
              options={templates.data.map((item) => ({
                value: item.id,
                label: item.is_active ? item.name : `${item.name} (выключен)`,
              }))}
            />
            <SelectField
              label="Версия"
              value={versionId || ""}
              onChange={setVersionId}
              options={[...(versions.data || [])]
                .sort((a, b) => b.version_number - a.version_number)
                .map((item) => ({
                  value: item.id,
                  label: `Версия ${item.version_number} · ${item.published_at ? `опубликована ${formatDateTime(item.published_at)}` : "черновик"}${
                    item.instances_count ? ` · процессов: ${item.instances_count}` : ""
                  }`,
                }))}
            />
            {template && (
              <>
                <TextField label="Название шаблона" value={templateName} onChange={setTemplateName} maxLength={255} />
                <div style={{ alignSelf: "flex-end" }} className="row">
                  <Button
                    variant="outline"
                    disabled={!templateName.trim() || templateName.trim() === template.name}
                    onClick={() => patchTemplate.mutate({ name: templateName.trim() })}
                  >
                    Переименовать
                  </Button>
                  <Switch
                    label="Действует"
                    checked={template.is_active}
                    onChange={(value) => patchTemplate.mutate({ is_active: value })}
                  />
                </div>
              </>
            )}
          </div>

          {version.isPending && versionId ? (
            <Loading />
          ) : version.isError ? (
            <ErrorState error={version.error} />
          ) : version.data && graph ? (
            <>
              <div className="row-between">
                <div className="row">
                  {isDraft ? (
                    <StatusBadge tone="warning">Черновик</StatusBadge>
                  ) : (
                    <StatusBadge tone="success">Опубликована</StatusBadge>
                  )}
                  <span className="muted">
                    Версия {version.data.version_number}
                    {version.data.instances_count ? ` · используется в ${version.data.instances_count} процессах` : ""}
                  </span>
                </div>
                <div className="row">
                  {isDraft ? (
                    <>
                      <Button
                        variant="danger"
                        icon={Trash2}
                        onClick={async () => {
                          const ok = await confirm({ title: "Удалить черновик версии?", confirmLabel: "Удалить", danger: true });
                          if (ok !== null) remove.mutate(undefined);
                        }}
                      >
                        Удалить
                      </Button>
                      <Button
                        variant="outline"
                        icon={Save}
                        disabled={!dirty || issues.length > 0}
                        loading={save.isPending}
                        onClick={() => save.mutate(undefined)}
                      >
                        Сохранить черновик
                      </Button>
                      <Button
                        icon={Rocket}
                        disabled={issues.length > 0}
                        loading={publish.isPending}
                        onClick={async () => {
                          const ok = await confirm({
                            title: "Опубликовать версию?",
                            message:
                              "После публикации версию нельзя изменить. Новые договоры пойдут по ней, уже запущенные процессы останутся на своей версии.",
                            confirmLabel: "Опубликовать",
                          });
                          if (ok !== null) publish.mutate(undefined);
                        }}
                      >
                        Опубликовать
                      </Button>
                    </>
                  ) : (
                    <Button
                      variant="secondary"
                      icon={CopyPlus}
                      loading={newVersion.isPending}
                      onClick={() => newVersion.mutate(undefined)}
                    >
                      Новая версия на основе этой
                    </Button>
                  )}
                </div>
              </div>
              {issues.length > 0 && isDraft && (
                <div className="quote" style={{ borderLeftColor: "var(--bad)" }}>
                  {issues.join(". ")}.
                </div>
              )}
              {preview && (
                <div className="stack-s">
                  <ProcessCanvas
                    stages={preview.stages}
                    transitions={preview.transitions}
                    editable={preview.saved && can("save_layout")}
                    onPositionsChange={setPositions}
                    resetKey={versionId || undefined}
                    height={460}
                  />
                  <div className="row-between">
                    <span className="muted" style={{ fontSize: 13 }}>
                      {preview.saved
                        ? "Этапы можно перетаскивать мышью и сохранить расположение."
                        : "Предпросмотр несохранённых изменений."}
                    </span>
                    {positions && (
                      <Button size="s" loading={layout.isPending} onClick={() => layout.mutate(undefined)}>
                        Сохранить расположение
                      </Button>
                    )}
                  </div>
                </div>
              )}
              <GraphEditor
                graph={graph}
                readOnly={!isDraft}
                onChange={(next) => {
                  setGraph(next);
                  setDirty(true);
                }}
              />
            </>
          ) : (
            <EmptyState
              title="У шаблона нет версий"
              action={<Button onClick={() => newVersion.mutate(undefined)}>Создать версию</Button>}
            />
          )}
        </div>
      )}
      <NewTemplateModal
        open={creating}
        onClose={() => setCreating(false)}
        onCreated={(id) => {
          setTemplateId(id);
          setVersionId(null);
        }}
      />
    </div>
  );
}
