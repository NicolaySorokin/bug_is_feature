/**
 * История взаимодействия по времени: заведение, запуск, переходы, блокировки, смена ответственного,
 * закрытие, с комментариями и файлами.
 */
import type { UseQueryResult } from "@tanstack/react-query";
import {
  ArrowLeft,
  ArrowRight,
  Ban,
  CheckCircle2,
  FilePlus2,
  Lock,
  Paperclip,
  Play,
  SkipForward,
  Unlock,
  UserRoundCog,
} from "lucide-react";
import { downloadAttachment } from "../../api/endpoints";
import { useDownload } from "../../api/mutations";
import { useLabel } from "../../api/queries";
import type { Attachment, Comment, WorkflowView } from "../../api/types";
import { Card, EmptyState, ErrorState, Loading } from "../../components/ui";
import { fileSize, formatDateTime } from "../../lib/format";

const ICONS = {
  created: FilePlus2,
  started: Play,
  forward: ArrowRight,
  backward: ArrowLeft,
  skipped: SkipForward,
  blocked: Lock,
  unblocked: Unlock,
  completed: CheckCircle2,
  cancelled: Ban,
  reassigned: UserRoundCog,
  commented: ArrowRight,
} as const;

export function HistoryTab({
  workflow,
  comments,
  attachments,
}: {
  workflow: UseQueryResult<WorkflowView | null>;
  comments: Comment[];
  attachments: Attachment[];
}) {
  const label = useLabel();
  const [download] = useDownload();
  if (workflow.isPending) return <Loading />;
  if (workflow.isError) return <ErrorState error={workflow.error} onRetry={() => void workflow.refetch()} />;
  const view = workflow.data;
  if (!view) return <EmptyState title="Истории пока нет">Она появится, когда взаимодействие заведут.</EmptyState>;

  const stages = view.version.stages || [];
  const name = (id?: string | null) => stages.find((stage) => stage.id === id)?.name || "—";
  const events = [...(view.events || [])].sort((a, b) => b.created_at.localeCompare(a.created_at));

  return (
    <Card title="История взаимодействия" description="Кто, когда и почему менял этап. Самые новые события сверху.">
      <ol className="timeline">
        {events.map((event) => {
          const Icon = ICONS[event.event_type] || ArrowRight;
          const tone =
            event.event_type === "blocked" || event.event_type === "cancelled"
              ? "timeline__dot--bad"
              : event.event_type === "completed" ||
                  (event.event_type === "forward" && stages.find((s) => s.id === event.to_stage_id)?.is_final)
                ? "timeline__dot--good"
                : event.event_type === "skipped" || event.event_type === "backward"
                  ? "timeline__dot--neutral"
                  : "";
          const eventComments = comments.filter((item) => item.workflow_event_id === event.id);
          const eventFiles = attachments.filter((item) => item.workflow_event_id === event.id);
          return (
            <li key={event.id} className="timeline__item">
              <span className={`timeline__dot ${tone}`}>
                <Icon size={14} />
              </span>
              <div className="timeline__body">
                <strong>{label("workflow_event_type", event.event_type)}</strong>
                <span>
                  {event.event_type === "created"
                    ? "Черновик взаимодействия"
                    : event.from_stage_id && event.from_stage_id === event.to_stage_id
                      ? `На этапе «${name(event.to_stage_id)}»`
                      : event.from_stage_id && event.to_stage_id
                        ? `«${name(event.from_stage_id)}» → «${name(event.to_stage_id)}»`
                        : event.to_stage_id
                          ? `Этап «${name(event.to_stage_id)}»`
                          : event.from_stage_id
                            ? `На этапе «${name(event.from_stage_id)}»`
                            : ""}
                </span>
                {event.comment && <div className="quote">{event.comment}</div>}
                {eventComments.map((item) => (
                  <div key={item.id} className="quote">
                    {item.text}
                    <br />
                    <small className="muted">
                      {item.author?.full_name} · {formatDateTime(item.created_at)}
                    </small>
                  </div>
                ))}
                {eventFiles.length > 0 && (
                  <div className="files">
                    {eventFiles.map((file) => (
                      <div key={file.id} className="file-row">
                        <Paperclip size={14} />
                        <div className="file-row__name">
                          <button
                            type="button"
                            className="link-btn"
                            onClick={() => void download(() => downloadAttachment(file.id))}
                          >
                            {file.original_name}
                          </button>
                          <small>{fileSize(file.size_bytes)}</small>
                        </div>
                      </div>
                    ))}
                  </div>
                )}
                <span className="timeline__meta">
                  {event.user?.full_name || "Система"} · {formatDateTime(event.created_at)}
                </span>
              </div>
            </li>
          );
        })}
      </ol>
    </Card>
  );
}
