/**
 * Карточка договора.
 *
 * Вверху - главное: вуз, ответственный, статус, сроки и где сейчас
 * процесс. Ниже вкладки: процесс (схема этапов и переходы), состав и
 * лицензии, контакты вуза, комментарии и файлы, история.
 */
import { useQuery } from "@tanstack/react-query";
import { ArrowLeft, Pencil, Trash2 } from "lucide-react";
import { useState } from "react";
import { Link, useNavigate, useParams, useSearchParams } from "react-router-dom";
import { ApiError } from "../../api/client";
import { deleteContract, getContract, getWorkflow, listAttachments, listComments } from "../../api/endpoints";
import { useApiMutation } from "../../api/mutations";
import { invalidateContractData, keys, useLabel } from "../../api/queries";
import { useSession } from "../../auth/session";
import { useConfirm } from "../../components/Confirm";
import { Button, Card, DescriptionList, ErrorState, Loading, PageHeader, StatusBadge, Tabs, Tag } from "../../components/ui";
import { countLabel, DAYS, daysUntil, formatDate, formatDateTime } from "../../lib/format";
import { CONTRACT_STATUS_TONE, WORKFLOW_TONE } from "../../lib/labels";
import { usePageTitle } from "../../lib/usePageTitle";
import { CommentsTab } from "./CommentsTab";
import { CompositionTab } from "./CompositionTab";
import { ContactsTab } from "./ContactsTab";
import { ContractFormModal } from "./ContractForm";
import { HistoryTab } from "./HistoryTab";
import { ProcessTab } from "./ProcessTab";

const TABS = ["process", "composition", "contacts", "comments", "history"] as const;
type TabKey = (typeof TABS)[number];

export default function ContractPage() {
  const { contractId = "" } = useParams();
  const [params, setParams] = useSearchParams();
  const navigate = useNavigate();
  const label = useLabel();
  const confirm = useConfirm();
  const { can } = useSession();
  const [editing, setEditing] = useState(false);
  const tab: TabKey = TABS.includes(params.get("tab") as TabKey) ? (params.get("tab") as TabKey) : "process";

  const contract = useQuery({ queryKey: keys.contract(contractId), queryFn: () => getContract(contractId) });
  const workflow = useQuery({
    queryKey: keys.workflow(contractId),
    queryFn: async () => {
      try {
        return await getWorkflow(contractId);
      } catch (error) {
        // 404 - процесс по договору ещё не запущен: это не ошибка.
        if (error instanceof ApiError && error.status === 404) return null;
        throw error;
      }
    },
    enabled: contract.isSuccess,
  });
  const comments = useQuery({
    queryKey: keys.comments(contractId),
    queryFn: () => listComments(contractId),
    enabled: contract.isSuccess,
  });
  const attachments = useQuery({
    queryKey: keys.attachments(contractId),
    queryFn: () => listAttachments(contractId),
    enabled: contract.isSuccess,
  });
  usePageTitle(contract.data ? `Договор ${contract.data.number}` : "Договор");

  const remove = useApiMutation(() => deleteContract(contractId), {
    success: "Договор удалён",
    onSuccess: () => {
      invalidateContractData();
      navigate("/contracts");
    },
  });

  if (contract.isPending)
    return (
      <div className="page">
        <Loading />
      </div>
    );
  if (contract.isError) {
    return (
      <div className="page">
        <ErrorState
          error={contract.error}
          title={contract.error instanceof ApiError && contract.error.status === 404 ? "Договор не найден" : undefined}
          onRetry={() => void contract.refetch()}
        />
      </div>
    );
  }

  const data = contract.data;
  const process = data.process;
  const left = daysUntil(data.valid_to);
  const setTab = (key: string) => {
    const next = new URLSearchParams(params);
    next.set("tab", key);
    setParams(next, { replace: true });
  };

  return (
    <div className="page">
      <PageHeader
        back={
          <Link className="back-link" to="/contracts">
            <ArrowLeft size={14} /> Договоры
          </Link>
        }
        title={
          <span className="row" style={{ gap: 12 }}>
            Договор {data.number}
            <StatusBadge tone={CONTRACT_STATUS_TONE[data.status]}>{label("contract_status", data.status)}</StatusBadge>
          </span>
        }
        description={data.title || undefined}
        actions={
          <>
            <Button variant="outline" icon={Pencil} onClick={() => setEditing(true)}>
              Изменить
            </Button>
            {can("delete_contract") && (
              <Button
                variant="danger"
                icon={Trash2}
                loading={remove.isPending}
                onClick={async () => {
                  const ok = await confirm({
                    title: `Удалить договор ${data.number}?`,
                    message: "Удалятся процесс, комментарии и файлы договора. Действие попадёт в журнал изменений.",
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

      <div className="grid-main-side" style={{ marginBottom: 20 }}>
        <Card title="Сведения">
          <DescriptionList
            items={[
              [
                "Вуз",
                data.university ? (
                  <Link to={`/universities/${data.university_id}`}>
                    {data.university.name}
                    {data.university.short_name ? ` (${data.university.short_name})` : ""}
                  </Link>
                ) : null,
              ],
              ["Ответственный", data.manager?.full_name || <Tag tone="warn">Не назначен</Tag>],
              ["Подписан", formatDate(data.signed_at)],
              [
                "Срок действия",
                data.valid_from || data.valid_to ? (
                  <span>
                    {formatDate(data.valid_from)} — {formatDate(data.valid_to)}
                    {data.status === "active" && left !== null && left <= 60 && (
                      <span className="field__error"> · {left < 0 ? "истёк" : `осталось ${countLabel(left, DAYS)}`}</span>
                    )}
                  </span>
                ) : null,
              ],
              [
                "Состав",
                `${countLabel((data.programs || []).length, ["программа", "программы", "программ"])}, ${countLabel((data.products || []).length, ["продукт", "продукта", "продуктов"])}`,
              ],
              ["Комментарий", data.comment ? <span style={{ whiteSpace: "pre-wrap" }}>{data.comment}</span> : null],
              ["Изменён", formatDateTime(data.updated_at || data.created_at)],
            ]}
          />
        </Card>
        <Card title="Процесс">
          {process ? (
            <div className="stack-s">
              <div className="row-between">
                <strong>{process.stage_name || "—"}</strong>
                <StatusBadge tone={WORKFLOW_TONE[process.status]}>{label("workflow_status", process.status)}</StatusBadge>
              </div>
              {process.days_on_stage !== null && process.days_on_stage !== undefined && process.status === "in_progress" && (
                <span className={process.sla_days && process.days_on_stage > process.sla_days ? "field__error" : "muted"}>
                  {countLabel(process.days_on_stage, DAYS)} на этапе{process.sla_days ? ` при норме ${process.sla_days}` : ""}
                </span>
              )}
              {workflow.data && (
                <div className="progress-steps" aria-hidden="true">
                  {[...(workflow.data.version.stages || [])]
                    .sort((a, b) => a.sort_order - b.sort_order)
                    .map((stage) => {
                      const state = workflow.data?.stage_states?.find((item) => item.stage_id === stage.id)?.state;
                      const cls =
                        state === "completed"
                          ? "done"
                          : state === "active"
                            ? "current"
                            : state === "blocked"
                              ? "blocked"
                              : state === "skipped"
                                ? "skipped"
                                : "";
                      return <span key={stage.id} className={cls} title={stage.name} />;
                    })}
                </div>
              )}
              <Button variant="secondary" size="s" onClick={() => setTab("process")}>
                Открыть схему
              </Button>
            </div>
          ) : (
            <div className="stack-s">
              <span className="muted">Рабочий процесс ещё не запущен.</span>
              <Button variant="secondary" size="s" onClick={() => setTab("process")}>
                Запустить
              </Button>
            </div>
          )}
        </Card>
      </div>

      <Tabs
        value={tab}
        onChange={setTab}
        items={[
          { key: "process", label: "Процесс" },
          { key: "composition", label: "Состав и лицензии" },
          { key: "contacts", label: "Контакты вуза" },
          {
            key: "comments",
            label: "Комментарии и файлы",
            count: (comments.data?.length || 0) + (attachments.data?.length || 0) || undefined,
          },
          { key: "history", label: "История" },
        ]}
      />

      {tab === "process" && (
        <ProcessTab contract={data} workflow={workflow} comments={comments.data || []} attachments={attachments.data || []} />
      )}
      {tab === "composition" && <CompositionTab contract={data} />}
      {tab === "contacts" && <ContactsTab contract={data} />}
      {tab === "comments" && (
        <CommentsTab contract={data} workflow={workflow.data || null} comments={comments} attachments={attachments} />
      )}
      {tab === "history" && (
        <HistoryTab workflow={workflow} comments={comments.data || []} attachments={attachments.data || []} />
      )}

      <ContractFormModal open={editing} onClose={() => setEditing(false)} contract={data} />
    </div>
  );
}

export function refreshContract(contractId: string): void {
  invalidateContractData(contractId);
}
