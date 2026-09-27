/**
 * Карточка взаимодействия с вузом.
 *
 * Вверху два блока (пункт 36 перечня исправлений): слева «Сведения» - вуз,
 * ответственный, дата начала, программы и продукты, источник; справа
 * «Обзор взаимодействия» - статус, текущий этап со следующим действием,
 * срок этапа и состояние договора. Схема процесса - только на вкладке
 * «Процесс», без дублирования.
 *
 * Вкладки: Процесс | Программы и продукты | Договор | Контакты |
 * Файлы и комментарии | История.
 */
import { useQuery } from "@tanstack/react-query";
import { ArrowLeft, Ban, Pencil, Play, Trash2 } from "lucide-react";
import { useState } from "react";
import { Link, useNavigate, useParams, useSearchParams } from "react-router-dom";
import { ApiError } from "../../api/client";
import {
  cancelInteraction,
  deleteInteraction,
  getInteraction,
  getWorkflow,
  listAttachments,
  listComments,
  startInteraction,
} from "../../api/endpoints";
import { useApiMutation } from "../../api/mutations";
import { invalidateInteractionData, keys, useLabel } from "../../api/queries";
import type { ClosureReason, InteractionDetail } from "../../api/types";
import { useConfirm } from "../../components/Confirm";
import { Modal } from "../../components/Modal";
import {
  Button,
  Card,
  DescriptionList,
  ErrorState,
  Loading,
  PageHeader,
  SelectField,
  Tag,
  TextAreaField,
  Tabs,
} from "../../components/ui";
import { InteractionFormModal } from "../../features/interaction/InteractionForm";
import { ContractCell, interactionTitle, InteractionStatusBadge, OutcomeBadge, SlaBlock } from "../../features/interaction/parts";
import { formatDate, formatDateTime } from "../../lib/format";
import { CLOSURE_REASONS } from "../../lib/labels";
import { usePageTitle } from "../../lib/usePageTitle";
import { CompositionTab } from "./CompositionTab";
import { ContactsTab } from "./ContactsTab";
import { ContractTab } from "./ContractTab";
import { FilesTab } from "./FilesTab";
import { HistoryTab } from "./HistoryTab";
import { ProcessTab } from "./ProcessTab";

const TABS = ["process", "composition", "contract", "contacts", "files", "history"] as const;
type TabKey = (typeof TABS)[number];

function CancelDialog({ open, onClose, interaction }: { open: boolean; onClose: () => void; interaction: InteractionDetail }) {
  const label = useLabel();
  const [reason, setReason] = useState<ClosureReason | "">("");
  const [comment, setComment] = useState("");
  const cancel = useApiMutation(() => cancelInteraction(interaction.id, reason as ClosureReason, comment.trim()), {
    success: "Взаимодействие отменено",
    onSuccess: () => {
      invalidateInteractionData(interaction.id);
      onClose();
    },
  });
  const needsComment = reason === "other";
  return (
    <Modal
      open={open}
      onClose={onClose}
      title="Отменить взаимодействие?"
      description="Работа прекращается досрочно: результат - «Неуспешно», причина попадёт в отчёты. Отмену нельзя откатить."
      footer={
        <>
          <Button variant="outline" onClick={onClose}>
            Не отменять
          </Button>
          <Button
            variant="danger"
            loading={cancel.isPending}
            disabled={!reason || (needsComment && !comment.trim())}
            onClick={() => cancel.mutate(undefined)}
          >
            Отменить взаимодействие
          </Button>
        </>
      }
    >
      <div className="stack">
        <SelectField
          label="Причина"
          required
          value={reason}
          onChange={(value) => setReason(value as ClosureReason)}
          placeholder="Выберите причину"
          options={CLOSURE_REASONS.map((value) => ({ value, label: label("closure_reason", value) }))}
        />
        <TextAreaField
          label="Комментарий"
          required={needsComment}
          value={comment}
          onChange={setComment}
          rows={3}
          maxLength={2000}
          placeholder="Что произошло и что делать дальше"
        />
      </div>
    </Modal>
  );
}

/**
 * «Обзор взаимодействия» - постоянная краткая сводка (пункт 36): статус,
 * текущий этап со следующим действием, срок этапа и состояние договора.
 * Процесс здесь - одна строка с текущим этапом; схема - на вкладке «Процесс».
 */
function Overview({ data, onTab }: { data: InteractionDetail; onTab: (key: TabKey) => void }) {
  const label = useLabel();
  const stage = data.stage;
  const open = data.status === "in_progress" || data.status === "blocked";
  const contract = data.contract;
  return (
    <Card title="Обзор взаимодействия">
      {/* Список строк «подпись - значение», как в «Сведениях»: статус, этап и срок
          остаются независимыми строками, цвет - только у полосы срока. */}
      <dl className="overview-list">
        <div className="overview-list__row">
          <dt>Статус</dt>
          <dd>
            <span className="row" style={{ gap: 6, flexWrap: "wrap" }}>
              <InteractionStatusBadge status={data.status} />
              <OutcomeBadge outcome={data.outcome} />
            </span>
            {data.status === "blocked" && data.blocked_reason && (
              <span className="soft">
                {data.blocked_reason}
                {data.blocked_at ? <small className="muted"> · с {formatDate(data.blocked_at)}</small> : null}
              </span>
            )}
            {(data.status === "completed" || data.status === "cancelled") && (
              <small className="muted">
                {formatDateTime(data.closed_at)}
                {data.closure_reason ? ` · ${label("closure_reason", data.closure_reason)}` : ""}
                {data.closed_by ? ` · ${data.closed_by.full_name}` : ""}
              </small>
            )}
          </dd>
        </div>
        <div className="overview-list__row">
          <dt>Текущий этап</dt>
          <dd>
            {stage ? (
              <>
                <strong>{stage.stage_name}</strong>
                {open && (stage.next_actions || []).length > 0 && (
                  <span className="soft">Дальше: {(stage.next_actions || []).join(" или ")}</span>
                )}
                {data.missing_documents && data.missing_documents.length > 0 && (
                  <span className="field__error">
                    Нужны документы: {data.missing_documents.map((item) => label("document_type", item).toLowerCase()).join(", ")}
                  </span>
                )}
              </>
            ) : (
              <span className="muted">{data.status === "draft" ? "Процесс ещё не запущен" : "—"}</span>
            )}
            <button type="button" className="link-btn" onClick={() => onTab("process")}>
              {data.status === "draft" ? "Запустить процесс" : "Открыть схему процесса"}
            </button>
          </dd>
        </div>
        <div className="overview-list__row">
          <dt>Срок этапа</dt>
          <dd>
            <SlaBlock sla={stage?.sla} status={data.status} />
          </dd>
        </div>
        <div className="overview-list__row">
          <dt>Договор</dt>
          <dd>
            {contract ? (
              <ContractCell contract={contract} />
            ) : (
              <span className="muted">Пока нет - заводится, когда до него дойдёт работа</span>
            )}
            <button type="button" className="link-btn" onClick={() => onTab("contract")}>
              {contract ? "Открыть договор" : data.can_edit ? "Завести договор" : "Подробнее"}
            </button>
          </dd>
        </div>
      </dl>
    </Card>
  );
}

/** «Сведения»: вуз, ответственный, дата начала, программы и продукты, источник. */
function Details({ data, onTab }: { data: InteractionDetail; onTab: (key: TabKey) => void }) {
  const label = useLabel();
  const university = data.university;
  const programs = (data.program_links || []).map((item) => item.program?.name).filter(Boolean) as string[];
  const products = data.product_links || [];
  return (
    <Card title="Сведения">
      <DescriptionList
        items={[
          [
            "Вуз",
            <Link key="u" to={`/universities/${university.id}`}>
              {university.name}
            </Link>,
          ],
          ["Ответственный", data.manager?.full_name || <Tag tone="warn">Не назначен</Tag>],
          ["Дата начала", data.started_at ? formatDate(data.started_at) : <span className="muted">процесс не запущен</span>],
          [
            "Программы и продукты",
            programs.length || products.length ? (
              <span className="stack-s" style={{ gap: 2 }}>
                <span>{programs.length ? programs.join(", ") : "Программы не выбраны"}</span>
                <button type="button" className="link-btn" onClick={() => onTab("composition")}>
                  {products.length ? `ИТ-продуктов: ${products.length}` : "Продуктов пока нет"}
                </button>
              </span>
            ) : (
              <button type="button" className="link-btn" onClick={() => onTab("composition")}>
                Не выбраны
              </button>
            ),
          ],
          ["Источник", label("interaction_source", data.source)],
          ["Процесс", `${data.template_name || "—"}, версия ${data.version_number}`],
          ["Заведено", `${formatDateTime(data.created_at)}${data.created_by ? ` · ${data.created_by.full_name}` : ""}`],
          ["Комментарий", data.comment ? <span style={{ whiteSpace: "pre-wrap" }}>{data.comment}</span> : null],
        ]}
      />
    </Card>
  );
}

export default function InteractionPage() {
  const { interactionId = "" } = useParams();
  const [params, setParams] = useSearchParams();
  const navigate = useNavigate();
  const confirm = useConfirm();
  const [editing, setEditing] = useState(false);
  const [cancelling, setCancelling] = useState(false);
  const tab: TabKey = TABS.includes(params.get("tab") as TabKey) ? (params.get("tab") as TabKey) : "process";

  const interaction = useQuery({ queryKey: keys.interaction(interactionId), queryFn: () => getInteraction(interactionId) });
  const workflow = useQuery({
    queryKey: keys.workflow(interactionId),
    queryFn: () => getWorkflow(interactionId),
    enabled: interaction.isSuccess,
  });
  const comments = useQuery({
    queryKey: keys.comments(interactionId),
    queryFn: () => listComments(interactionId),
    enabled: interaction.isSuccess,
  });
  const attachments = useQuery({
    queryKey: keys.attachments(interactionId),
    queryFn: () => listAttachments(interactionId),
    enabled: interaction.isSuccess,
  });
  usePageTitle(interaction.data ? interactionTitle(interaction.data) : "Взаимодействие");

  const start = useApiMutation(() => startInteraction(interactionId), {
    success: "Процесс запущен",
    onSuccess: () => invalidateInteractionData(interactionId),
  });
  const remove = useApiMutation(() => deleteInteraction(interactionId), {
    success: "Черновик удалён",
    onSuccess: () => {
      invalidateInteractionData();
      navigate("/interactions");
    },
  });

  if (interaction.isPending)
    return (
      <div className="page">
        <Loading />
      </div>
    );
  if (interaction.isError) {
    return (
      <div className="page">
        <ErrorState
          error={interaction.error}
          title={
            interaction.error instanceof ApiError && interaction.error.status === 404
              ? "Взаимодействие не найдено"
              : interaction.error instanceof ApiError && interaction.error.status === 403
                ? "Взаимодействие вне вашей области данных"
                : undefined
          }
          onRetry={() => void interaction.refetch()}
        />
      </div>
    );
  }

  const data = interaction.data;
  const setTab = (key: string) => {
    const next = new URLSearchParams(params);
    next.set("tab", key);
    setParams(next, { replace: true });
  };
  const university = data.university;
  const filesCount = (comments.data?.length || 0) + (attachments.data?.length || 0);

  return (
    <div className="page">
      <PageHeader
        back={
          <Link className="back-link" to="/interactions">
            <ArrowLeft size={14} /> Взаимодействия
          </Link>
        }
        eyebrow={university.short_name || university.name}
        title={interactionTitle(data)}
        actions={
          <>
            {data.status === "draft" && data.can_edit && (
              <Button icon={Play} loading={start.isPending} onClick={() => start.mutate(undefined)}>
                Запустить процесс
              </Button>
            )}
            {data.can_edit && (
              <Button variant="outline" icon={Pencil} onClick={() => setEditing(true)}>
                Изменить
              </Button>
            )}
            {data.can_cancel && (
              <Button variant="outline" icon={Ban} onClick={() => setCancelling(true)}>
                Отменить
              </Button>
            )}
            {data.can_delete && (
              <Button
                variant="danger"
                icon={Trash2}
                loading={remove.isPending}
                onClick={async () => {
                  const ok = await confirm({
                    title: "Удалить черновик?",
                    message: "Удаляется только ошибочно заведённый черновик без договора, файлов и движения по процессу.",
                    confirmLabel: "Удалить",
                    danger: true,
                  });
                  if (ok !== null) remove.mutate(undefined);
                }}
              >
                Удалить
              </Button>
            )}
          </>
        }
      />

      <div className="interaction-top">
        <Details data={data} onTab={setTab} />
        <Overview data={data} onTab={setTab} />
      </div>

      <Tabs
        value={tab}
        onChange={setTab}
        items={[
          { key: "process", label: "Процесс", dot: (data.missing_documents || []).length > 0 },
          {
            key: "composition",
            label: "Программы и продукты",
            count: (data.program_links || []).length + (data.product_links || []).length || undefined,
          },
          {
            key: "contract",
            label: "Договор",
            dot: Boolean(data.contract && data.contract.status === "active" && (data.contract.days_left ?? 999) <= 60),
          },
          { key: "contacts", label: "Контакты", count: (data.contacts || []).length || undefined },
          { key: "files", label: "Файлы и комментарии", count: filesCount || undefined },
          { key: "history", label: "История" },
        ]}
      />

      {tab === "process" && (
        <ProcessTab interaction={data} workflow={workflow} comments={comments.data || []} attachments={attachments.data || []} />
      )}
      {tab === "composition" && <CompositionTab interaction={data} />}
      {tab === "contract" && <ContractTab interaction={data} workflow={workflow.data || null} />}
      {tab === "contacts" && <ContactsTab interaction={data} />}
      {tab === "files" && (
        <FilesTab interaction={data} workflow={workflow.data || null} comments={comments} attachments={attachments} />
      )}
      {tab === "history" && (
        <HistoryTab workflow={workflow} comments={comments.data || []} attachments={attachments.data || []} />
      )}

      {data.can_edit && <InteractionFormModal open={editing} onClose={() => setEditing(false)} interaction={data} />}
      {data.can_cancel && <CancelDialog open={cancelling} onClose={() => setCancelling(false)} interaction={data} />}
    </div>
  );
}
