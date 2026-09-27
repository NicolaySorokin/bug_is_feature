/**
 * Файлы и комментарии взаимодействия.
 *
 * Рабочие материалы принадлежат взаимодействию, а не договору: переписка
 * и документы появляются задолго до подписания. У файла - тип документа:
 * по нему проверяются обязательные документы этапа. По умолчанию новое
 * сообщение привязывается к текущему этапу процесса, тогда оно видно
 * и в карточке этапа. Черновик комментария сохраняется, если уйти со
 * страницы (кэш действий пользователя, требование 13 ТЗ).
 */
import type { UseQueryResult } from "@tanstack/react-query";
import { MessageSquare, Paperclip, Trash2 } from "lucide-react";
import { useState } from "react";
import { createComment, deleteAttachment, downloadAttachment, uploadAttachment } from "../../api/endpoints";
import { useApiMutation, useDownload } from "../../api/mutations";
import { invalidateInteractionData, useLabel } from "../../api/queries";
import type { Attachment, Comment, DocumentType, InteractionDetail, WorkflowView } from "../../api/types";
import { useSession } from "../../auth/session";
import { useConfirm } from "../../components/Confirm";
import { FilePicker } from "../../components/FilePicker";
import { useToast } from "../../components/Toasts";
import {
  Avatar,
  Button,
  Card,
  Checkbox,
  EmptyState,
  ErrorState,
  Loading,
  SelectField,
  Tag,
  TextAreaField,
} from "../../components/ui";
import { fileSize, formatDateTime } from "../../lib/format";
import { DOCUMENT_TYPES } from "../../lib/labels";
import { usePersistentState } from "../../lib/storage";

export function FilesTab({
  interaction,
  workflow,
  comments,
  attachments,
}: {
  interaction: InteractionDetail;
  workflow: WorkflowView | null;
  comments: UseQueryResult<Comment[]>;
  attachments: UseQueryResult<Attachment[]>;
}) {
  const { me, can } = useSession();
  const label = useLabel();
  const toast = useToast();
  const confirm = useConfirm();
  const [download] = useDownload();
  const [draft, setDraft, clearDraft] = usePersistentState(`draft.comment.${interaction.id}`, "");
  const [files, setFiles] = useState<File[]>([]);
  const [documentType, setDocumentType] = useState<DocumentType>(
    (interaction.missing_documents?.[0] as DocumentType | undefined) || "other",
  );
  const canWork = can("work_interaction");
  const [toStage, setToStage] = useState(true);
  const [busy, setBusy] = useState(false);

  const events = workflow?.events || [];
  const stages = workflow?.version.stages || [];
  const stageOfEvent = (eventId?: string | null) => {
    const event = events.find((item) => item.id === eventId);
    return stages.find((stage) => stage.id === event?.to_stage_id)?.name;
  };
  const arrival = workflow
    ? [...events]
        .filter((event) => event.to_stage_id === workflow.current_stage_id)
        .sort((a, b) => b.created_at.localeCompare(a.created_at))[0]
    : undefined;
  const currentStage = stages.find((stage) => stage.id === workflow?.current_stage_id);

  const remove = useApiMutation((id: string) => deleteAttachment(id), {
    success: "Файл удалён",
    onSuccess: () => invalidateInteractionData(interaction.id),
  });

  const send = async () => {
    setBusy(true);
    const eventId = toStage ? arrival?.id : undefined;
    const text = draft.trim();
    let saved = false;
    try {
      // Отправленное сразу уходит из формы: повтор после сбоя одного из
      // файлов не задвоит комментарий и уже загруженные файлы.
      if (text) {
        await createComment(interaction.id, text, eventId);
        saved = true;
        clearDraft();
      }
      for (const file of files) {
        await uploadAttachment(interaction.id, file, eventId, documentType);
        saved = true;
        setFiles((current) => current.filter((item) => item !== file));
      }
      toast.success(text ? "Комментарий добавлен" : "Файлы загружены");
    } catch (error) {
      toast.error(error, "Не удалось отправить");
    } finally {
      setBusy(false);
      if (saved) invalidateInteractionData(interaction.id);
    }
  };

  return (
    <div className="grid-main-side">
      <div className="stack">
        {canWork && (
          <Card title="Новое сообщение">
            <div className="stack">
              <TextAreaField
                label="Комментарий"
                value={draft}
                onChange={setDraft}
                rows={3}
                maxLength={4000}
                placeholder="Договорённости, вопросы, что осталось сделать"
                hint="Черновик сохраняется автоматически"
              />
              <FilePicker files={files} onChange={setFiles} />
              {files.length > 0 && (
                <SelectField
                  label="Тип документа"
                  value={documentType}
                  onChange={(value) => setDocumentType(value as DocumentType)}
                  options={DOCUMENT_TYPES.map((value) => ({ value, label: label("document_type", value) }))}
                  hint="По типу проверяются обязательные документы этапа"
                />
              )}
              {arrival && currentStage && (
                <Checkbox label={`Привязать к текущему этапу «${currentStage.name}»`} checked={toStage} onChange={setToStage} />
              )}
              <div>
                <Button loading={busy} disabled={!draft.trim() && files.length === 0} onClick={() => void send()}>
                  Отправить
                </Button>
              </div>
            </div>
          </Card>
        )}

        <Card title="Комментарии">
          {comments.isPending ? (
            <Loading />
          ) : comments.isError ? (
            <ErrorState error={comments.error} onRetry={() => void comments.refetch()} />
          ) : comments.data.length === 0 ? (
            <EmptyState icon={MessageSquare} title="Комментариев нет" />
          ) : (
            <ol className="timeline">
              {[...comments.data]
                .sort((a, b) => b.created_at.localeCompare(a.created_at))
                .map((item) => (
                  <li key={item.id} className="timeline__item">
                    <Avatar name={item.author?.full_name} />
                    <div className="timeline__body">
                      <span className="timeline__meta">
                        <strong style={{ color: "var(--text)" }}>{item.author?.full_name || "—"}</strong> ·{" "}
                        {formatDateTime(item.created_at)}
                        {stageOfEvent(item.workflow_event_id) ? ` · этап «${stageOfEvent(item.workflow_event_id)}»` : ""}
                      </span>
                      <div className="quote">{item.text}</div>
                    </div>
                  </li>
                ))}
            </ol>
          )}
        </Card>
      </div>

      <Card title="Файлы" description="PNG, JPEG, PDF, ZIP, GZIP, RAR, DOC, DOCX, XLS, XLSX">
        {attachments.isPending ? (
          <Loading />
        ) : attachments.isError ? (
          <ErrorState error={attachments.error} onRetry={() => void attachments.refetch()} />
        ) : attachments.data.length === 0 ? (
          <EmptyState icon={Paperclip} title="Файлов нет" />
        ) : (
          <div className="files">
            {[...attachments.data]
              .sort((a, b) => b.created_at.localeCompare(a.created_at))
              .map((file) => (
                <div key={file.id} className="file-row">
                  <Paperclip size={16} />
                  <div className="file-row__name">
                    <button
                      type="button"
                      className="link-btn"
                      title={file.original_name}
                      onClick={() => void download(() => downloadAttachment(file.id))}
                    >
                      {file.original_name}
                    </button>
                    <small>
                      {fileSize(file.size_bytes)} · {file.uploader?.full_name || "—"} · {formatDateTime(file.created_at)}
                      {stageOfEvent(file.workflow_event_id) ? ` · «${stageOfEvent(file.workflow_event_id)}»` : ""}
                    </small>
                  </div>
                  {file.document_type && file.document_type !== "other" && (
                    <Tag>{label("document_type", file.document_type)}</Tag>
                  )}
                  {canWork && (file.uploaded_by === me.id || can("assign_responsible")) && (
                    <button
                      type="button"
                      className="icon-btn"
                      aria-label={`Удалить ${file.original_name}`}
                      onClick={async () => {
                        const ok = await confirm({
                          title: `Удалить файл «${file.original_name}»?`,
                          confirmLabel: "Удалить",
                          danger: true,
                        });
                        if (ok !== null) remove.mutate(file.id);
                      }}
                    >
                      <Trash2 size={16} />
                    </button>
                  )}
                </div>
              ))}
          </div>
        )}
      </Card>
    </div>
  );
}
