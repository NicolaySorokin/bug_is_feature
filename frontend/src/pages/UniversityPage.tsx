/**
 * Карточка вуза: ответственный от ИТ Школы, контакты вуза, договоры
 * и (для администратора) журнал изменений.
 */
import { useQuery } from "@tanstack/react-query";
import { ArrowLeft, ExternalLink, Mail, Pencil, Phone, Plus, Trash2, UserPlus } from "lucide-react";
import { useEffect, useState } from "react";
import { Link, useNavigate, useParams } from "react-router-dom";
import { ApiError } from "../api/client";
import {
  createContact,
  deleteContact,
  deleteUniversity,
  getUniversity,
  listAudit,
  listContracts,
  updateContact,
} from "../api/endpoints";
import { useApiMutation } from "../api/mutations";
import { invalidateContractData, keys, useLabel } from "../api/queries";
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
  StatusBadge,
  Tag,
  TextField,
} from "../components/ui";
import { formatDateTime } from "../lib/format";
import { CONTRACT_STATUS_TONE } from "../lib/labels";
import { usePageTitle } from "../lib/usePageTitle";
import { ContractFormModal } from "./contract/ContractForm";
import { StageCell, ValidTo } from "./ContractsPage";
import { UniversityFormModal } from "./UniversityForm";
import { AuditEntries } from "./admin/AuditPage";

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
        invalidateContractData();
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
      description="Сотрудник вуза, с которым ведётся работа. Персональные данные видят только сотрудники с доступом к вузу."
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

export default function UniversityPage() {
  const { universityId = "" } = useParams();
  const navigate = useNavigate();
  const label = useLabel();
  const confirm = useConfirm();
  const { can, me } = useSession();
  const [editing, setEditing] = useState(false);
  const [contact, setContact] = useState<UniversityContact | null | undefined>(undefined);
  const [creatingContract, setCreatingContract] = useState(false);

  const university = useQuery({ queryKey: keys.university(universityId), queryFn: () => getUniversity(universityId) });
  const contracts = useQuery({
    queryKey: [...keys.contracts, { university_id: universityId, limit: 100 }],
    queryFn: () => listContracts({ university_id: universityId, limit: 100 }),
  });
  const audit = useQuery({
    queryKey: ["audit", "university", universityId],
    queryFn: () => listAudit({ entity_type: "universities", entity_id: universityId, limit: 20 }),
    enabled: can("view_audit"),
  });
  usePageTitle(university.data?.short_name || university.data?.name || "Вуз");

  const removeContact = useApiMutation((id: string) => deleteContact(universityId, id), {
    success: "Контакт удалён",
    onSuccess: () => invalidateContractData(),
  });
  const remove = useApiMutation(() => deleteUniversity(universityId), {
    success: "Вуз удалён",
    onSuccess: () => {
      invalidateContractData();
      navigate("/universities");
    },
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
  const manageContacts = can("edit_university") || data.manager_id === me.id;

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
            {!data.is_active && <StatusBadge>Не активен</StatusBadge>}
          </span>
        }
        actions={
          <>
            <Button variant="outline" icon={Plus} onClick={() => setCreatingContract(true)}>
              Новый договор
            </Button>
            {can("edit_university") && (
              <Button variant="outline" icon={Pencil} onClick={() => setEditing(true)}>
                Изменить
              </Button>
            )}
            {can("delete_contract") && (
              <Button
                variant="danger"
                icon={Trash2}
                disabled={(data.contracts_count || 0) > 0}
                title={(data.contracts_count || 0) > 0 ? "У вуза есть договоры - удалить нельзя" : undefined}
                onClick={async () => {
                  const ok = await confirm({ title: `Удалить вуз «${data.name}»?`, confirmLabel: "Удалить", danger: true });
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
          <Card
            title="Договоры"
            description={`Всего ${data.contracts_count || 0}, действует ${data.active_contracts_count || 0}`}
            flush
          >
            {contracts.isPending ? (
              <Loading />
            ) : contracts.isError ? (
              <ErrorState error={contracts.error} onRetry={() => void contracts.refetch()} />
            ) : contracts.data.items.length === 0 ? (
              <EmptyState
                title="Договоров нет"
                action={
                  <Button icon={Plus} onClick={() => setCreatingContract(true)}>
                    Новый договор
                  </Button>
                }
              />
            ) : (
              <div className="table-wrap">
                <table className="data-table data-table--cards">
                  <thead>
                    <tr>
                      <th scope="col">Договор</th>
                      <th scope="col">Статус</th>
                      <th scope="col">Этап</th>
                      <th scope="col">Ответственный</th>
                      <th scope="col">Действует по</th>
                    </tr>
                  </thead>
                  <tbody>
                    {contracts.data.items.map((row) => (
                      <tr key={row.id} className="clickable" onClick={() => navigate(`/contracts/${row.id}`)}>
                        <td className="cell-primary">
                          <div className="cell-title">
                            <Link to={`/contracts/${row.id}`}>
                              <strong>{row.number}</strong>
                            </Link>
                            <small>{row.title || "Без предмета"}</small>
                          </div>
                        </td>
                        <td data-label="Статус">
                          <StatusBadge tone={CONTRACT_STATUS_TONE[row.status]}>
                            {label("contract_status", row.status)}
                          </StatusBadge>
                        </td>
                        <td data-label="Этап">
                          <StageCell row={row} />
                        </td>
                        <td data-label="Ответственный">{row.manager?.full_name || "—"}</td>
                        <td data-label="Действует по">
                          <ValidTo value={row.valid_to} status={row.status} />
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}
          </Card>

          <Card
            title="Контакты вуза"
            description="Сотрудники вуза, с которыми ведётся работа по договорам."
            flush
            actions={
              manageContacts && (
                <Button variant="secondary" size="s" icon={UserPlus} onClick={() => setContact(null)}>
                  Добавить
                </Button>
              )
            }
          >
            {(data.contacts || []).length === 0 ? (
              <EmptyState title="Контактов нет">
                Добавьте ответственных от вуза - их можно будет закрепить за договорами.
              </EmptyState>
            ) : (
              <div className="list">
                {(data.contacts || []).map((item) => (
                  <div key={item.id} className="list-item" style={{ alignItems: "flex-start" }}>
                    <div className="list-item__main">
                      <strong>{item.full_name}</strong>
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
                        <button
                          type="button"
                          className="icon-btn"
                          aria-label={`Удалить ${item.full_name}`}
                          onClick={async () => {
                            const ok = await confirm({
                              title: `Удалить контакт ${item.full_name}?`,
                              message: "Контакт открепится от всех договоров вуза.",
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
                ["В системе с", formatDateTime(data.created_at)],
              ]}
            />
          </Card>
          <Card title="Ответственный от ИТ Школы">
            {data.manager ? (
              <div className="stack-s">
                <strong>{data.manager.full_name}</strong>
                {data.manager.email && <a href={`mailto:${data.manager.email}`}>{data.manager.email}</a>}
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
      <ContractFormModal open={creatingContract} onClose={() => setCreatingContract(false)} universityId={universityId} />
    </div>
  );
}
