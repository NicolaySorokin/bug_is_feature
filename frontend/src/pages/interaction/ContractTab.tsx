/**
 * Вкладка «Договор»: договор - необязательный блок взаимодействия.
 *
 * Договор появляется в ходе работы (обычно на обмене документами), у
 * взаимодействия он не больше одного. Вуз и ответственный в договоре не
 * дублируются - они берутся из взаимодействия. А подписант со стороны вуза -
 * свой: договор подписывает не обязательно ответственный контакт, а,
 * например, ректор по уставу или проректор по доверенности. Сервер
 * проверяет даты и статусы: действующий договор подписан, закрытый -
 * с причиной, подписанный не удаляют, а закрывают.
 *
 * Проект договора собирается по типовому шаблону - см. ContractDocument.tsx.
 */
import { useQuery } from "@tanstack/react-query";
import { FilePlus2, FileText, KeyRound, Trash2 } from "lucide-react";
import { useEffect, useState, type FormEvent } from "react";
import { Link } from "react-router-dom";
import { deleteContract, getContract, getUniversity, listInteractionLicenses, saveContract } from "../../api/endpoints";
import { useApiMutation } from "../../api/mutations";
import { invalidateInteractionData, keys, useLabel } from "../../api/queries";
import type { Contract, ContractClosureReason, ContractStatus, InteractionDetail, WorkflowView } from "../../api/types";
import { useSession } from "../../auth/session";
import { useConfirm } from "../../components/Confirm";
import {
  Button,
  Card,
  DescriptionList,
  EmptyState,
  ErrorState,
  Loading,
  SelectField,
  StatusBadge,
  TextAreaField,
  TextField,
} from "../../components/ui";
import { countLabel, DAYS, daysUntil, formatDate, formatDateTime } from "../../lib/format";
import { CONTRACT_STATUS_TONE, LICENSE_TONE } from "../../lib/labels";
import { ContractDocumentModal } from "./ContractDocument";

const STATUSES: ContractStatus[] = ["draft", "active", "suspended", "closed", "cancelled"];
const SIGNED: ContractStatus[] = ["active", "suspended", "closed"];

interface FormState {
  number: string;
  title: string;
  status: ContractStatus;
  closure_reason: ContractClosureReason | "";
  signed_at: string;
  valid_from: string;
  valid_to: string;
  comment: string;
  signatory_name: string;
  signatory_position: string;
  signatory_basis: string;
}

function initial(contract: Contract | null | undefined, interaction: InteractionDetail): FormState {
  return {
    number: contract?.number || "",
    title: contract?.title || interaction.title || "",
    status: contract?.status || "draft",
    closure_reason: contract?.closure_reason || "",
    signed_at: contract?.signed_at || "",
    valid_from: contract?.valid_from || "",
    valid_to: contract?.valid_to || "",
    comment: contract?.comment || "",
    signatory_name: contract?.signatory_name || "",
    signatory_position: contract?.signatory_position || "",
    signatory_basis: contract?.signatory_basis || "",
  };
}

function ContractForm({
  interaction,
  contract,
  onDone,
}: {
  interaction: InteractionDetail;
  contract: Contract | null;
  onDone: () => void;
}) {
  const label = useLabel();
  const [form, setForm] = useState<FormState>(() => initial(contract, interaction));
  const [errors, setErrors] = useState<Partial<Record<keyof FormState, string>>>({});
  useEffect(() => setForm(initial(contract, interaction)), [contract, interaction]);
  const set = <K extends keyof FormState>(key: K, value: FormState[K]) => setForm((current) => ({ ...current, [key]: value }));
  // Подписанта удобно взять из контактов вуза - а можно вписать любого.
  const university = useQuery({
    queryKey: keys.university(interaction.university.id),
    queryFn: () => getUniversity(interaction.university.id),
  });
  const contacts = (university.data?.contacts || []).filter((item) => item.is_active);

  const save = useApiMutation(
    (state: FormState) =>
      saveContract(interaction.id, {
        number: state.number.trim(),
        title: state.title.trim() || null,
        status: state.status,
        closure_reason: state.status === "closed" ? state.closure_reason || null : null,
        signed_at: state.signed_at || null,
        valid_from: state.valid_from || null,
        valid_to: state.valid_to || null,
        comment: state.comment.trim() || null,
        signatory_name: state.signatory_name.trim() || null,
        signatory_position: state.signatory_position.trim() || null,
        signatory_basis: state.signatory_basis.trim() || null,
      }),
    {
      success: contract ? "Договор сохранён" : "Договор заведён",
      onSuccess: () => {
        invalidateInteractionData(interaction.id);
        onDone();
      },
    },
  );

  const submit = (event: FormEvent) => {
    event.preventDefault();
    const found: typeof errors = {};
    if (!form.number.trim()) found.number = "Укажите номер договора";
    if (SIGNED.includes(form.status) && !form.signed_at) found.signed_at = "Действующий договор должен быть подписан";
    if (form.valid_from && form.valid_to && form.valid_to < form.valid_from) found.valid_to = "Окончание раньше начала";
    if (form.signed_at && form.valid_to && form.signed_at > form.valid_to) found.signed_at = "Подписан позже окончания срока";
    if (form.status === "closed" && !form.closure_reason) found.closure_reason = "Укажите, почему договор закрыт";
    setErrors(found);
    if (Object.keys(found).length === 0) save.mutate(form);
  };

  return (
    <form className="form-grid" onSubmit={submit} noValidate>
      <TextField
        label="Номер договора"
        required
        value={form.number}
        onChange={(value) => set("number", value)}
        error={errors.number}
        maxLength={100}
        placeholder="ДГ-2026-001"
      />
      <SelectField
        label="Статус"
        value={form.status}
        onChange={(value) => set("status", value as ContractStatus)}
        options={STATUSES.map((status) => ({ value: status, label: label("contract_status", status) }))}
      />
      <TextField
        className="span-2"
        label="Предмет договора"
        value={form.title}
        onChange={(value) => set("title", value)}
        maxLength={500}
      />
      <TextField
        label="Дата подписания"
        type="date"
        value={form.signed_at}
        onChange={(value) => set("signed_at", value)}
        error={errors.signed_at}
      />
      {form.status === "closed" ? (
        <SelectField
          label="Причина закрытия"
          required
          value={form.closure_reason}
          onChange={(value) => set("closure_reason", value as ContractClosureReason)}
          placeholder="Выберите"
          error={errors.closure_reason}
          options={(["fulfilled", "expired", "terminated"] as const).map((value) => ({
            value,
            label: label("contract_closure_reason", value),
          }))}
        />
      ) : (
        <span />
      )}
      <TextField label="Действует с" type="date" value={form.valid_from} onChange={(value) => set("valid_from", value)} />
      <TextField
        label="Действует по"
        type="date"
        value={form.valid_to}
        onChange={(value) => set("valid_to", value)}
        error={errors.valid_to}
        hint="За 60 дней до окончания ответственный получит предупреждение"
      />
      <div className="span-2 form-section">
        <strong>Подписант со стороны вуза</strong>
        <span className="muted">Кто подписывает договор - не обязательно ответственный от вуза.</span>
      </div>
      {contacts.length > 0 && (
        <SelectField
          className="span-2"
          label="Взять из контактов вуза"
          value=""
          placeholder="Выберите контакт"
          onChange={(id) => {
            const contact = contacts.find((item) => item.id === id);
            if (!contact) return;
            set("signatory_name", contact.full_name);
            set("signatory_position", contact.position || "");
          }}
          options={contacts.map((item) => ({
            value: item.id,
            label: item.position ? `${item.full_name} - ${item.position}` : item.full_name,
          }))}
        />
      )}
      <TextField
        label="ФИО подписанта"
        value={form.signatory_name}
        onChange={(value) => set("signatory_name", value)}
        maxLength={255}
        placeholder="Смирнов Алексей Викторович"
      />
      <TextField
        label="Должность"
        value={form.signatory_position}
        onChange={(value) => set("signatory_position", value)}
        maxLength={255}
        placeholder="Ректор"
      />
      <TextField
        className="span-2"
        label="Действует на основании"
        value={form.signatory_basis}
        onChange={(value) => set("signatory_basis", value)}
        maxLength={255}
        placeholder="Устава"
        hint="Как в договоре после «действует на основании»: «Устава», «доверенности № 12 от 15.01.2026»"
      />
      <TextAreaField
        className="span-2"
        label="Комментарий"
        value={form.comment}
        onChange={(value) => set("comment", value)}
        rows={3}
        maxLength={4000}
      />
      <div className="span-2 row">
        <Button type="submit" loading={save.isPending}>
          {contract ? "Сохранить договор" : "Завести договор"}
        </Button>
        <Button variant="outline" onClick={onDone}>
          Отмена
        </Button>
      </div>
    </form>
  );
}

export function ContractTab({ interaction, workflow }: { interaction: InteractionDetail; workflow: WorkflowView | null }) {
  const label = useLabel();
  const confirm = useConfirm();
  const { can } = useSession();
  const canWork = can("work_interaction");
  const [editing, setEditing] = useState(false);
  const [documentOpen, setDocumentOpen] = useState(false);
  const contract = useQuery({
    queryKey: [...keys.interaction(interaction.id), "contract"],
    queryFn: () => getContract(interaction.id),
  });
  const licenses = useQuery({
    queryKey: keys.licenses(interaction.id),
    queryFn: () => listInteractionLicenses(interaction.id),
  });
  const remove = useApiMutation(() => deleteContract(interaction.id), {
    success: "Черновик договора удалён",
    onSuccess: () => invalidateInteractionData(interaction.id),
  });

  if (contract.isPending) return <Loading />;
  if (contract.isError) return <ErrorState error={contract.error} onRetry={() => void contract.refetch()} />;
  const data = contract.data;
  const closed = interaction.status === "cancelled";

  if (!data && !editing) {
    return (
      <Card>
        <EmptyState
          icon={FilePlus2}
          title="Договора пока нет"
          action={
            canWork && !closed ? (
              <Button icon={FilePlus2} onClick={() => setEditing(true)}>
                Завести договор
              </Button>
            ) : undefined
          }
        >
          Договор появляется в ходе взаимодействия - обычно на этапе обмена документами. Программы, продукты, контакты и файлы
          ведутся и без него.
        </EmptyState>
      </Card>
    );
  }

  if (editing || !data) {
    return (
      <Card title={data ? `Договор ${data.number}` : "Новый договор"}>
        <ContractForm interaction={interaction} contract={data || null} onDone={() => setEditing(false)} />
      </Card>
    );
  }

  const left = daysUntil(data.valid_to);
  const productName = Object.fromEntries(
    (interaction.product_links || []).map((item) => [item.id, item.product?.name || "Продукт"]),
  );

  return (
    <div className="grid-main-side grid-main-side--pair">
      <Card
        className="card--spread"
        title={
          <span className="row" style={{ gap: 10 }}>
            Договор {data.number}
            <StatusBadge tone={CONTRACT_STATUS_TONE[data.status]}>{label("contract_status", data.status)}</StatusBadge>
          </span>
        }
        actions={
          canWork && (
            <>
              <Button variant="secondary" size="s" icon={FileText} onClick={() => setDocumentOpen(true)}>
                Договор по шаблону
              </Button>
              <Button variant="outline" size="s" onClick={() => setEditing(true)}>
                Изменить
              </Button>
              {data.status === "draft" && !data.signed_at && (
                <Button
                  variant="ghost"
                  size="s"
                  icon={Trash2}
                  loading={remove.isPending}
                  onClick={async () => {
                    const ok = await confirm({
                      title: `Удалить черновик договора ${data.number}?`,
                      message: "Удаляется только ошибочный черновик без лицензий. Подписанный договор закрывают.",
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
          )
        }
      >
        <DescriptionList
          items={[
            ["Предмет", data.title],
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
              "Подписант от вуза",
              data.signatory_name ? (
                <span className="stack-s" style={{ gap: 2 }}>
                  <span>{data.signatory_name}</span>
                  <small className="muted">
                    {[data.signatory_position, data.signatory_basis && `на основании ${data.signatory_basis}`]
                      .filter(Boolean)
                      .join(" · ")}
                  </small>
                </span>
              ) : (
                <span className="muted">не указан</span>
              ),
            ],
            ["Причина закрытия", data.closure_reason ? label("contract_closure_reason", data.closure_reason) : null],
            ["Комментарий", data.comment ? <span style={{ whiteSpace: "pre-wrap" }}>{data.comment}</span> : null],
            ["Изменён", formatDateTime(data.updated_at || data.created_at)],
          ]}
        />
      </Card>
      <Card title="Лицензии по договору" className="card--spread">
        {licenses.isPending ? (
          <Loading />
        ) : (licenses.data || []).length === 0 ? (
          <p className="muted card-empty">Лицензий пока нет.</p>
        ) : (
          <div className="files">
            {(licenses.data || []).map((license) => {
              const days = daysUntil(license.valid_to);
              return (
                <div key={license.id} className="file-row">
                  <KeyRound size={16} />
                  <div className="file-row__name">
                    <span>
                      {productName[license.interaction_product_id] || "Продукт"} · {license.number || "без номера"}
                    </span>
                    <small>
                      до {formatDate(license.valid_to)}
                      {license.status === "active" && days !== null && days <= 60 && (
                        <span className="field__error"> · {days < 0 ? "истекла" : `осталось ${countLabel(days, DAYS)}`}</span>
                      )}
                    </small>
                  </div>
                  <StatusBadge tone={LICENSE_TONE[license.status]}>{label("license_status", license.status)}</StatusBadge>
                </div>
              );
            })}
          </div>
        )}
        {/* Пояснение - внизу карточки: она одной высоты с договором рядом. */}
        <p className="card-note">
          Лицензии добавляются к продукту на вкладке{" "}
          <Link to="?tab=composition" replace>
            «Программы и продукты»
          </Link>
          .
        </p>
      </Card>
      <ContractDocumentModal
        interaction={interaction}
        workflow={workflow}
        open={documentOpen}
        onClose={() => setDocumentOpen(false)}
      />
    </div>
  );
}
