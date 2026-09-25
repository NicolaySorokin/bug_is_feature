/**
 * Ответственные от вуза по договору.
 *
 * Контакты берутся из карточки вуза: один человек может отвечать за
 * несколько договоров в разных ролях. Основной контакт - один.
 */
import { useQuery } from "@tanstack/react-query";
import { Mail, Phone, Plus, Star, Trash2 } from "lucide-react";
import { useState } from "react";
import { Link } from "react-router-dom";
import { getUniversity, putContractContact, removeContractContact } from "../../api/endpoints";
import { useApiMutation } from "../../api/mutations";
import { invalidateContractData, keys } from "../../api/queries";
import type { ContractDetail } from "../../api/types";
import { useConfirm } from "../../components/Confirm";
import { Button, Card, Checkbox, EmptyState, SelectField, Tag, TextField } from "../../components/ui";

export function ContactsTab({ contract }: { contract: ContractDetail }) {
  const confirm = useConfirm();
  const university = useQuery({
    queryKey: keys.university(contract.university_id),
    queryFn: () => getUniversity(contract.university_id),
  });
  const [contactId, setContactId] = useState("");
  const [role, setRole] = useState("");
  const [primary, setPrimary] = useState(false);
  const linked = new Set((contract.contacts || []).map((item) => item.contact_id));
  const refresh = () => invalidateContractData(contract.id);

  const assign = useApiMutation(
    (body: { contact_id: string; role?: string | null; is_primary?: boolean }) => putContractContact(contract.id, body),
    {
      success: "Контакт закреплён за договором",
      onSuccess: () => {
        setContactId("");
        setRole("");
        setPrimary(false);
        refresh();
      },
    },
  );
  const remove = useApiMutation((id: string) => removeContractContact(contract.id, id), {
    success: "Контакт откреплён",
    onSuccess: refresh,
  });

  const available = (university.data?.contacts || []).filter((item) => item.is_active && !linked.has(item.id));

  return (
    <div className="stack">
      <Card
        title="Ответственные от вуза"
        description="С кем согласовывать документы и занятия по этому договору."
        flush
        actions={<Link to={`/universities/${contract.university_id}`}>Все контакты вуза</Link>}
      >
        {(contract.contacts || []).length === 0 ? (
          <EmptyState title="Контакты не закреплены">Выберите сотрудника вуза ниже или добавьте его в карточке вуза.</EmptyState>
        ) : (
          <div className="list">
            {(contract.contacts || []).map((item) => (
              <div key={item.contact_id} className="list-item" style={{ alignItems: "flex-start" }}>
                <div className="list-item__main">
                  <strong className="row" style={{ gap: 6 }}>
                    {item.contact.full_name}
                    {item.is_primary && <Tag tone="accent">основной</Tag>}
                  </strong>
                  <small>{[item.role, item.contact.position].filter(Boolean).join(" · ") || "Роль не указана"}</small>
                  <div className="row" style={{ gap: 12, marginTop: 4 }}>
                    {item.contact.phone && (
                      <a href={`tel:${item.contact.phone}`} className="row" style={{ gap: 4 }}>
                        <Phone size={13} /> {item.contact.phone}
                      </a>
                    )}
                    {item.contact.email && (
                      <a href={`mailto:${item.contact.email}`} className="row" style={{ gap: 4 }}>
                        <Mail size={13} /> {item.contact.email}
                      </a>
                    )}
                  </div>
                </div>
                <div className="row">
                  {!item.is_primary && (
                    <Button
                      variant="ghost"
                      size="s"
                      icon={Star}
                      onClick={() => assign.mutate({ contact_id: item.contact_id, role: item.role, is_primary: true })}
                    >
                      Сделать основным
                    </Button>
                  )}
                  <button
                    type="button"
                    className="icon-btn"
                    aria-label={`Открепить ${item.contact.full_name}`}
                    onClick={async () => {
                      const ok = await confirm({
                        title: `Открепить ${item.contact.full_name}?`,
                        message: "Контакт останется в карточке вуза.",
                        confirmLabel: "Открепить",
                      });
                      if (ok !== null) remove.mutate(item.contact_id);
                    }}
                  >
                    <Trash2 size={16} />
                  </button>
                </div>
              </div>
            ))}
          </div>
        )}
      </Card>

      <Card title="Закрепить контакт">
        {available.length === 0 ? (
          <p className="muted">
            Свободных контактов у вуза нет. Добавьте сотрудника вуза в{" "}
            <Link to={`/universities/${contract.university_id}`}>карточке вуза</Link>.
          </p>
        ) : (
          <div className="toolbar" style={{ marginBottom: 0 }}>
            <SelectField
              label="Сотрудник вуза"
              value={contactId}
              onChange={setContactId}
              placeholder="Выберите"
              options={available.map((item) => ({
                value: item.id,
                label: item.position ? `${item.full_name} — ${item.position}` : item.full_name,
              }))}
            />
            <TextField label="Роль по договору" value={role} onChange={setRole} placeholder="Например: юрист" maxLength={100} />
            <div style={{ alignSelf: "center", paddingTop: 22 }}>
              <Checkbox label="Основной" checked={primary} onChange={setPrimary} />
            </div>
            <div style={{ alignSelf: "flex-end" }}>
              <Button
                icon={Plus}
                disabled={!contactId}
                loading={assign.isPending}
                onClick={() => assign.mutate({ contact_id: contactId, role: role.trim() || null, is_primary: primary })}
              >
                Закрепить
              </Button>
            </div>
          </div>
        )}
      </Card>
    </div>
  );
}
