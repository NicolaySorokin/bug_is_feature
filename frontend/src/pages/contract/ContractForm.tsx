/**
 * Создание и изменение договора.
 *
 * Менеджер заводит договор на себя; выбрать другого ответственного может
 * руководитель. При создании можно сразу задать состав (ИТ-программы и
 * продукты) и запустить рабочий процесс по шаблону.
 */
import { useEffect, useMemo, useState, type FormEvent } from "react";
import { useNavigate } from "react-router-dom";
import { createContract, updateContract } from "../../api/endpoints";
import { useApiMutation } from "../../api/mutations";
import {
  invalidateContractData,
  queryClient,
  keys,
  useLabel,
  usePrograms,
  useProducts,
  useTemplates,
  useUniversities,
  useUsers,
} from "../../api/queries";
import type { ContractDetail, ContractStatus } from "../../api/types";
import { useSession } from "../../auth/session";
import { Modal } from "../../components/Modal";
import { MultiSelect } from "../../components/MultiSelect";
import { Button, SelectField, TextAreaField, TextField } from "../../components/ui";

const STATUSES: ContractStatus[] = ["draft", "active", "suspended", "closed"];

interface FormState {
  university_id: string;
  number: string;
  title: string;
  status: ContractStatus;
  manager_id: string;
  signed_at: string;
  valid_from: string;
  valid_to: string;
  comment: string;
  program_ids: string[];
  product_ids: string[];
  workflow_template_id: string;
}

function initial(contract?: ContractDetail, universityId?: string, managerId?: string): FormState {
  return {
    university_id: contract?.university_id || universityId || "",
    number: contract?.number || "",
    title: contract?.title || "",
    status: contract?.status || "draft",
    manager_id: contract?.manager_id || managerId || "",
    signed_at: contract?.signed_at || "",
    valid_from: contract?.valid_from || "",
    valid_to: contract?.valid_to || "",
    comment: contract?.comment || "",
    program_ids: [],
    product_ids: [],
    workflow_template_id: "",
  };
}

export function ContractFormModal({
  open,
  onClose,
  contract,
  universityId,
}: {
  open: boolean;
  onClose: () => void;
  contract?: ContractDetail;
  universityId?: string;
}) {
  const { me, can } = useSession();
  const navigate = useNavigate();
  const label = useLabel();
  const universities = useUniversities();
  const users = useUsers();
  const programs = usePrograms();
  const products = useProducts();
  const templates = useTemplates();
  const [form, setForm] = useState<FormState>(() => initial(contract, universityId, me.id));
  const [errors, setErrors] = useState<Partial<Record<keyof FormState, string>>>({});
  const editing = Boolean(contract);

  useEffect(() => {
    if (open) {
      setForm(initial(contract, universityId, me.id));
      setErrors({});
    }
  }, [open, contract, universityId, me.id]);

  // Шаблон процесса по умолчанию - первый действующий.
  useEffect(() => {
    if (!editing && open && !form.workflow_template_id && templates.data?.length) {
      const active = templates.data.find((item) => item.is_active);
      if (active) setForm((current) => ({ ...current, workflow_template_id: active.id }));
    }
  }, [editing, open, form.workflow_template_id, templates.data]);

  const set = <K extends keyof FormState>(key: K, value: FormState[K]) => setForm((current) => ({ ...current, [key]: value }));

  const managers = useMemo(
    () =>
      (users.data || [])
        .filter((user) => user.is_active && (user.roles || []).includes("manager"))
        .map((user) => ({ value: user.id, label: user.full_name })),
    [users.data],
  );

  const save = useApiMutation(
    async (state: FormState) => {
      const common = {
        number: state.number.trim(),
        title: state.title.trim() || null,
        status: state.status,
        signed_at: state.signed_at || null,
        valid_from: state.valid_from || null,
        valid_to: state.valid_to || null,
        comment: state.comment.trim() || null,
      };
      if (contract) {
        const body = can("assign_responsible") ? { ...common, manager_id: state.manager_id || null } : common;
        return updateContract(contract.id, body);
      }
      return createContract({
        ...common,
        university_id: state.university_id,
        manager_id: can("assign_responsible") ? state.manager_id || null : null,
        program_ids: state.program_ids,
        product_ids: state.product_ids,
        workflow_template_id: state.workflow_template_id || null,
      });
    },
    {
      success: editing ? "Договор сохранён" : "Договор создан",
      onSuccess: (saved) => {
        queryClient.setQueryData(keys.contract(saved.id), saved);
        invalidateContractData(saved.id);
        onClose();
        if (!editing) navigate(`/contracts/${saved.id}`);
      },
    },
  );

  const submit = (event: FormEvent) => {
    event.preventDefault();
    const found: typeof errors = {};
    if (!form.university_id) found.university_id = "Выберите вуз";
    if (!form.number.trim()) found.number = "Укажите номер договора";
    if (form.valid_from && form.valid_to && form.valid_to < form.valid_from) found.valid_to = "Окончание раньше начала";
    setErrors(found);
    if (Object.keys(found).length === 0) save.mutate(form);
  };

  const formId = editing ? "contract-edit" : "contract-create";

  return (
    <Modal
      open={open}
      onClose={onClose}
      size="wide"
      dismissable={!save.isPending}
      title={editing ? `Договор ${contract?.number}` : "Новый договор"}
      description={
        editing
          ? "Изменения попадут в журнал изменений."
          : "Договор появится в реестре; по выбранному шаблону сразу запустится рабочий процесс."
      }
      footer={
        <>
          <Button variant="outline" onClick={onClose} disabled={save.isPending}>
            Отмена
          </Button>
          <Button type="submit" form={formId} loading={save.isPending}>
            {editing ? "Сохранить" : "Создать договор"}
          </Button>
        </>
      }
    >
      <form id={formId} className="form-grid" onSubmit={submit} noValidate>
        <SelectField
          className="span-2"
          label="Вуз"
          required
          value={form.university_id}
          onChange={(value) => set("university_id", value)}
          placeholder="Выберите вуз"
          disabled={editing || Boolean(universityId)}
          error={errors.university_id}
          options={(universities.data || []).map((item) => ({
            value: item.id,
            label: item.short_name ? `${item.short_name} — ${item.name}` : item.name,
          }))}
        />
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
          placeholder="Например: сотрудничество по ИТ-программам 2026/27"
        />
        {can("assign_responsible") ? (
          <SelectField
            label="Ответственный"
            value={form.manager_id}
            onChange={(value) => set("manager_id", value)}
            placeholder="Не назначен"
            options={managers}
            hint="Менять ответственного может руководитель"
          />
        ) : (
          <TextField
            label="Ответственный"
            value={contract?.manager?.full_name || me.full_name}
            onChange={() => undefined}
            disabled
            hint="Договор заводится на вас"
          />
        )}
        <TextField label="Дата подписания" type="date" value={form.signed_at} onChange={(value) => set("signed_at", value)} />
        <TextField label="Действует с" type="date" value={form.valid_from} onChange={(value) => set("valid_from", value)} />
        <TextField
          label="Действует по"
          type="date"
          value={form.valid_to}
          onChange={(value) => set("valid_to", value)}
          error={errors.valid_to}
        />
        {!editing && (
          <>
            <MultiSelect
              label="ИТ-программы"
              placeholder="Не выбраны"
              value={form.program_ids}
              onChange={(value) => set("program_ids", value)}
              options={(programs.data || [])
                .filter((item) => item.is_active)
                .map((item) => ({ value: item.id, label: item.name }))}
            />
            <MultiSelect
              label="ИТ-продукты"
              placeholder="Не выбраны"
              value={form.product_ids}
              onChange={(value) => set("product_ids", value)}
              options={(products.data || [])
                .filter((item) => item.is_active)
                .map((item) => ({ value: item.id, label: item.name }))}
            />
            <SelectField
              className="span-2"
              label="Рабочий процесс"
              value={form.workflow_template_id}
              onChange={(value) => set("workflow_template_id", value)}
              placeholder="Не запускать сейчас"
              options={(templates.data || [])
                .filter((item) => item.is_active)
                .map((item) => ({ value: item.id, label: item.name }))}
              hint="Процесс можно запустить и позже - на вкладке «Процесс» договора"
            />
          </>
        )}
        <TextAreaField
          className="span-2"
          label="Комментарий"
          value={form.comment}
          onChange={(value) => set("comment", value)}
          rows={3}
          maxLength={4000}
        />
      </form>
    </Modal>
  );
}
