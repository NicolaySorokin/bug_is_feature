/**
 * Новое взаимодействие и правка его сведений. Договор заводится позже на вкладке «Договор».
 * Без флажка «Запустить процесс» взаимодействие остаётся черновиком.
 */
import { useEffect, useMemo, useState, type FormEvent } from "react";
import { useNavigate } from "react-router-dom";
import { createInteraction, updateInteraction } from "../../api/endpoints";
import { useApiMutation } from "../../api/mutations";
import {
  invalidateInteractionData,
  keys,
  queryClient,
  useDirectory,
  usePrograms,
  useTemplates,
  useUniversities,
} from "../../api/queries";
import type { InteractionDetail } from "../../api/types";
import { useSession } from "../../auth/session";
import { Modal } from "../../components/Modal";
import { MultiSelect } from "../../components/MultiSelect";
import { Button, Checkbox, SelectField, TextAreaField, TextField } from "../../components/ui";

interface FormState {
  university_id: string;
  title: string;
  comment: string;
  manager_id: string;
  template_id: string;
  program_ids: string[];
  start: boolean;
}

function initial(interaction?: InteractionDetail, universityId?: string, managerId?: string): FormState {
  return {
    university_id: interaction?.university.id || universityId || "",
    title: interaction?.title || "",
    comment: interaction?.comment || "",
    manager_id: interaction ? interaction.manager?.id || "" : managerId || "",
    template_id: "",
    program_ids: [],
    start: true,
  };
}

export function InteractionFormModal({
  open,
  onClose,
  interaction,
  universityId,
}: {
  open: boolean;
  onClose: () => void;
  interaction?: InteractionDetail;
  universityId?: string;
}) {
  const { me, can, roles } = useSession();
  const navigate = useNavigate();
  const universities = useUniversities();
  const directory = useDirectory();
  const programs = usePrograms();
  const templates = useTemplates();
  const assign = can("assign_responsible");
  const selfManager = roles.includes("manager");
  const editing = Boolean(interaction);
  const [form, setForm] = useState<FormState>(() => initial(interaction, universityId, selfManager ? me.id : ""));
  const [errors, setErrors] = useState<Partial<Record<keyof FormState, string>>>({});

  useEffect(() => {
    if (open) {
      setForm(initial(interaction, universityId, selfManager ? me.id : ""));
      setErrors({});
    }
  }, [open, interaction, universityId, me.id, selfManager]);

  const set = <K extends keyof FormState>(key: K, value: FormState[K]) => setForm((current) => ({ ...current, [key]: value }));

  // Взаимодействие заводится только с подтверждённым вузом своей области.
  const universityOptions = useMemo(
    () =>
      (universities.data || [])
        .filter((item) => item.status === "confirmed" && (item.in_scope ?? true))
        .map((item) => ({
          value: item.id,
          label: item.short_name ? `${item.short_name} — ${item.name}` : item.name,
        })),
    [universities.data],
  );
  const managerOptions = (directory.data || []).map((user) => ({
    value: user.id,
    label: user.id === me.id ? `${user.full_name} (я)` : user.full_name,
  }));
  const activeTemplates = (templates.data || []).filter((item) => item.is_active && item.active_version_id);

  const save = useApiMutation(
    async (state: FormState) => {
      if (interaction) {
        const body: Record<string, unknown> = { title: state.title.trim() || null, comment: state.comment.trim() || null };
        if (assign && interaction.can_assign) body.manager_id = state.manager_id || null;
        return updateInteraction(interaction.id, body);
      }
      return createInteraction({
        university_id: state.university_id,
        title: state.title.trim() || null,
        comment: state.comment.trim() || null,
        manager_id: assign ? state.manager_id || null : null,
        template_id: state.template_id || null,
        program_ids: state.program_ids,
        start: state.start,
      });
    },
    {
      success: editing ? "Сведения сохранены" : "Взаимодействие заведено",
      onSuccess: (saved) => {
        queryClient.setQueryData(keys.interaction(saved.id), saved);
        invalidateInteractionData(saved.id);
        onClose();
        if (!editing) navigate(`/interactions/${saved.id}`);
      },
    },
  );

  const submit = (event: FormEvent) => {
    event.preventDefault();
    const found: typeof errors = {};
    if (!form.university_id) found.university_id = "Выберите вуз";
    setErrors(found);
    if (Object.keys(found).length === 0) save.mutate(form);
  };

  const formId = editing ? "interaction-edit" : "interaction-create";

  return (
    <Modal
      open={open}
      onClose={onClose}
      size="wide"
      dismissable={!save.isPending}
      title={editing ? "Сведения о взаимодействии" : "Новое взаимодействие"}
      description={
        editing
          ? "Изменения попадут в журнал изменений, смена ответственного - и в историю процесса."
          : "Взаимодействие с вузом: ответственный, программы и ход по процессу. Договор появится позже, если до него дойдёт."
      }
      footer={
        <>
          <Button variant="outline" onClick={onClose} disabled={save.isPending}>
            Отмена
          </Button>
          <Button type="submit" form={formId} loading={save.isPending}>
            {editing ? "Сохранить" : form.start ? "Завести и запустить" : "Завести черновик"}
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
          options={universityOptions}
          hint={editing ? undefined : "Только подтверждённые вузы вашей области данных"}
        />
        <TextField
          className="span-2"
          label="Название"
          value={form.title}
          onChange={(value) => set("title", value)}
          maxLength={500}
          placeholder="Например: подготовка тестировщиков, пилотный поток"
        />
        {assign ? (
          <SelectField
            label="Ответственный"
            value={form.manager_id}
            onChange={(value) => set("manager_id", value)}
            placeholder="Не назначен"
            disabled={editing && !interaction?.can_assign}
            options={managerOptions}
            hint="Менеджер вашей команды"
          />
        ) : (
          <TextField
            label="Ответственный"
            value={interaction?.manager?.full_name || me.full_name}
            onChange={() => undefined}
            disabled
            hint="Взаимодействие ведёте вы"
          />
        )}
        {!editing && (
          <>
            <SelectField
              label="Процесс"
              value={form.template_id}
              onChange={(value) => set("template_id", value)}
              placeholder="Основной шаблон"
              options={activeTemplates.map((item) => ({ value: item.id, label: item.name }))}
            />
            <MultiSelect
              className="span-2"
              label="ИТ-программы"
              placeholder="Можно добавить позже"
              value={form.program_ids}
              onChange={(value) => set("program_ids", value)}
              options={(programs.data || [])
                .filter((item) => item.is_active)
                .map((item) => ({ value: item.id, label: item.name }))}
            />
            <div className="span-2">
              <Checkbox
                label="Сразу запустить процесс - взаимодействие встанет на стартовый этап"
                checked={form.start}
                onChange={(value) => set("start", value)}
              />
            </div>
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
