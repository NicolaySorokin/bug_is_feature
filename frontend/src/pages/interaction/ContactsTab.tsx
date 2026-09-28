/**
 * Ответственные от вуза по взаимодействию. Контакты хранятся у вуза, основной контакт один.
 */
import { useQuery } from "@tanstack/react-query";
import { Mail, Phone, Plus, Star, Trash2 } from "lucide-react";
import { useState } from "react";
import { Link } from "react-router-dom";
import { getUniversity, putInteractionContact, removeInteractionContact } from "../../api/endpoints";
import { useApiMutation } from "../../api/mutations";
import { invalidateInteractionData, keys } from "../../api/queries";
import type { InteractionDetail } from "../../api/types";
import { useSession } from "../../auth/session";
import { useConfirm } from "../../components/Confirm";
import { Button, Card, Checkbox, EmptyState, SelectField, Tag, TextField } from "../../components/ui";

export function ContactsTab({ interaction }: { interaction: InteractionDetail }) {
  const confirm = useConfirm();
  const { can } = useSession();
  const canWork = can("work_interaction");
  const universityId = interaction.university.id;
  const university = useQuery({
    queryKey: keys.university(universityId),
    queryFn: () => getUniversity(universityId),
  });
  const [contactId, setContactId] = useState("");
  const [role, setRole] = useState("");
  const [primary, setPrimary] = useState(false);
  const linked = new Set((interaction.contacts || []).map((item) => item.contact_id));
  const refresh = () => invalidateInteractionData(interaction.id);

  const assign = useApiMutation(
    (body: { contact_id: string; role?: string | null; is_primary?: boolean }) => putInteractionContact(interaction.id, body),
    {
      success: "Контакт назначен по взаимодействию",
      onSuccess: () => {
        setContactId("");
        setRole("");
        setPrimary(false);
        refresh();
      },
    },
  );
  const remove = useApiMutation((id: string) => removeInteractionContact(interaction.id, id), {
    success: "Контакт откреплён",
    onSuccess: refresh,
  });

  const available = (university.data?.contacts || []).filter((item) => item.is_active && !linked.has(item.id));

  return (
    <div className="stack">
      <Card
        title="Ответственные от вуза"
        description="С кем согласовывать программы, документы и занятия в этом взаимодействии."
        flush
        actions={<Link to={`/universities/${universityId}`}>Все контакты вуза</Link>}
      >
        {(interaction.contacts || []).length === 0 ? (
          <EmptyState title="Контакты не назначены">Выберите сотрудника вуза ниже или добавьте его в карточке вуза.</EmptyState>
        ) : (
          <div className="list">
            {(interaction.contacts || []).map((item) => (
              <div key={item.contact_id} className="list-item" style={{ alignItems: "flex-start" }}>
                <div className="list-item__main">
                  <strong className="row" style={{ gap: 6 }}>
                    {item.contact.full_name}
                    {item.is_primary && <Tag tone="accent">основной</Tag>}
                    {!item.contact.is_active && <Tag>в архиве</Tag>}
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
                {canWork && (
                  <div className="row">
                    {/* Архивный контакт остаётся в истории, но заново не назначается. */}
                    {!item.is_primary && item.contact.is_active && (
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
                )}
              </div>
            ))}
          </div>
        )}
      </Card>

      {canWork && (
        <Card title="Назначить контакт">
          {available.length === 0 ? (
            <p className="muted">
              Свободных контактов у вуза нет. Добавьте сотрудника вуза в{" "}
              <Link to={`/universities/${universityId}`}>карточке вуза</Link>.
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
              <TextField
                label="Роль во взаимодействии"
                value={role}
                onChange={setRole}
                placeholder="Например: юрист"
                maxLength={100}
              />
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
                  Назначить
                </Button>
              </div>
            </div>
          )}
        </Card>
      )}
    </div>
  );
}
