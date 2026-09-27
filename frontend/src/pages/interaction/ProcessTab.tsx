/**
 * Вкладка «Процесс»: схема этапов, переходы, блокировка, комментарии
 * и файлы к этапам.
 *
 * Переходы - только те, что разрешены версией шаблона (сервер присылает
 * их списком). Этап может требовать документы: без них вперёд не уйти,
 * и вкладка говорит, каких не хватает. Финальный этап с неуспешным
 * результатом («Отказ вуза») закрывает взаимодействие только с причиной.
 * Комментарий и файлы, добавленные при переходе, привязываются к событию
 * перехода и видны в карточке этапа и в истории.
 */
import { Segment, SegmentedControl } from "@atomaro/ui-kit";
import type { UseQueryResult } from "@tanstack/react-query";
import { ArrowLeftCircle, ArrowRightCircle, FileWarning, Lock, Paperclip, Pencil, Play, SkipForward, Unlock } from "lucide-react";
import { useEffect, useMemo, useState } from "react";
import {
  blockInteraction,
  createComment,
  downloadAttachment,
  renameStage,
  saveLayout,
  skipStage,
  startInteraction,
  transition,
  unblockInteraction,
  uploadAttachment,
} from "../../api/endpoints";
import { useApiMutation, useDownload } from "../../api/mutations";
import { invalidateInteractionData, queryClient, useLabel } from "../../api/queries";
import type {
  Attachment,
  ClosureReason,
  Comment,
  DocumentType,
  InteractionDetail,
  Stage,
  Transition,
  WorkflowView,
} from "../../api/types";
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
import { SlaMeter, slaRemainder, slaUsage } from "../../features/interaction/parts";
import { ProcessCanvas } from "../../features/workflow/ProcessCanvas";
import type { Point } from "../../features/workflow/layout";
import { countLabel, DAYS, daysSince, fileSize, formatDateTime } from "../../lib/format";
import { CLOSURE_REASONS, DOCUMENT_TYPES, INTERACTION_TONE } from "../../lib/labels";

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

/** Черновик: процесс ещё не запущен. Запуск ставит взаимодействие на стартовый этап. */
function StartProcess({ interaction }: { interaction: InteractionDetail }) {
  const { can } = useSession();
  const start = useApiMutation(() => startInteraction(interaction.id), {
    success: "Процесс запущен",
    onSuccess: () => invalidateInteractionData(interaction.id),
  });
  return (
    <Card>
      <EmptyState icon={Play} title="Процесс ещё не запущен">
        Взаимодействие - черновик: проверьте вуз, ответственного и программы. При запуске процесс встанет на стартовый этап
        действующей версии шаблона «{interaction.template_name || "основной"}».
      </EmptyState>
      {can("work_interaction") && (
        <div className="row" style={{ justifyContent: "center", paddingBottom: 12 }}>
          <Button icon={Play} loading={start.isPending} onClick={() => start.mutate(undefined)}>
            Запустить процесс
          </Button>
        </div>
      )}
    </Card>
  );
}

function TransitionDialog({
  dialog,
  view,
  interaction,
  onClose,
}: {
  dialog: Dialog;
  view: WorkflowView;
  interaction: InteractionDetail;
  onClose: () => void;
}) {
  const toast = useToast();
  const label = useLabel();
  const [comment, setComment] = useState("");
  const [files, setFiles] = useState<File[]>([]);
  const [documentType, setDocumentType] = useState<DocumentType>("other");
  const [reason, setReason] = useState<ClosureReason | "">("");
  const [busy, setBusy] = useState(false);
  useEffect(() => {
    setComment("");
    setFiles([]);
    setReason("");
    setDocumentType("other");
  }, [dialog]);

  if (!dialog) return null;
  const stages = view.version.stages || [];
  const from = stages.find((stage) => stage.id === dialog.transition.from_stage_id);
  const to = stages.find((stage) => stage.id === dialog.transition.to_stage_id);
  // Финальный этап без успеха закрывает взаимодействие - нужна причина.
  const failing = Boolean(!dialog.skip && to?.is_final && to.outcome && to.outcome !== "successful");
  const needsText = dialog.skip || dialog.transition.requires_comment || (failing && reason === "other");
  const blocked = (needsText && !comment.trim()) || (failing && !reason);

  const title = dialog.skip
    ? `Пропустить этап «${from?.name}»`
    : dialog.transition.is_backward
      ? `Вернуть на этап «${to?.name}»`
      : `Перейти на этап «${to?.name}»`;

  const submit = async () => {
    setBusy(true);
    try {
      const result = dialog.skip
        ? await skipStage(interaction.id, dialog.transition.to_stage_id, comment.trim())
        : await transition(interaction.id, dialog.transition.to_stage_id, comment.trim(), reason || null);
      const event = newestEvent(result);
      for (const file of files) {
        await uploadAttachment(interaction.id, file, event?.id, documentType);
      }
      toast.success(
        to?.is_final ? "Взаимодействие завершено" : `Этап: «${to?.name}»`,
        files.length ? `Приложено файлов: ${files.length}` : undefined,
      );
      invalidateInteractionData(interaction.id);
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
          : `С «${from?.name}» на «${to?.name}»${
              to?.is_final
                ? failing
                  ? " - это закроет взаимодействие без успеха"
                  : " - это успешно завершит взаимодействие"
                : ""
            }.`
      }
      footer={
        <>
          <Button variant="outline" onClick={onClose} disabled={busy}>
            Отмена
          </Button>
          <Button loading={busy} disabled={blocked} onClick={() => void submit()}>
            {dialog.skip ? "Пропустить" : dialog.transition.is_backward ? "Вернуть" : "Перейти"}
          </Button>
        </>
      }
    >
      <div className="stack">
        {failing && (
          <SelectField
            label="Причина закрытия"
            required
            value={reason}
            onChange={(value) => setReason(value as ClosureReason)}
            placeholder="Выберите причину"
            options={CLOSURE_REASONS.map((value) => ({ value, label: label("closure_reason", value) }))}
          />
        )}
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
        {files.length > 0 && (
          <SelectField
            label="Тип документа"
            value={documentType}
            onChange={(value) => setDocumentType(value as DocumentType)}
            options={DOCUMENT_TYPES.map((value) => ({ value, label: label("document_type", value) }))}
          />
        )}
      </div>
    </Modal>
  );
}

function RenameStageDialog({
  stage,
  onClose,
  interactionId,
}: {
  stage: Stage | null;
  onClose: () => void;
  interactionId: string;
}) {
  const [name, setName] = useState("");
  const [description, setDescription] = useState("");
  useEffect(() => {
    setName(stage?.name || "");
    setDescription(stage?.description || "");
  }, [stage]);
  const save = useApiMutation(() => renameStage(stage!.id, { name: name.trim(), description: description.trim() || null }), {
    success: "Этап переименован",
    onSuccess: () => {
      invalidateInteractionData(interactionId);
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
      description="Новое название увидят все взаимодействия, которые идут по этой версии шаблона, а также отчёты."
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
  interaction,
  comments,
  attachments,
  onTransition,
  onRename,
}: {
  view: WorkflowView;
  stage: Stage;
  interaction: InteractionDetail;
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
  const [documentType, setDocumentType] = useState<DocumentType>("other");
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
  const canWork = can("work_interaction");
  const canSkip = canWork && (stage.is_optional || can("skip_any_stage"));
  const required = stage.required_documents || [];
  const missing = isCurrent ? interaction.missing_documents || [] : [];
  // Срок текущего этапа - тот же расчёт сервера, что в «Обзоре» и на главной.
  const sla = isCurrent ? interaction.stage?.sla : null;
  const days = isCurrent && view.current_stage_started_at ? daysSince(view.current_stage_started_at) : null;
  const blockEvent = [...(view.events || [])]
    .filter((event) => event.event_type === "blocked")
    .sort((a, b) => b.created_at.localeCompare(a.created_at))[0];

  const block = useApiMutation((reason: string) => blockInteraction(interaction.id, reason), {
    success: "Взаимодействие заблокировано",
    onSuccess: () => invalidateInteractionData(interaction.id),
  });
  const unblock = useApiMutation((reason: string) => unblockInteraction(interaction.id, reason), {
    success: "Блокировка снята",
    onSuccess: () => invalidateInteractionData(interaction.id),
  });

  const addNote = async () => {
    if (!arrival) return;
    setBusy(true);
    try {
      if (note.trim()) await createComment(interaction.id, note.trim(), arrival.id);
      for (const file of files) await uploadAttachment(interaction.id, file, arrival.id, documentType);
      toast.success("Добавлено к этапу", `«${stage.name}»`);
      setNote("");
      setFiles([]);
      invalidateInteractionData(interaction.id);
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
            {can("edit_workflow_presentation") && (
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
            {stage.is_final && (
              <span className={`tag ${stage.outcome === "successful" ? "tag--accent" : "tag--warn"}`}>
                Завершающий · {label("interaction_outcome", stage.outcome || "successful").toLowerCase()}
              </span>
            )}
            {required.map((item) => (
              <span key={item} className="tag">
                Нужен документ: {label("document_type", item).toLowerCase()}
              </span>
            ))}
          </div>
          {(view.status === "in_progress" || view.status === "blocked") &&
            (sla ? (
              <div className="stack-s" style={{ gap: 4 }}>
                <span className={sla.state === "overdue" ? "field__error" : "muted"}>
                  Срок этапа: {slaUsage(sla)}, {slaRemainder(sla)} · с {formatDateTime(view.current_stage_started_at)}
                </span>
                <SlaMeter sla={sla} />
              </div>
            ) : days !== null ? (
              <span className="muted">
                На этапе {countLabel(days, DAYS)} · с {formatDateTime(view.current_stage_started_at)}
              </span>
            ) : null)}
        </div>

        {missing.length > 0 && (
          <div className="note note--warn" style={{ marginTop: 12 }}>
            <FileWarning size={16} aria-hidden="true" /> Чтобы уйти с этапа вперёд, загрузите:{" "}
            {missing.map((item) => label("document_type", item).toLowerCase()).join(", ")}. Файлы добавляются ниже или на вкладке
            «Файлы и комментарии» - с типом документа.
          </div>
        )}

        {isCurrent && view.status === "in_progress" && canWork && (
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
                  title: "Заблокировать взаимодействие?",
                  message:
                    "Работа остановится на текущем этапе, пока блокировку не снимут. Причина будет видна в карточке и у руководителя.",
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
              <strong>Взаимодействие заблокировано</strong>
              {view.blocked_reason || blockEvent?.comment ? `: ${view.blocked_reason || blockEvent?.comment}` : ""}
              <br />
              <small className="muted">
                {blockEvent?.user?.full_name} · {formatDateTime(blockEvent?.created_at)}
              </small>
            </div>
            {canWork && (
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
            )}
          </div>
        )}

        {isCurrent && (view.status === "completed" || view.status === "cancelled") && (
          <p className="muted" style={{ marginTop: 12 }}>
            {view.status === "completed" ? "Взаимодействие завершено" : "Взаимодействие отменено"}{" "}
            {formatDateTime(view.closed_at)}
            {view.outcome ? ` · результат: ${label("interaction_outcome", view.outcome).toLowerCase()}` : ""}
            {view.closure_reason ? ` · ${label("closure_reason", view.closure_reason).toLowerCase()}` : ""}.
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
          {arrival && canWork ? (
            <div className="stack-s" style={{ borderTop: "1px solid var(--line)", paddingTop: 12 }}>
              <TextAreaField label="Комментарий к этапу" value={note} onChange={setNote} rows={3} maxLength={4000} />
              <FilePicker files={files} onChange={setFiles} title="Приложить файлы к этапу" />
              {files.length > 0 && (
                <SelectField
                  label="Тип документа"
                  value={documentType}
                  onChange={(value) => setDocumentType(value as DocumentType)}
                  options={DOCUMENT_TYPES.map((value) => ({ value, label: label("document_type", value) }))}
                  hint={required.length ? "Обязательный документ этапа отметьте его типом" : undefined}
                />
              )}
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
          ) : !arrival ? (
            <p className="muted">Комментарии и файлы можно добавить, когда процесс дойдёт до этого этапа.</p>
          ) : null}
        </div>
      </Card>
    </div>
  );
}

export function ProcessTab({
  interaction,
  workflow,
  comments,
  attachments,
}: {
  interaction: InteractionDetail;
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
  const currentStageId =
    view?.current_stage_id || view?.version.stages?.find((item) => item.is_initial)?.id || view?.version.stages?.[0]?.id || null;
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
        invalidateInteractionData(interaction.id);
        void queryClient.invalidateQueries({ queryKey: ["version", view!.workflow_version_id] });
      },
    },
  );

  if (workflow.isPending) return <Loading />;
  if (workflow.isError) return <ErrorState error={workflow.error} onRetry={() => void workflow.refetch()} />;
  if (!view || interaction.status === "draft") return <StartProcess interaction={interaction} />;

  const stages = view.version.stages || [];
  const stage = stages.find((item) => item.id === selected) || stages[0];
  const ordered = [...stages].sort((a, b) => a.sort_order - b.sort_order);

  return (
    <div className="stack">
      <div className="row-between">
        <div className="row">
          <StatusBadge tone={INTERACTION_TONE[view.status]}>{label("interaction_status", view.status)}</StatusBadge>
          <span className="muted">
            {interaction.template_name || "Шаблон"}: версия {view.version.version_number}
            {view.version.status !== "active"
              ? ` (${label("workflow_version_status", view.version.status).toLowerCase()})`
              : ""}{" "}
            · запущен {formatDateTime(view.started_at)}
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
          {can("edit_workflow_presentation") && mode === "scheme" && !arranging && (
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
          Перетаскивайте этапы мышью. Расположение сохранится для всех взаимодействий этой версии процесса.
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
              interaction={interaction}
              comments={comments}
              attachments={attachments}
              onTransition={setDialog}
              onRename={setRenaming}
            />
          )}
        </div>
      </div>

      <TransitionDialog dialog={dialog} view={view} interaction={interaction} onClose={() => setDialog(null)} />
      <RenameStageDialog stage={renaming} onClose={() => setRenaming(null)} interactionId={interaction.id} />
    </div>
  );
}
