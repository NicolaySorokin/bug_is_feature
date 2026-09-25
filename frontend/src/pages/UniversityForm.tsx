/** Создание и изменение вуза (руководитель и администратор). */
import { useEffect, useState, type FormEvent } from "react";
import { useNavigate } from "react-router-dom";
import { createUniversity, updateUniversity } from "../api/endpoints";
import { useApiMutation } from "../api/mutations";
import { invalidateContractData, useUsers } from "../api/queries";
import type { UniversityDetail } from "../api/types";
import { Modal } from "../components/Modal";
import { Button, SelectField, Switch, TextAreaField, TextField } from "../components/ui";

interface State {
  name: string;
  short_name: string;
  city: string;
  website: string;
  description: string;
  manager_id: string;
  is_active: boolean;
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
  const users = useUsers();
  const [state, setState] = useState<State>({
    name: "",
    short_name: "",
    city: "",
    website: "",
    description: "",
    manager_id: "",
    is_active: true,
  });
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!open) return;
    setError(null);
    setState({
      name: university?.name || "",
      short_name: university?.short_name || "",
      city: university?.city || "",
      website: university?.website || "",
      description: university?.description || "",
      manager_id: university?.manager_id || "",
      is_active: university?.is_active ?? true,
    });
  }, [open, university]);

  const save = useApiMutation(
    () => {
      const body = {
        name: state.name.trim(),
        short_name: state.short_name.trim() || null,
        city: state.city.trim() || null,
        website: state.website.trim() || null,
        description: state.description.trim() || null,
        manager_id: state.manager_id || null,
      };
      return university ? updateUniversity(university.id, { ...body, is_active: state.is_active }) : createUniversity(body);
    },
    {
      success: university ? "Вуз сохранён" : "Вуз добавлен",
      onSuccess: (saved) => {
        invalidateContractData();
        onClose();
        if (!university) navigate(`/universities/${saved.id}`);
      },
    },
  );

  const submit = (event: FormEvent) => {
    event.preventDefault();
    if (!state.name.trim()) {
      setError("Укажите название вуза");
      return;
    }
    save.mutate(undefined);
  };

  const set = <K extends keyof State>(key: K, value: State[K]) => setState((current) => ({ ...current, [key]: value }));

  return (
    <Modal
      open={open}
      onClose={onClose}
      size="wide"
      title={university ? university.name : "Новый вуз"}
      footer={
        <>
          <Button variant="outline" onClick={onClose}>
            Отмена
          </Button>
          <Button type="submit" form="university-form" loading={save.isPending}>
            Сохранить
          </Button>
        </>
      }
    >
      <form id="university-form" className="form-grid" onSubmit={submit} noValidate>
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
        <SelectField
          label="Ответственный от ИТ Школы"
          value={state.manager_id}
          onChange={(value) => set("manager_id", value)}
          placeholder="Не назначен"
          options={(users.data || [])
            .filter((user) => user.is_active && (user.roles || []).includes("manager"))
            .map((user) => ({ value: user.id, label: user.full_name }))}
        />
        <TextAreaField
          className="span-2"
          label="Описание"
          value={state.description}
          onChange={(value) => set("description", value)}
          rows={3}
          maxLength={4000}
        />
        {university && <Switch label="Вуз в работе" checked={state.is_active} onChange={(value) => set("is_active", value)} />}
      </form>
    </Modal>
  );
}
