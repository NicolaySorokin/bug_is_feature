/**
 * Создание и изменение вуза. Руководитель и администратор заводят подтверждённый вуз, менеджер
 * предлагает, и вуз ждёт проверки. Дубль по ИНН или названию завести нельзя.
 */
import { useEffect, useState, type FormEvent } from "react";
import { useNavigate } from "react-router-dom";
import { ApiError } from "../api/client";
import { createUniversity, updateUniversity } from "../api/endpoints";
import { useApiMutation } from "../api/mutations";
import { invalidateInteractionData, useDirectory } from "../api/queries";
import type { UniversityDetail } from "../api/types";
import { useSession } from "../auth/session";
import { Modal } from "../components/Modal";
import { Button, Notice, SelectField, TextAreaField, TextField } from "../components/ui";

interface State {
  name: string;
  short_name: string;
  inn: string;
  city: string;
  website: string;
  description: string;
  requisites: string;
  manager_id: string;
}

export function UniversityFormModal({
  open,
  onClose,
  university,
}: {
  open: boolean;
  onClose: () => void;
  university?: UniversityDetail;
}) {
  const navigate = useNavigate();
  const { can } = useSession();
  const manages = can("manage_universities");
  const assign = can("assign_responsible");
  const directory = useDirectory();
  const [state, setState] = useState<State>({
    name: "",
    short_name: "",
    inn: "",
    city: "",
    website: "",
    description: "",
    requisites: "",
    manager_id: "",
  });
  const [error, setError] = useState<string | null>(null);
  const [duplicateId, setDuplicateId] = useState<string | null>(null);

  useEffect(() => {
    if (!open) return;
    setError(null);
    setDuplicateId(null);
    setState({
      name: university?.name || "",
      short_name: university?.short_name || "",
      inn: university?.inn || "",
      city: university?.city || "",
      website: university?.website || "",
      description: university?.description || "",
      requisites: university?.requisites || "",
      manager_id: university?.manager_id || "",
    });
  }, [open, university]);

  const save = useApiMutation(
    () => {
      const body = {
        name: state.name.trim(),
        short_name: state.short_name.trim() || null,
        inn: state.inn.trim() || null,
        city: state.city.trim() || null,
        website: state.website.trim() || null,
        description: state.description.trim() || null,
        requisites: state.requisites.trim() || null,
        ...(assign ? { manager_id: state.manager_id || null } : {}),
      };
      return university ? updateUniversity(university.id, body) : createUniversity(body);
    },
    {
      success: university ? "Вуз сохранён" : manages ? "Вуз добавлен" : "Вуз отправлен на проверку",
      onSuccess: (saved) => {
        invalidateInteractionData();
        onClose();
        if (!university) navigate(`/universities/${saved.id}`);
      },
    },
  );

  useEffect(() => {
    const failure = save.error;
    if (failure instanceof ApiError && failure.status === 409) {
      const id = failure.details?.university_id;
      setDuplicateId(typeof id === "string" ? id : null);
    }
  }, [save.error]);

  const submit = (event: FormEvent) => {
    event.preventDefault();
    if (!state.name.trim()) {
      setError("Укажите название вуза");
      return;
    }
    if (state.inn.trim() && !/^\d{10}(\d{2})?$/.test(state.inn.trim())) {
      setError("ИНН - 10 или 12 цифр");
      return;
    }
    setError(null);
    save.mutate(undefined);
  };

  const set = <K extends keyof State>(key: K, value: State[K]) => setState((current) => ({ ...current, [key]: value }));

  return (
    <Modal
      open={open}
      onClose={onClose}
      size="wide"
      title={university ? university.name : manages ? "Новый вуз" : "Предложить вуз"}
      description={
        university
          ? undefined
          : manages
            ? "Вуз появится в справочнике подтверждённым."
            : "Вуз уйдёт на проверку руководителю: пока его не подтвердят, взаимодействие с ним не завести."
      }
      footer={
        <>
          <Button variant="outline" onClick={onClose}>
            Отмена
          </Button>
          <Button type="submit" form="university-form" loading={save.isPending}>
            {university ? "Сохранить" : manages ? "Добавить" : "Отправить на проверку"}
          </Button>
        </>
      }
    >
      <form id="university-form" className="form-grid" onSubmit={submit} noValidate>
        {duplicateId && (
          <div className="span-2">
            <Notice
              tone="warning"
              title="Такой вуз уже есть"
              actions={[
                {
                  label: "Открыть существующую запись",
                  onClick: () => {
                    onClose();
                    navigate(`/universities/${duplicateId}`);
                  },
                },
              ]}
            >
              Дубль не заводится: работайте с существующей записью или объедините записи.
            </Notice>
          </div>
        )}
        <TextField
          className="span-2"
          label="Полное название"
          required
          value={state.name}
          onChange={(value) => set("name", value)}
          error={error}
          maxLength={500}
        />
        <TextField
          label="Краткое название"
          value={state.short_name}
          onChange={(value) => set("short_name", value)}
          maxLength={100}
          placeholder="МТУСИ"
          hint="Показывается в списках, уведомлениях и на главной"
        />
        <TextField
          label="ИНН"
          value={state.inn}
          onChange={(value) => set("inn", value.replace(/\D/g, ""))}
          maxLength={12}
          hint="Стабильный ключ вуза: по нему находятся дубли"
        />
        <TextField label="Город" value={state.city} onChange={(value) => set("city", value)} maxLength={100} />
        <TextField
          label="Сайт"
          type="url"
          value={state.website}
          onChange={(value) => set("website", value)}
          placeholder="https://"
          maxLength={255}
        />
        {assign && (
          <SelectField
            label="Менеджер по умолчанию"
            value={state.manager_id}
            onChange={(value) => set("manager_id", value)}
            placeholder="Не назначен"
            options={(directory.data || []).map((user) => ({ value: user.id, label: user.full_name }))}
            hint="Станет ответственным за новые взаимодействия вуза"
          />
        )}
        <TextAreaField
          className="span-2"
          label="Описание"
          value={state.description}
          onChange={(value) => set("description", value)}
          rows={3}
          maxLength={4000}
        />
        <TextAreaField
          className="span-2"
          label="Реквизиты для договора"
          value={state.requisites}
          onChange={(value) => set("requisites", value)}
          rows={3}
          maxLength={4000}
          placeholder={"Адрес: ...\nКПП ..., ОГРН ...\nр/с ... в банке ..., БИК ..."}
          hint="Как их пишут в договоре: подставляются в проект договора по шаблону"
        />
      </form>
    </Modal>
  );
}
