/**
 * Карточка вуза: статус записи, менеджер по умолчанию, контакты вуза,
 * взаимодействия с ним и (для администратора) журнал изменений.
 *
 * Руководитель подтверждает вуз, переводит в архив и объединяет дубль
 * с итоговой записью: контакты, взаимодействия и доступы переходят к ней.
 */
import { useQuery } from "@tanstack/react-query";
import {
  Archive,
  ArchiveRestore,
  ArrowLeft,
  CheckCircle2,
  ExternalLink,
  GitMerge,
  Mail,
  Pencil,
  Phone,
  Plus,
  Trash2,
  UserPlus,
} from "lucide-react";
import { useEffect, useState } from "react";
import { Link, useNavigate, useParams } from "react-router-dom";
import { ApiError } from "../api/client";
import {
  archiveUniversity,
  confirmUniversity,
  createContact,
  deleteContact,
  deleteUniversity,
  getUniversity,
  listAudit,
  listInteractions,
  mergeUniversity,
  updateContact,
} from "../api/endpoints";
import { useApiMutation } from "../api/mutations";
import { invalidateInteractionData, keys, useLabel, useUniversities } from "../api/queries";
import type { UniversityContact } from "../api/types";
import { useSession } from "../auth/session";
import { useConfirm } from "../components/Confirm";
import { Modal } from "../components/Modal";
import {
  Button,
  Card,
  DescriptionList,
  EmptyState,
  ErrorState,
  Loading,
  PageHeader,
  SelectField,
  StatusBadge,
  Tag,
  TextField,
} from "../components/ui";
import { InteractionFormModal } from "../features/interaction/InteractionForm";
import { ContractCell, interactionTitle, SlaChip, StageCell, StatusCell } from "../features/interaction/parts";
import { formatDateTime } from "../lib/format";
import { UNIVERSITY_TONE } from "../lib/labels";
import { usePageTitle } from "../lib/usePageTitle";
import { UniversityFormModal } from "./UniversityForm";
import { AuditEntries } from "./admin/AuditPage";

const ORIGIN: Record<string, string> = {
  manual: "Заведён вручную",
  import: "Загрузка из Excel",
  site: "Сайт ИТ Школы",
  lms: "LMS",
};

interface ContactState {
  full_name: string;
  position: string;
  phone: string;
  email: string;
}

function ContactModal({
  open,
  onClose,
  universityId,
  contact,
}: {
  open: boolean;
  onClose: () => void;
  universityId: string;
  contact: UniversityContact | null;
}) {
  const [state, setState] = useState<ContactState>({ full_name: "", position: "", phone: "", email: "" });
  const [error, setError] = useState<string | null>(null);
  useEffect(() => {
    if (!open) return;
    setError(null);
    setState({
      full_name: contact?.full_name || "",
      position: contact?.position || "",
      phone: contact?.phone || "",
      email: contact?.email || "",
    });
  }, [open, contact]);
  const save = useApiMutation(
    () => {
      const body = {
        full_name: state.full_name.trim(),
        position: state.position.trim() || null,
        phone: state.phone.trim() || null,
        email: state.email.trim() || null,
      };
      return contact ? updateContact(universityId, contact.id, body) : createContact(universityId, body);
    },
    {
      success: contact ? "Контакт сохранён" : "Контакт добавлен",
      onSuccess: () => {
        invalidateInteractionData();
        onClose();
      },
    },
  );
  const set = (key: keyof ContactState, value: string) => setState((current) => ({ ...current, [key]: value }));
  return (
    <Modal
      open={open}
      onClose={onClose}
      title={contact ? contact.full_name : "Новый контакт вуза"}
      description="Сотрудник вуза, с которым ведётся работа. Контакт хранится у вуза и назначается во взаимодействиях - без дублей."
      footer={
        <>
          <Button variant="outline" onClick={onClose}>
            Отмена
          </Button>
          <Button
            loading={save.isPending}
            onClick={() => {
              if (!state.full_name.trim()) setError("Укажите ФИО");
              else if (state.email && !/^\S+@\S+\.\S+$/.test(state.email.trim())) setError("Проверьте адрес почты");
              else save.mutate(undefined);
            }}
          >
            Сохранить
          </Button>
        </>
      }
    >
      <div className="form-grid">
        <TextField
          className="span-2"
          label="ФИО"
          required
          value={state.full_name}
          onChange={(value) => set("full_name", value)}
          error={error}
          maxLength={255}
        />
        <TextField
          className="span-2"
          label="Должность"
          value={state.position}
          onChange={(value) => set("position", value)}
          maxLength={255}
          placeholder="Проректор по цифровизации"
        />
        <TextField
          label="Телефон"
          type="tel"
          value={state.phone}
          onChange={(value) => set("phone", value)}
          maxLength={50}
          placeholder="+7 900 000-00-00"
        />
        <TextField label="Почта" type="email" value={state.email} onChange={(value) => set("email", value)} maxLength={255} />
      </div>
    </Modal>
  );
}

/** Объединение дубля с итоговой записью. */
function MergeDialog({
  open,
  onClose,
  sourceId,
  sourceName,
}: {
  open: boolean;
  onClose: () => void;
  sourceId: string;
  sourceName: string;
}) {
  const navigate = useNavigate();
  const universities = useUniversities();
  const [targetId, setTargetId] = useState("");
  useEffect(() => setTargetId(""), [open]);
  const merge = useApiMutation(() => mergeUniversity(sourceId, targetId), {
    success: "Записи объединены",
    onSuccess: (target) => {
      invalidateInteractionData();
      onClose();
      navigate(`/universities/${target.id}`);
    },
  });
  return (
    <Modal
      open={open}
      onClose={onClose}
      title={`Объединить «${sourceName}» с другой записью`}
      description="Контакты, взаимодействия и доступы перейдут к итоговой записи, а эта останется в архиве со ссылкой на неё."
      footer={
        <>
          <Button variant="outline" onClick={onClose}>
            Отмена
          </Button>
          <Button icon={GitMerge} disabled={!targetId} loading={merge.isPending} onClick={() => merge.mutate(undefined)}>
            Объединить
          </Button>
        </>
      }
    >
      <SelectField
        label="Итоговая запись"
        required
        value={targetId}
        onChange={setTargetId}
        placeholder="Выберите вуз"
        options={(universities.data || [])
          .filter((item) => item.id !== sourceId && item.status !== "archived")
          .map((item) => ({ value: item.id, label: item.short_name ? `${item.short_name} — ${item.name}` : item.name }))}
      />
    </Modal>
  );
}

export default function UniversityPage() {
  const { universityId = "" } = useParams();
  const navigate = useNavigate();
  const label = useLabel();
  const confirm = useConfirm();
  const { can, me, roles, business } = useSession();
  const [editing, setEditing] = useState(false);
  const [merging, setMerging] = useState(false);
  const [contact, setContact] = useState<UniversityContact | null | undefined>(undefined);
  const [creatingInteraction, setCreatingInteraction] = useState(false);

  const university = useQuery({ queryKey: keys.university(universityId), queryFn: () => getUniversity(universityId) });
  const interactions = useQuery({
    queryKey: [...keys.interactions, { university_id: universityId, limit: 100 }],
    queryFn: () => listInteractions({ university_id: universityId, limit: 100 }),
    enabled: business,
  });
  const audit = useQuery({
    queryKey: ["audit", "university", universityId],
    queryFn: () => listAudit({ entity_type: "universities", entity_id: universityId, limit: 20 }),
    enabled: can("view_audit"),
  });
  usePageTitle(university.data?.short_name || university.data?.name || "Вуз");

  const removeContact = useApiMutation((id: string) => deleteContact(universityId, id), {
    success: "Контакт удалён",
    onSuccess: () => invalidateInteractionData(),
  });
  // Контакт из истории взаимодействий не удаляют, а переводят в архив.
  const toggleContact = useApiMutation(
    (item: UniversityContact) => updateContact(universityId, item.id, { is_active: !item.is_active }),
    {
      success: (saved) => (saved.is_active ? "Контакт возвращён из архива" : "Контакт переведён в архив"),
      onSuccess: () => invalidateInteractionData(),
    },
  );
  const remove = useApiMutation(() => deleteUniversity(universityId), {
    success: "Вуз удалён",
    onSuccess: () => {
      invalidateInteractionData();
      navigate("/universities");
    },
  });
  const confirmRecord = useApiMutation(() => confirmUniversity(universityId), {
    success: "Вуз подтверждён",
    onSuccess: () => invalidateInteractionData(),
  });
  const archive = useApiMutation(() => archiveUniversity(universityId), {
    success: "Вуз переведён в архив",
    onSuccess: () => invalidateInteractionData(),
  });

  if (university.isPending)
    return (
      <div className="page">
        <Loading />
      </div>
    );
  if (university.isError) {
    return (
      <div className="page">
        <ErrorState
          error={university.error}
          title={university.error instanceof ApiError && university.error.status === 404 ? "Вуз не найден" : undefined}
          onRetry={() => void university.refetch()}
        />
      </div>
    );
  }
  const data = university.data;
  const manages = can("manage_universities");
  const manageContacts =
    data.in_scope !== false && (roles.includes("head") || (data.manager_id === me.id && can("edit_university_contacts")));
  const merged = Boolean(data.merged_into_id);
  const canCreate = can("create_interaction") && data.status === "confirmed" && data.in_scope !== false;
  // Действующие контакты - сверху, архивные - после них (внутри групп - по ФИО).
  const contacts = [...(data.contacts || [])].sort((a, b) => Number(!a.is_active) - Number(!b.is_active));

  return (
    <div className="page">
      <PageHeader
        back={
          <Link className="back-link" to="/universities">
            <ArrowLeft size={14} /> Вузы
          </Link>
        }
        title={
          <span className="row" style={{ gap: 12 }}>
            {data.short_name || data.name}
            <StatusBadge tone={UNIVERSITY_TONE[data.status]}>{label("university_status", data.status)}</StatusBadge>
          </span>
        }
        description={
          merged ? (
            <>
              Запись объединена с <Link to={`/universities/${data.merged_into_id}`}>итоговой</Link> - работайте с ней.
            </>
          ) : data.status === "pending" ? (
            "Вуз ждёт проверки: пока его не подтвердят, взаимодействие с ним не завести."
          ) : undefined
        }
        actions={
          <>
            {canCreate && (
              <Button icon={Plus} onClick={() => setCreatingInteraction(true)}>
                Новое взаимодействие
              </Button>
            )}
            {manages && !merged && data.status !== "confirmed" && (
              <Button
                variant="outline"
                icon={CheckCircle2}
                loading={confirmRecord.isPending}
                onClick={() => confirmRecord.mutate(undefined)}
              >
                {data.status === "archived" ? "Вернуть из архива" : "Подтвердить"}
              </Button>
            )}
            {manages && !merged && (
              <Button variant="outline" icon={GitMerge} onClick={() => setMerging(true)}>
                Объединить с…
              </Button>
            )}
            {manages && !merged && (
              <Button variant="outline" icon={Pencil} onClick={() => setEditing(true)}>
                Изменить
              </Button>
            )}
            {manages && !merged && data.status !== "archived" && (
              <Button
                variant="outline"
                icon={Archive}
                loading={archive.isPending}
                onClick={async () => {
                  const ok = await confirm({
                    title: `Перевести «${data.short_name || data.name}» в архив?`,
                    message: "Начатые взаимодействия продолжатся, новые с вузом заводиться не будут.",
                    confirmLabel: "В архив",
                  });
                  if (ok !== null) archive.mutate(undefined);
                }}
              >
                В архив
              </Button>
            )}
            {manages && (data.interactions_count || 0) === 0 && (
              <Button
                variant="danger"
                icon={Trash2}
                onClick={async () => {
                  const ok = await confirm({
                    title: `Удалить вуз «${data.name}»?`,
                    message: "Удаляется только ошибочная запись без взаимодействий. Вуз с историей переводят в архив.",
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

      <div className="grid-main-side">
        <div className="stack">
          {business && data.in_scope !== false && (
            <Card
              title="Взаимодействия"
              description={`Всего ${data.interactions_count || 0}, активных ${data.active_interactions_count || 0}`}
              flush
            >
              {interactions.isPending ? (
                <Loading />
              ) : interactions.isError ? (
                <ErrorState error={interactions.error} onRetry={() => void interactions.refetch()} />
              ) : interactions.data.items.length === 0 ? (
                <EmptyState
                  title="Взаимодействий нет"
                  action={
                    canCreate ? (
                      <Button icon={Plus} onClick={() => setCreatingInteraction(true)}>
                        Новое взаимодействие
                      </Button>
                    ) : undefined
                  }
                />
              ) : (
                <div className="table-wrap">
                  <table className="data-table data-table--cards">
                    <thead>
                      <tr>
                        <th scope="col">Взаимодействие</th>
                        <th scope="col">Статус</th>
                        <th scope="col">Этап</th>
                        <th scope="col">Срок этапа</th>
                        <th scope="col">Договор</th>
                      </tr>
                    </thead>
                    <tbody>
                      {interactions.data.items.map((row) => (
                        <tr key={row.id} className="clickable" onClick={() => navigate(`/interactions/${row.id}`)}>
                          <td className="cell-primary">
                            <div className="cell-title">
                              <Link to={`/interactions/${row.id}`}>
                                <strong>{interactionTitle(row)}</strong>
                              </Link>
                              <small>{row.manager?.full_name || "Ответственный не назначен"}</small>
                            </div>
                          </td>
                          <td data-label="Статус">
                            <StatusCell status={row.status} outcome={row.outcome} />
                          </td>
                          <td data-label="Этап">
                            <StageCell
                              stageName={row.stage?.stage_name}
                              nextActions={row.stage?.next_actions}
                              status={row.status}
                            />
                          </td>
                          <td data-label="Срок этапа">
                            <SlaChip sla={row.stage?.sla} status={row.status} />
                          </td>
                          <td data-label="Договор">
                            <ContractCell contract={row.contract} />
                          </td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              )}
            </Card>
          )}

          <Card
            title="Контакты вуза"
            description="Сотрудники вуза, с которыми ведётся работа. Во взаимодействии их назначают на вкладке «Контакты»."
            flush
            actions={
              manageContacts && (
                <Button variant="secondary" size="s" icon={UserPlus} onClick={() => setContact(null)}>
                  Добавить
                </Button>
              )
            }
          >
            {contacts.length === 0 ? (
              <EmptyState title="Контактов нет">
                Добавьте ответственных от вуза - их можно будет назначить во взаимодействиях.
              </EmptyState>
            ) : (
              <div className="list">
                {contacts.map((item) => (
                  <div key={item.id} className="list-item" style={{ alignItems: "flex-start" }}>
                    <div className="list-item__main">
                      <strong className="row" style={{ gap: 6 }}>
                        {item.full_name}
                        {!item.is_active && <Tag>в архиве</Tag>}
                      </strong>
                      <small>{item.position || "Должность не указана"}</small>
                      <div className="row" style={{ gap: 12, marginTop: 4 }}>
                        {item.phone && (
                          <a href={`tel:${item.phone}`} className="row" style={{ gap: 4 }}>
                            <Phone size={13} /> {item.phone}
                          </a>
                        )}
                        {item.email && (
                          <a href={`mailto:${item.email}`} className="row" style={{ gap: 4 }}>
                            <Mail size={13} /> {item.email}
                          </a>
                        )}
                      </div>
                    </div>
                    {manageContacts && (
                      <div className="row">
                        <button
                          type="button"
                          className="icon-btn"
                          aria-label={`Изменить ${item.full_name}`}
                          onClick={() => setContact(item)}
                        >
                          <Pencil size={16} />
                        </button>
                        {item.is_active ? (
                          <button
                            type="button"
                            className="icon-btn"
                            aria-label={`Перевести в архив ${item.full_name}`}
                            disabled={toggleContact.isPending}
                            onClick={async () => {
                              const ok = await confirm({
                                title: `Перевести контакт ${item.full_name} в архив?`,
                                message:
                                  "В прошлых взаимодействиях контакт останется, но назначить его в новые будет нельзя. Вернуть из архива можно в любой момент.",
                                confirmLabel: "В архив",
                              });
                              if (ok !== null) toggleContact.mutate(item);
                            }}
                          >
                            <Archive size={16} />
                          </button>
                        ) : (
                          <button
                            type="button"
                            className="icon-btn"
                            aria-label={`Вернуть из архива ${item.full_name}`}
                            disabled={toggleContact.isPending}
                            onClick={() => toggleContact.mutate(item)}
                          >
                            <ArchiveRestore size={16} />
                          </button>
                        )}
                        <button
                          type="button"
                          className="icon-btn"
                          aria-label={`Удалить ${item.full_name}`}
                          onClick={async () => {
                            const ok = await confirm({
                              title: `Удалить контакт ${item.full_name}?`,
                              message:
                                "Удаляют контакт, заведённый по ошибке. Контакт, назначенный во взаимодействиях, не удаляется - его переводят в архив, чтобы история осталась читаемой.",
                              confirmLabel: "Удалить",
                              danger: true,
                            });
                            if (ok !== null) removeContact.mutate(item.id);
                          }}
                        >
                          <Trash2 size={16} />
                        </button>
                      </div>
                    )}
                  </div>
                ))}
              </div>
            )}
          </Card>
        </div>

        <div className="stack">
          <Card title="Сведения">
            <DescriptionList
              items={[
                ["Полное название", data.name],
                ["ИНН", data.inn],
                ["Город", data.city],
                [
                  "Сайт",
                  data.website ? (
                    <a href={data.website} target="_blank" rel="noreferrer" className="row" style={{ gap: 4 }}>
                      {data.website.replace(/^https?:\/\//, "")} <ExternalLink size={12} />
                    </a>
                  ) : null,
                ],
                ["Описание", data.description],
                ["Источник записи", ORIGIN[data.origin || "manual"] || data.origin],
                ["В системе с", formatDateTime(data.created_at)],
                ["Подтверждён", data.confirmed_at ? formatDateTime(data.confirmed_at) : null],
              ]}
            />
          </Card>
          <Card title="Менеджер по умолчанию">
            {data.manager ? (
              <div className="stack-s">
                <strong>{data.manager.full_name}</strong>
                <small className="muted">Становится ответственным за новые взаимодействия вуза.</small>
              </div>
            ) : (
              <Tag tone="warn">Не назначен</Tag>
            )}
          </Card>
          {can("view_audit") && (
            <Card title="Журнал изменений" flush>
              {audit.data ? <AuditEntries entries={audit.data.items} compact /> : <Loading />}
            </Card>
          )}
        </div>
      </div>

      <UniversityFormModal open={editing} onClose={() => setEditing(false)} university={data} />
      <ContactModal
        open={contact !== undefined}
        onClose={() => setContact(undefined)}
        universityId={universityId}
        contact={contact || null}
      />
      {canCreate && (
        <InteractionFormModal
          open={creatingInteraction}
          onClose={() => setCreatingInteraction(false)}
          universityId={universityId}
        />
      )}
      {manages && (
        <MergeDialog
          open={merging}
          onClose={() => setMerging(false)}
          sourceId={universityId}
          sourceName={data.short_name || data.name}
        />
      )}
    </div>
  );
}
