/**
 * Шаблоны договоров, их ведёт руководитель. Поле {{...}} вставляется кнопкой в место курсора,
 * неизвестное поле сервер не пропустит.
 *
 * Текст правится в обычном <textarea>: при вставке из кода курсор и прокрутка должны остаться на месте.
 */
import { useQuery } from "@tanstack/react-query";
import { Pencil, Plus } from "lucide-react";
import { useEffect, useId, useRef, useState } from "react";
import { listContractTemplates, listTemplateFields, saveContractTemplate } from "../../api/endpoints";
import { useApiMutation } from "../../api/mutations";
import { keys, queryClient } from "../../api/queries";
import type { ContractTemplate, TemplateField } from "../../api/types";
import { Modal } from "../../components/Modal";
import { Button, Card, EmptyState, ErrorState, Field, Loading, StatusBadge, Switch, TextField } from "../../components/ui";
import { formatDateTime } from "../../lib/format";

function TemplateModal({
  template,
  fields,
  onClose,
}: {
  template: ContractTemplate | "new" | null;
  fields: TemplateField[];
  onClose: () => void;
}) {
  const current = template === "new" ? null : template;
  const [name, setName] = useState("");
  const [body, setBody] = useState("");
  const [active, setActive] = useState(true);
  const [error, setError] = useState<string>();
  const editor = useRef<HTMLTextAreaElement>(null);
  const editorId = useId();

  useEffect(() => {
    setName(current?.name || "");
    setBody(current?.body || "");
    setActive(current?.is_active ?? true);
    setError(undefined);
  }, [template, current]);

  const save = useApiMutation(() => saveContractTemplate(current?.id || null, { name: name.trim(), body, is_active: active }), {
    success: current ? "Шаблон сохранён" : "Шаблон добавлен",
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: keys.contractTemplates });
      onClose();
    },
  });

  // Поле вставляется в место курсора: выделение сохраняется, даже когда фокус ушёл на кнопку.
  const insert = (key: string) => {
    const token = `{{${key}}}`;
    const area = editor.current;
    const at = area ? area.selectionStart : body.length;
    const end = area ? area.selectionEnd : body.length;
    setBody(body.slice(0, at) + token + body.slice(end));
    requestAnimationFrame(() => {
      area?.focus();
      area?.setSelectionRange(at + token.length, at + token.length);
    });
  };

  const groups = fields.reduce<Record<string, TemplateField[]>>((result, field) => {
    (result[field.group] ||= []).push(field);
    return result;
  }, {});

  return (
    <Modal
      open={template !== null}
      onClose={onClose}
      size="xl"
      title={current ? `Шаблон «${current.name}»` : "Новый шаблон договора"}
      description="Строка «# ...» - заголовок по центру, «## ...» - заголовок раздела, «- ...» - пункт списка. Пустая строка разделяет абзацы."
      footer={
        <>
          <Button variant="outline" onClick={onClose}>
            Отмена
          </Button>
          <Button
            loading={save.isPending}
            onClick={() => {
              if (!name.trim() || !body.trim()) {
                setError(!name.trim() ? "Укажите название шаблона" : "Шаблон пустой");
                return;
              }
              save.mutate();
            }}
          >
            {current ? "Сохранить" : "Добавить"}
          </Button>
        </>
      }
    >
      <div className="template-editor">
        <div className="stack">
          <TextField label="Название" required value={name} onChange={setName} maxLength={255} error={error} />
          <Switch label="Используется - менеджеры формируют по нему договоры" checked={active} onChange={setActive} />
          <Field label="Текст договора" htmlFor={editorId}>
            <textarea
              id={editorId}
              ref={editor}
              className="control"
              value={body}
              rows={22}
              maxLength={50000}
              spellCheck
              onChange={(event) => setBody(event.target.value)}
            />
          </Field>
        </div>
        <aside className="template-fields" aria-label="Поля шаблона">
          <strong>Поля</strong>
          <span className="muted">Нажмите, чтобы вставить в место курсора</span>
          {Object.entries(groups).map(([group, items]) => (
            <div key={group} className="template-fields__group">
              <span className="template-fields__title">{group}</span>
              {items.map((field) => (
                <button key={field.key} type="button" className="template-field" onClick={() => insert(field.key)}>
                  <code>{`{{${field.key}}}`}</code>
                  <span>{field.label}</span>
                </button>
              ))}
            </div>
          ))}
        </aside>
      </div>
    </Modal>
  );
}

export function ContractTemplates() {
  const templates = useQuery({ queryKey: keys.contractTemplates, queryFn: listContractTemplates });
  const fields = useQuery({ queryKey: keys.templateFields, queryFn: listTemplateFields, staleTime: Infinity });
  const [edit, setEdit] = useState<ContractTemplate | "new" | null>(null);
  const items = templates.data || [];

  return (
    <>
      <div className="templates-head">
        <p className="muted">
          Менеджер формирует по шаблону проект договора во взаимодействии: вкладка «Договор» → «Договор по шаблону».
        </p>
        <Button icon={Plus} onClick={() => setEdit("new")}>
          Добавить шаблон
        </Button>
      </div>
      <Card flush title={`Шаблоны договоров: ${items.length}`}>
        {templates.isPending ? (
          <Loading />
        ) : templates.isError ? (
          <ErrorState error={templates.error} onRetry={() => void templates.refetch()} />
        ) : items.length === 0 ? (
          <EmptyState title="Шаблонов нет" />
        ) : (
          <div className="table-wrap">
            <table className="data-table data-table--cards">
              <thead>
                <tr>
                  <th scope="col">Название</th>
                  <th scope="col">Изменён</th>
                  <th scope="col">Состояние</th>
                  <th scope="col" className="col-actions">
                    <span className="visually-hidden">Действия</span>
                  </th>
                </tr>
              </thead>
              <tbody>
                {items.map((item) => (
                  <tr key={item.id}>
                    <td className="cell-primary">
                      <div className="cell-title">
                        <button type="button" className="link-btn" onClick={() => setEdit(item)}>
                          {item.name}
                        </button>
                        <small>
                          {item.body
                            .split("\n")
                            .find((line) => line.trim())
                            ?.replace(/^#+\s*/, "")}
                        </small>
                      </div>
                    </td>
                    <td data-label="Изменён">
                      {formatDateTime(item.updated_at)}
                      {item.updated_by && <small className="muted"> · {item.updated_by.full_name}</small>}
                    </td>
                    <td data-label="Состояние">
                      {item.is_active ? (
                        <StatusBadge tone="success">Используется</StatusBadge>
                      ) : (
                        <StatusBadge>Выключен</StatusBadge>
                      )}
                    </td>
                    <td className="col-actions" data-label="">
                      <button
                        type="button"
                        className="icon-btn"
                        aria-label={`Изменить ${item.name}`}
                        onClick={() => setEdit(item)}
                      >
                        <Pencil size={16} />
                      </button>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </Card>
      <TemplateModal template={edit} fields={fields.data || []} onClose={() => setEdit(null)} />
    </>
  );
}
