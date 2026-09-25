/**
 * Вкладка «Процесс»: схема этапов, переходы, блокировка, комментарии
 * и файлы к этапам.
 *
 * Переходы - только те, что разрешены шаблоном (сервер присылает их
 * списком). Комментарий и файлы, добавленные при переходе, привязываются
 * к событию перехода и видны в карточке этапа и в истории.
 */
import { Segment, SegmentedControl } from "@atomaro/ui-kit";
import type { UseQueryResult } from "@tanstack/react-query";
import { ArrowLeftCircle, ArrowRightCircle, Lock, Paperclip, Pencil, Play, SkipForward, Unlock } from "lucide-react";
import { useEffect, useMemo, useState } from "react";
import {
  blockWorkflow,
  createComment,
  downloadAttachment,
  renameStage,
  saveLayout,
  skipStage,
  startWorkflow,
  transition,
  unblockWorkflow,
  uploadAttachment,
} from "../../api/endpoints";
import { useApiMutation, useDownload } from "../../api/mutations";
import { invalidateContractData, queryClient, useLabel, useTemplates } from "../../api/queries";
import type { Attachment, Comment, ContractDetail, Stage, Transition, WorkflowView } from "../../api/types";
import { useSession } from "../../auth/session";
import { useConfirm } from "../../components/Confirm";
import { FilePicker } from "../../components/FilePicker";
import { Modal } from "../../components/Modal";
import { useToast } from "../../components/Toasts";
import {
  Button,
  Card,
  EmptyState,
  ErrorState,
  Loading,
  SelectField,
  StatusBadge,
  TextAreaField,
  TextField,
} from "../../components/ui";
import { ProcessCanvas } from "../../features/workflow/ProcessCanvas";
import type { Point } from "../../features/workflow/layout";
import { countLabel, DAYS, daysSince, fileSize, formatDateTime } from "../../lib/format";
import { WORKFLOW_TONE } from "../../lib/labels";

type Dialog = { transition: Transition; skip: boolean } | null;

const STAGE_TONE = {
  not_started: "neutral",
  active: "accent",
  completed: "success",
  skipped: "neutral",
  blocked: "error",
} as const;

function newestEvent(view: WorkflowView) {
  return [...(view.events || [])].sort((left, right) => right.created_at.localeCompare(left.created_at))[0];
}

/** Запуск процесса по шаблону, если по договору его ещё нет. */
function StartProcess({ contract }: { contract: ContractDetail }) {
  const templates = useTemplates();
  const [templateId, setTemplateId] = useState("");
  const active = (templates.data || []).filter((item) => item.is_active);
  useEffect(() => {
    if (!templateId && active.length) setTemplateId(active[0].id);
  }, [templateId, active]);
  const start = useApiMutation(() => startWorkflow(contract.id, templateId), {
    success: "Процесс запущен",
    onSuccess: () => invalidateContractData(contract.id),
  });
  return (
    <Card>
      <EmptyState icon={Play} title="Рабочий процесс не запущен">
        Выберите шаблон: процесс начнётся с первого этапа, а договор появится в отчётах по этапам.
      </EmptyState>
      <div className="row" style={{ justifyContent: "center", paddingBottom: 12 }}>
        <SelectField
          label="Шаблон процесса"
          value={templateId}
          onChange={setTemplateId}
          options={active.map((item) => ({ value: item.id, label: item.name }))}
        />
        <div style={{ alignSelf: "flex-end" }}>
          <Button icon={Play} disabled={!templateId} loading={start.isPending} onClick={() => start.mutate(undefined)}>
            Запустить
          </Button>
        </div>
      </div>
    </Card>
  );
}

function TransitionDialog({
  dialog,
  view,
  contract,
  onClose,
}: {
  dialog: Dialog;
  view: WorkflowView;
  contract: ContractDetail;
  onClose: () => void;
}) {
  const toast = useToast();
  const [comment, setComment] = useState("");
  const [files, setFiles] = useState<File[]>([]);
  const [busy, setBusy] = useState(false);
  useEffect(() => {
    setComment("");
    setFiles([]);
  }, [dialog]);

  if (!dialog) return null;
  const stages = view.version.stages || [];
  const from = stages.find((stage) => stage.id === dialog.transition.from_stage_id);
  const to = stages.find((stage) => stage.id === dialog.transition.to_stage_id);
  const needsText = dialog.skip || dialog.transition.requires_comment;

  const title = dialog.skip
    ? `Пропустить этап «${from?.name}»`
    : dialog.transition.is_backward
      ? `Вернуть на этап «${to?.name}»`
      : `Перейти на этап «${to?.name}»`;

  const submit = async () => {
    setBusy(true);
    try {
      const result = dialog.skip
        ? await skipStage(view.id, dialog.transition.to_stage_id, comment.trim())
        : await transition(view.id, dialog.transition.to_stage_id, comment.trim());
      const event = newestEvent(result);
      for (const file of files) {
        await uploadAttachment(contract.id, file, event?.id);
      }
      toast.success(
        to?.is_final ? "Процесс завершён" : `Этап: «${to?.name}»`,
        files.length ? `Приложено файлов: ${files.length}` : undefined,
      );
      invalidateContractData(contract.id);
      onClose();
    } catch (error) {
      toast.error(error, "Переход не выполнен");
    } finally {
      setBusy(false);
    }
  };

  return (
    <Modal
      open
      onClose={onClose}
      dismissable={!busy}
      title={title}
      description={
        dialog.skip
          ? `Этап будет отмечен пропущенным, процесс перейдёт на «${to?.name}».`
          : `С «${from?.name}» на «${to?.name}»${to?.is_final ? " - это завершит процесс" : ""}.`
      }
      footer={
        <>
          <Button variant="outline" onClick={onClose} disabled={busy}>
            Отмена
          </Button>
          <Button loading={busy} disabled={needsText && !comment.trim()} onClick={() => void submit()}>
            {dialog.skip ? "Пропустить" : dialog.transition.is_backward ? "Вернуть" : "Перейти"}
          </Button>
        </>
      }
    >
      <div className="stack">
        <TextAreaField
          label={dialog.skip ? "Причина пропуска" : "Комментарий к переходу"}
          required={needsText}
          value={comment}
          onChange={setComment}
          rows={3}
          maxLength={4000}
          placeholder={dialog.skip ? "Почему этап не нужен этому вузу" : "Что сделано, о чём договорились"}
          hint={dialog.transition.requires_comment && !dialog.skip ? "Для этого перехода комментарий обязателен" : undefined}
        />
        <div className="field">
          <span className="field__label">Файлы к этапу</span>
          <FilePicker files={files} onChange={setFiles} />
        </div>
      </div>
    </Modal>
  );
}

function RenameStageDialog({ stage, onClose, contractId }: { stage: Stage | null; onClose: () => void; contractId: string }) {
  const [name, setName] = useState("");
  const [description, setDescription] = useState("");
  useEffect(() => {
    setName(stage?.name || "");
    setDescription(stage?.description || "");
  }, [stage]);
  const save = useApiMutation(() => renameStage(stage!.id, { name: name.trim(), description: description.trim() || null }), {
    success: "Этап переименован",
    onSuccess: () => {
      invalidateContractData(contractId);
      void queryClient.invalidateQueries({ queryKey: ["stage-names"] });
      void queryClient.invalidateQueries({ queryKey: ["version"] });
      onClose();
    },
  });
  return (
    <Modal
      open={stage !== null}
      onClose={onClose}
      title="Название этапа"
      description="Новое название увидят все договоры, которые идут по этой версии шаблона, а также отчёты."
      footer={
        <>
          <Button variant="outline" onClick={onClose}>
            Отмена
          </Button>
          <Button loading={save.isPending} disabled={!name.trim()} onClick={() => save.mutate(undefined)}>
            Сохранить
          </Button>
        </>
      }
    >
      <div className="stack">
        <TextField label="Название" required value={name} onChange={setName} maxLength={255} autoFocus />
        <TextAreaField
          label="Описание"
          value={description}
          onChange={setDescription}
          rows={3}
          maxLength={2000}
          hint="Что нужно сделать на этом этапе"
        />
      </div>
    </Modal>
  );
}

function StagePanel({
  view,
  stage,
  contract,
  comments,
  attachments,
  onTransition,
  onRename,
}: {
  view: WorkflowView;
  stage: Stage;
  contract: ContractDetail;
  comments: Comment[];
  attachments: Attachment[];
  onTransition: (dialog: Dialog) => void;
  onRename: (stage: Stage) => void;
}) {
  const label = useLabel();
  const { can } = useSession();
  const confirm = useConfirm();
  const toast = useToast();
  const [download] = useDownload();
  const [note, setNote] = useState("");
  const [files, setFiles] = useState<File[]>([]);
  const [busy, setBusy] = useState(false);

  const stages = view.version.stages || [];
  const stageName = (id?: string | null) => stages.find((item) => item.id === id)?.name || "—";
  const state = view.stage_states?.find((item) => item.stage_id === stage.id)?.state || "not_started";
  const isCurrent = view.current_stage_id === stage.id;
  const ordered = [...stages].sort((a, b) => a.sort_order - b.sort_order);
  const number = ordered.findIndex((item) => item.id === stage.id) + 1;

  const events = (view.events || []).filter((event) => event.to_stage_id === stage.id || event.from_stage_id === stage.id);
  const eventIds = new Set(events.map((event) => event.id));
  const arrival = [...(view.events || [])]
    .filter((event) => event.to_stage_id === stage.id)
    .sort((a, b) => b.created_at.localeCompare(a.created_at))[0];
  const stageComments = comments.filter((item) => item.workflow_event_id && eventIds.has(item.workflow_event_id));
  const stageFiles = attachments.filter((item) => item.workflow_event_id && eventIds.has(item.workflow_event_id));
  const transitions = isCurrent ? view.available_transitions || [] : [];
  const forward = transitions.filter((item) => !item.is_backward);
  const backward = transitions.filter((item) => item.is_backward);
  const canSkip = stage.is_optional || can("skip_any_stage");
  const days = isCurrent && view.current_stage_started_at ? daysSince(view.current_stage_started_at) : null;
  const blockEvent = [...(view.events || [])]
    .filter((event) => event.event_type === "blocked")
    .sort((a, b) => b.created_at.localeCompare(a.created_at))[0];

  const block = useApiMutation((reason: string) => blockWorkflow(view.id, reason), {
    success: "Процесс заблокирован",
    onSuccess: () => invalidateContractData(contract.id),
  });
  const unblock = useApiMutation((reason: string) => unblockWorkflow(view.id, reason), {
    success: "Блокировка снята",
    onSuccess: () => invalidateContractData(contract.id),
  });

  const addNote = async () => {
    if (!arrival) return;
    setBusy(true);
    try {
      if (note.trim()) await createComment(contract.id, note.trim(), arrival.id);
      for (const file of files) await uploadAttachment(contract.id, file, arrival.id);
      toast.success("Добавлено к этапу", `«${stage.name}»`);
      setNote("");
      setFiles([]);
      invalidateContractData(contract.id);
    } catch (error) {
      toast.error(error, "Не удалось добавить");
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="stack">
      <Card>
        <div className="stack-s">
          <div className="row-between">
            <span className="eyebrow">
              Этап {number} из {stages.length}
            </span>
            <StatusBadge tone={STAGE_TONE[state]}>{label("stage_state", state)}</StatusBadge>
          </div>
          <div className="row-between" style={{ alignItems: "flex-start" }}>
            <h2 className="card__title" style={{ fontSize: 18 }}>
              {stage.name}
            </h2>
            {can("rename_stage") && (
              <button
                type="button"
                className="icon-btn"
                aria-label="Переименовать этап"
                title="Переименовать этап"
                onClick={() => onRename(stage)}
              >
                <Pencil size={16} />
              </button>
            )}
          </div>
          {stage.description && <p className="soft">{stage.description}</p>}
          <div className="tags">
            {stage.sla_days ? <span className="tag">Норма: {countLabel(stage.sla_days, DAYS)}</span> : null}
            <span className="tag">{stage.is_optional ? "Необязательный" : "Обязательный"}</span>
            {stage.is_final && <span className="tag tag--accent">Завершающий</span>}
          </div>
          {days !== null && view.status === "in_progress" && (
            <div className="stack-s" style={{ gap: 4 }}>
              <span className={stage.sla_days && days > stage.sla_days ? "field__error" : "muted"}>
                На этапе {countLabel(days, DAYS)}
                {stage.sla_days ? ` из ${stage.sla_days}` : ""} · с {formatDateTime(view.current_stage_started_at)}
              </span>
              {stage.sla_days ? (
                <div
                  className={`meter ${days > stage.sla_days ? "meter--bad" : days >= stage.sla_days * 0.75 ? "meter--warn" : ""}`}
                >
                  <div
                    className="meter__fill"
                    style={{ width: `${Math.min(100, Math.max(4, (days / stage.sla_days) * 100))}%` }}
                  />
                </div>
              ) : null}
            </div>
          )}
        </div>

        {isCurrent && view.status === "in_progress" && (
          <div className="stack-s" style={{ marginTop: 16 }}>
            <span className="field__label">Куда дальше</span>
            {forward.length === 0 && backward.length === 0 && <span className="muted">Переходов из этого этапа нет.</span>}
            {forward.map((item) => (
              <div key={item.id} className="stack-s" style={{ gap: 4 }}>
                <Button icon={ArrowRightCircle} onClick={() => onTransition({ transition: item, skip: false })}>
                  {item.name || `На «${stageName(item.to_stage_id)}»`}
                </Button>
                {canSkip && (
                  <button
                    type="button"
                    className="link-btn"
                    style={{ fontSize: 13 }}
                    onClick={() => onTransition({ transition: item, skip: true })}
                  >
                    <SkipForward size={13} /> Пропустить этап и перейти на «{stageName(item.to_stage_id)}»
                  </button>
                )}
              </div>
            ))}
            {backward.map((item) => (
              <Button
                key={item.id}
                variant="outline"
                icon={ArrowLeftCircle}
                onClick={() => onTransition({ transition: item, skip: false })}
              >
                {item.name || `Вернуть на «${stageName(item.to_stage_id)}»`}
              </Button>
            ))}
            <Button
              variant="danger"
              icon={Lock}
              loading={block.isPending}
              onClick={async () => {
                const reason = await confirm({
                  title: "Заблокировать процесс?",
                  message:
                    "Процесс остановится на текущем этапе, пока блокировку не снимут. Руководитель увидит его в списке проблем.",
                  confirmLabel: "Заблокировать",
                  danger: true,
                  reason: { label: "Причина", required: true, placeholder: "Например: ждём подписи ректора" },
                });
                if (reason) block.mutate(reason);
              }}
            >
              Заблокировать
            </Button>
          </div>
        )}

        {isCurrent && view.status === "blocked" && (
          <div className="stack-s" style={{ marginTop: 16 }}>
            <div className="quote" style={{ borderLeftColor: "var(--bad)" }}>
              <strong>Процесс заблокирован</strong>
              {blockEvent?.comment ? `: ${blockEvent.comment}` : ""}
              <br />
              <small className="muted">
                {blockEvent?.user?.full_name} · {formatDateTime(blockEvent?.created_at)}
              </small>
            </div>
            <Button
              icon={Unlock}
              loading={unblock.isPending}
              onClick={async () => {
                const reason = await confirm({
                  title: "Снять блокировку?",
                  message: "Процесс продолжится с текущего этапа.",
                  confirmLabel: "Снять блокировку",
                  reason: { label: "Что изменилось", required: true },
                });
                if (reason) unblock.mutate(reason);
              }}
            >
              Снять блокировку
            </Button>
          </div>
        )}

        {isCurrent && view.status === "completed" && (
          <p className="muted" style={{ marginTop: 12 }}>
            Процесс завершён {formatDateTime(view.completed_at)}.
          </p>
        )}
      </Card>

      <Card title="Комментарии и файлы этапа">
        <div className="stack">
          {events.filter((event) => event.comment).length === 0 && stageComments.length === 0 && stageFiles.length === 0 && (
            <p className="muted">Пока ничего нет.</p>
          )}
          {events
            .filter((event) => event.comment)
            .map((event) => (
              <div key={event.id} className="stack-s" style={{ gap: 4 }}>
                <span className="timeline__meta">
                  {label("workflow_event_type", event.event_type)} · {event.user?.full_name || "система"} ·{" "}
                  {formatDateTime(event.created_at)}
                </span>
                <div className="quote">{event.comment}</div>
              </div>
            ))}
          {stageComments.map((item) => (
            <div key={item.id} className="stack-s" style={{ gap: 4 }}>
              <span className="timeline__meta">
                {item.author?.full_name || "—"} · {formatDateTime(item.created_at)}
              </span>
              <div className="quote">{item.text}</div>
            </div>
          ))}
          {stageFiles.length > 0 && (
            <div className="files">
              {stageFiles.map((file) => (
                <div key={file.id} className="file-row">
                  <Paperclip size={16} />
                  <div className="file-row__name">
                    <button type="button" className="link-btn" onClick={() => void download(() => downloadAttachment(file.id))}>
                      {file.original_name}
                    </button>
                    <small>
                      {fileSize(file.size_bytes)} · {file.uploader?.full_name || "—"} · {formatDateTime(file.created_at)}
                    </small>
                  </div>
                </div>
              ))}
            </div>
          )}
          {arrival ? (
            <div className="stack-s" style={{ borderTop: "1px solid var(--line)", paddingTop: 12 }}>
              <TextAreaField label="Комментарий к этапу" value={note} onChange={setNote} rows={3} maxLength={4000} />
              <FilePicker files={files} onChange={setFiles} title="Приложить файлы к этапу" />
              <div>
                <Button
                  variant="secondary"
                  loading={busy}
                  disabled={!note.trim() && files.length === 0}
                  onClick={() => void addNote()}
                >
                  Добавить к этапу
                </Button>
              </div>
            </div>
          ) : (
            <p className="muted">Комментарии и файлы можно добавить, когда процесс дойдёт до этого этапа.</p>
          )}
        </div>
      </Card>
    </div>
  );
}

export function ProcessTab({
  contract,
  workflow,
  comments,
  attachments,
}: {
  contract: ContractDetail;
  workflow: UseQueryResult<WorkflowView | null>;
  comments: Comment[];
  attachments: Attachment[];
}) {
  const { can } = useSession();
  const label = useLabel();
  const toast = useToast();
  const [selected, setSelected] = useState<string | null>(null);
  const [dialog, setDialog] = useState<Dialog>(null);
  const [renaming, setRenaming] = useState<Stage | null>(null);
  const [arranging, setArranging] = useState(false);
  const [positions, setPositions] = useState<Record<string, Point> | null>(null);
  const [resetKey, setResetKey] = useState(0);
  const [mode, setMode] = useState<"scheme" | "list">(() =>
    typeof window !== "undefined" && window.matchMedia("(max-width: 720px)").matches ? "list" : "scheme",
  );

  const view = workflow.data;
  // После перехода выбранным становится новый текущий этап.
  const currentStageId = view?.current_stage_id || view?.version.stages?.[0]?.id || null;
  useEffect(() => {
    if (currentStageId) setSelected(currentStageId);
  }, [currentStageId]);

  const states = useMemo(
    () => Object.fromEntries((view?.stage_states || []).map((item) => [item.stage_id, item.state])),
    [view?.stage_states],
  );
  const available = useMemo(
    () => new Set((view?.available_transitions || []).map((item) => item.id)),
    [view?.available_transitions],
  );

  const layout = useApiMutation(
    () =>
      saveLayout(
        view!.workflow_version_id,
        Object.entries(positions || {}).map(([stageId, point]) => ({ stage_id: stageId, layout_x: point.x, layout_y: point.y })),
      ),
    {
      success: "Расположение схемы сохранено",
      onSuccess: () => {
        setPositions(null);
        setArranging(false);
        invalidateContractData(contract.id);
        void queryClient.invalidateQueries({ queryKey: ["version", view!.workflow_version_id] });
      },
    },
  );

  if (workflow.isPending) return <Loading />;
  if (workflow.isError) return <ErrorState error={workflow.error} onRetry={() => void workflow.refetch()} />;
  if (!view) return <StartProcess contract={contract} />;

  const stages = view.version.stages || [];
  const stage = stages.find((item) => item.id === selected) || stages[0];
  const ordered = [...stages].sort((a, b) => a.sort_order - b.sort_order);

  return (
    <div className="stack">
      <div className="row-between">
        <div className="row">
          <StatusBadge tone={WORKFLOW_TONE[view.status]}>{label("workflow_status", view.status)}</StatusBadge>
          <span className="muted">
            Шаблон: версия {view.version.version_number} · запущен {formatDateTime(view.started_at)}
          </span>
        </div>
        <div className="row">
          <SegmentedControl
            value={mode}
            onChange={(value: string) => setMode(value as "scheme" | "list")}
            size="s"
            variant="secondary"
          >
            <Segment index="scheme" label="Схема" />
            <Segment index="list" label="Список" />
          </SegmentedControl>
          {can("save_layout") && mode === "scheme" && !arranging && (
            <Button variant="outline" size="s" onClick={() => setArranging(true)}>
              Изменить расположение
            </Button>
          )}
          {arranging && (
            <>
              <Button
                variant="outline"
                size="s"
                onClick={() => {
                  setArranging(false);
                  setPositions(null);
                  setResetKey((value) => value + 1);
                }}
              >
                Отменить
              </Button>
              <Button size="s" disabled={!positions} loading={layout.isPending} onClick={() => layout.mutate(undefined)}>
                Сохранить расположение
              </Button>
            </>
          )}
        </div>
      </div>
      {arranging && (
        <p className="muted" style={{ marginTop: -8 }}>
          Перетаскивайте этапы мышью. Расположение сохранится для всех договоров этой версии процесса.
        </p>
      )}

      <div className="process">
        {mode === "scheme" ? (
          <ProcessCanvas
            stages={stages}
            transitions={view.version.transitions || []}
            states={states}
            selectedId={stage?.id}
            onSelect={setSelected}
            availableTransitionIds={available}
            editable={arranging}
            resetKey={resetKey}
            onPositionsChange={(next) => {
              setPositions(next);
              if (!arranging) toast.info("Расположение не сохранено");
            }}
          />
        ) : (
          <Card>
            <ol className="stage-list">
              {ordered.map((item, index) => {
                const state = states[item.id] || "not_started";
                return (
                  <li key={item.id}>
                    <button
                      type="button"
                      className={item.id === view.current_stage_id ? "is-current" : undefined}
                      aria-pressed={item.id === stage?.id}
                      onClick={() => setSelected(item.id)}
                    >
                      <span className={`stage-num stage-num--${state}`}>{index + 1}</span>
                      <span className="cell-title">
                        <strong>{item.name}</strong>
                        <small>
                          {label("stage_state", state)}
                          {item.sla_days ? ` · норма ${item.sla_days} дн.` : ""}
                          {item.is_optional ? " · необязательный" : ""}
                        </small>
                      </span>
                      {item.id === stage?.id && <span className="tag tag--accent">выбран</span>}
                    </button>
                  </li>
                );
              })}
            </ol>
          </Card>
        )}
        <div className="stage-panel">
          {stage && (
            <StagePanel
              view={view}
              stage={stage}
              contract={contract}
              comments={comments}
              attachments={attachments}
              onTransition={setDialog}
              onRename={setRenaming}
            />
          )}
        </div>
      </div>

      <TransitionDialog dialog={dialog} view={view} contract={contract} onClose={() => setDialog(null)} />
      <RenameStageDialog stage={renaming} onClose={() => setRenaming(null)} contractId={contract.id} />
    </div>
  );
}
