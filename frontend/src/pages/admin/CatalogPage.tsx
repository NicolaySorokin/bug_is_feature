/**
 * Справочники: направления, программы, вендоры, продукты. Записи ведёт администратор, продукты
 * программ и шаблоны договоров руководитель. Запись не удаляется, а выключается.
 */
import { useQuery } from "@tanstack/react-query";
import {
  Boxes,
  Compass,
  Factory,
  FileSignature,
  FileSpreadsheet,
  GraduationCap,
  Mail,
  Pencil,
  Phone,
  Plus,
  Trash2,
  UserPlus,
  type LucideIcon,
} from "lucide-react";
import { useEffect, useMemo, useState } from "react";
import { useNavigate, useSearchParams } from "react-router-dom";
import {
  createCatalogItem,
  createVendorContact,
  deleteVendorContact,
  listProgramProducts,
  setProgramProducts,
  updateCatalogItem,
  updateVendorContact,
} from "../../api/endpoints";
import { useApiMutation } from "../../api/mutations";
import { keys, queryClient, useDirections, usePrograms, useProducts, useVendors } from "../../api/queries";
import type { Vendor, VendorContact } from "../../api/types";
import { useSession } from "../../auth/session";
import { useConfirm } from "../../components/Confirm";
import { Modal } from "../../components/Modal";
import { MultiSelect } from "../../components/MultiSelect";
import {
  Button,
  Card,
  EmptyState,
  ErrorState,
  Field,
  Loading,
  PageHeader,
  SearchInput,
  SelectField,
  StatusBadge,
  Switch,
  Tabs,
  TextAreaField,
  TextField,
} from "../../components/ui";
import { usePageTitle } from "../../lib/usePageTitle";
import { ContractTemplates } from "./ContractTemplates";

type Kind = "directions" | "programs" | "vendors" | "products";

interface Item {
  id: string;
  name: string;
  description: string | null;
  is_active: boolean;
  direction_id?: string | null;
  vendor_id?: string | null;
  contact_id?: string | null;
}

interface EditState {
  kind: Kind;
  item: Item | null;
}

const TAB_ICONS: Record<Kind, LucideIcon> = {
  programs: GraduationCap,
  directions: Compass,
  products: Boxes,
  vendors: Factory,
};

const TITLES: Record<Kind, [string, string]> = {
  directions: ["ИТ-направления", "направление"],
  programs: ["ИТ-программы", "программу"],
  vendors: ["Вендоры", "вендора"],
  products: ["ИТ-продукты", "продукт"],
};

function refreshCatalog() {
  void queryClient.invalidateQueries({ queryKey: ["catalog"] });
  void queryClient.invalidateQueries({ queryKey: ["report"] });
  void queryClient.invalidateQueries({ queryKey: ["statistics"] });
}

function ItemModal({ edit, onClose, canLink }: { edit: EditState | null; onClose: () => void; canLink: boolean }) {
  const directions = useDirections();
  const vendors = useVendors();
  const products = useProducts();
  const links = useQuery({ queryKey: keys.programProducts, queryFn: listProgramProducts, enabled: edit?.kind === "programs" });
  const [name, setName] = useState("");
  const [description, setDescription] = useState("");
  const [active, setActive] = useState(true);
  const [directionId, setDirectionId] = useState("");
  const [vendorId, setVendorId] = useState("");
  const [contactId, setContactId] = useState("");
  const [productIds, setProductIds] = useState<string[]>([]);

  useEffect(() => {
    if (!edit) return;
    setName(edit.item?.name || "");
    setDescription(edit.item?.description || "");
    setActive(edit.item?.is_active ?? true);
    setDirectionId(edit.item?.direction_id || "");
    setVendorId(edit.item?.vendor_id || "");
    setContactId(edit.item?.contact_id || "");
  }, [edit]);

  useEffect(() => {
    if (edit?.kind === "programs" && edit.item && links.data) {
      setProductIds(links.data.filter((link) => link.program_id === edit.item!.id).map((link) => link.product_id));
    } else {
      setProductIds([]);
    }
  }, [edit, links.data]);

  // Новые связи только с действующими записями, уже выбранная остаётся в списке.
  const vendorContacts = ((vendors.data || []).find((vendor) => vendor.id === vendorId)?.contacts || []).filter(
    (item) => item.is_active !== false || item.id === contactId,
  );

  const save = useApiMutation(
    async () => {
      if (!edit) return;
      const body: Record<string, unknown> = { name: name.trim(), description: description.trim() || null };
      if (edit.kind === "programs") body.direction_id = directionId || null;
      if (edit.kind === "products") {
        body.vendor_id = vendorId || null;
        body.contact_id = contactId || null;
      }
      if (edit.item) body.is_active = active;
      const saved = edit.item
        ? await updateCatalogItem<Item>(edit.kind, edit.item.id, body)
        : await createCatalogItem<Item>(edit.kind, body);
      if (edit.kind === "programs" && canLink) await setProgramProducts(saved.id, productIds);
      return saved;
    },
    {
      success: "Справочник обновлён",
      onSuccess: () => {
        refreshCatalog();
        onClose();
      },
    },
  );

  if (!edit) return null;
  const [, accusative] = TITLES[edit.kind];
  return (
    <Modal
      open
      onClose={onClose}
      title={edit.item ? edit.item.name : `Добавить ${accusative}`}
      footer={
        <>
          <Button variant="outline" onClick={onClose}>
            Отмена
          </Button>
          <Button loading={save.isPending} disabled={!name.trim()} onClick={() => save.mutate(undefined)}>
            Сохранить
          </Button>
        </>
      }
    >
      <div className="stack">
        <TextField label="Название" required value={name} onChange={setName} maxLength={255} />
        {edit.kind === "programs" && (
          <>
            <SelectField
              label="ИТ-направление"
              value={directionId}
              onChange={setDirectionId}
              placeholder="Не указано"
              options={(directions.data || [])
                .filter((item) => item.is_active || item.id === directionId)
                .map((item) => ({ value: item.id, label: item.name }))}
            />
            {canLink ? (
              <MultiSelect
                label="ИТ-продукты программы"
                placeholder="Не выбраны"
                value={productIds}
                onChange={setProductIds}
                options={(products.data || [])
                  .filter((item) => item.is_active || productIds.includes(item.id))
                  .map((item) => ({ value: item.id, label: item.name }))}
                hint="Продукты, на которых ведётся обучение по программе"
              />
            ) : (
              <Field label="ИТ-продукты программы" hint="Соответствие программ и продуктов задаёт руководитель">
                <span className={productIds.length ? undefined : "muted"}>
                  {productIds.length
                    ? (products.data || [])
                        .filter((item) => productIds.includes(item.id))
                        .map((item) => item.name)
                        .join(", ")
                    : "Не выбраны"}
                </span>
              </Field>
            )}
          </>
        )}
        {edit.kind === "products" && (
          <>
            <SelectField
              label="Вендор"
              value={vendorId}
              onChange={(value) => {
                setVendorId(value);
                setContactId("");
              }}
              placeholder="Не указан"
              options={(vendors.data || [])
                .filter((item) => item.is_active || item.id === vendorId)
                .map((item) => ({ value: item.id, label: item.name }))}
            />
            <SelectField
              label="Контакт вендора по продукту"
              value={contactId}
              onChange={setContactId}
              placeholder="Не указан"
              disabled={!vendorId}
              options={vendorContacts.map((item) => ({ value: item.id, label: item.full_name }))}
            />
          </>
        )}
        <TextAreaField label="Описание" value={description} onChange={setDescription} rows={3} maxLength={4000} />
        {edit.item && <Switch label="Используется" checked={active} onChange={setActive} />}
      </div>
    </Modal>
  );
}

/** Продукты программы задаёт руководитель. */
function ProgramProductsModal({ program, onClose }: { program: Item | null; onClose: () => void }) {
  const products = useProducts();
  const links = useQuery({ queryKey: keys.programProducts, queryFn: listProgramProducts, enabled: program !== null });
  const [productIds, setProductIds] = useState<string[]>([]);

  useEffect(() => {
    if (program && links.data) {
      setProductIds(links.data.filter((link) => link.program_id === program.id).map((link) => link.product_id));
    }
  }, [program, links.data]);

  const save = useApiMutation(() => setProgramProducts(program!.id, productIds), {
    success: "Продукты программы сохранены",
    onSuccess: () => {
      refreshCatalog();
      onClose();
    },
  });

  if (!program) return null;
  return (
    <Modal
      open
      onClose={onClose}
      title={program.name}
      description="Какие ИТ-продукты используются в программе. Во взаимодействии продукт добавляется к программе, с которой он связан; иной продукт - только как исключение с обоснованием."
      footer={
        <>
          <Button variant="outline" onClick={onClose}>
            Отмена
          </Button>
          <Button loading={save.isPending} disabled={links.isPending} onClick={() => save.mutate(undefined)}>
            Сохранить
          </Button>
        </>
      }
    >
      <MultiSelect
        label="ИТ-продукты программы"
        placeholder="Не выбраны"
        value={productIds}
        onChange={setProductIds}
        options={(products.data || [])
          .filter((item) => item.is_active || productIds.includes(item.id))
          .map((item) => ({ value: item.id, label: item.is_active ? item.name : `${item.name} (выключен)` }))}
      />
    </Modal>
  );
}

function VendorContacts({ vendor, onClose, readOnly }: { vendor: Vendor | null; onClose: () => void; readOnly: boolean }) {
  const confirm = useConfirm();
  const [editing, setEditing] = useState<VendorContact | null | undefined>(undefined);
  const [form, setForm] = useState({ full_name: "", phone: "", email: "", contact_channel: "" });
  useEffect(() => {
    if (editing !== undefined) {
      setForm({
        full_name: editing?.full_name || "",
        phone: editing?.phone || "",
        email: editing?.email || "",
        contact_channel: editing?.contact_channel || "",
      });
    }
  }, [editing]);
  const save = useApiMutation(
    () => {
      const body = {
        full_name: form.full_name.trim(),
        phone: form.phone.trim() || null,
        email: form.email.trim() || null,
        contact_channel: form.contact_channel.trim() || null,
      };
      return editing ? updateVendorContact(editing.id, body) : createVendorContact(vendor!.id, body);
    },
    {
      success: "Контакт сохранён",
      onSuccess: () => {
        refreshCatalog();
        setEditing(undefined);
      },
    },
  );
  const remove = useApiMutation((id: string) => deleteVendorContact(id), {
    success: "Контакт удалён",
    onSuccess: refreshCatalog,
  });
  const vendors = useVendors();
  const current = (vendors.data || []).find((item) => item.id === vendor?.id) || vendor;

  return (
    <Modal
      open={vendor !== null}
      onClose={onClose}
      size="wide"
      title={`Контакты: ${vendor?.name || ""}`}
      description="Кому писать по продуктам вендора."
    >
      <div className="stack">
        {(current?.contacts || []).length === 0 && <p className="muted">Контактов нет.</p>}
        <div className="list" style={{ border: "1px solid var(--line)", borderRadius: 10 }}>
          {(current?.contacts || []).map((item) => (
            <div key={item.id} className="list-item">
              <div className="list-item__main">
                <strong>{item.full_name}</strong>
                <small className="row" style={{ gap: 10 }}>
                  {item.phone && (
                    <span className="row" style={{ gap: 4 }}>
                      <Phone size={12} /> {item.phone}
                    </span>
                  )}
                  {item.email && (
                    <span className="row" style={{ gap: 4 }}>
                      <Mail size={12} /> {item.email}
                    </span>
                  )}
                  {item.contact_channel && <span>Связь: {item.contact_channel}</span>}
                </small>
              </div>
              {!readOnly && (
                <>
                  <button type="button" className="icon-btn" aria-label="Изменить" onClick={() => setEditing(item)}>
                    <Pencil size={16} />
                  </button>
                  <button
                    type="button"
                    className="icon-btn"
                    aria-label="Удалить"
                    onClick={async () => {
                      const ok = await confirm({
                        title: `Удалить контакт ${item.full_name}?`,
                        confirmLabel: "Удалить",
                        danger: true,
                      });
                      if (ok !== null) remove.mutate(item.id);
                    }}
                  >
                    <Trash2 size={16} />
                  </button>
                </>
              )}
            </div>
          ))}
        </div>
        {readOnly ? null : editing === undefined ? (
          <div>
            <Button variant="secondary" icon={UserPlus} onClick={() => setEditing(null)}>
              Добавить контакт
            </Button>
          </div>
        ) : (
          <Card title={editing ? "Изменить контакт" : "Новый контакт"}>
            <div className="form-grid">
              <TextField
                className="span-2"
                label="ФИО"
                required
                value={form.full_name}
                onChange={(value) => setForm({ ...form, full_name: value })}
              />
              <TextField label="Телефон" type="tel" value={form.phone} onChange={(value) => setForm({ ...form, phone: value })} />
              <TextField label="Почта" type="email" value={form.email} onChange={(value) => setForm({ ...form, email: value })} />
              <TextField
                className="span-2"
                label="Способ связи"
                value={form.contact_channel}
                onChange={(value) => setForm({ ...form, contact_channel: value })}
                placeholder="Почта, телефон, мессенджер"
              />
            </div>
            <div className="row" style={{ marginTop: 12 }}>
              <Button variant="outline" onClick={() => setEditing(undefined)}>
                Отмена
              </Button>
              <Button loading={save.isPending} disabled={!form.full_name.trim()} onClick={() => save.mutate(undefined)}>
                Сохранить
              </Button>
            </div>
          </Card>
        )}
      </div>
    </Modal>
  );
}

export default function CatalogPage() {
  const [params, setParams] = useSearchParams();
  const navigate = useNavigate();
  const { can } = useSession();
  const canEdit = can("edit_catalog");
  const canLink = can("edit_program_products");
  const canTemplates = can("edit_contract_templates");
  const kind = (
    ["directions", "programs", "vendors", "products"].includes(params.get("tab") || "") ? params.get("tab") : "programs"
  ) as Kind;
  const showTemplates = canTemplates && params.get("tab") === "templates";
  const [search, setSearch] = useState("");
  const [edit, setEdit] = useState<EditState | null>(null);
  const [contactsOf, setContactsOf] = useState<Vendor | null>(null);
  const [linksOf, setLinksOf] = useState<Item | null>(null);
  const directions = useDirections();
  const programs = usePrograms();
  const vendors = useVendors();
  const products = useProducts();
  const links = useQuery({ queryKey: keys.programProducts, queryFn: listProgramProducts });
  usePageTitle("Справочники");

  const sources = { directions, programs, vendors, products };
  const source = sources[kind];
  const directionName = useMemo(
    () => Object.fromEntries((directions.data || []).map((item) => [item.id, item.name])),
    [directions.data],
  );
  const vendorName = useMemo(() => Object.fromEntries((vendors.data || []).map((item) => [item.id, item.name])), [vendors.data]);
  const programsCount = useMemo(() => {
    const counts: Record<string, number> = {};
    (programs.data || []).forEach((item) => {
      if (item.direction_id) counts[item.direction_id] = (counts[item.direction_id] || 0) + 1;
    });
    return counts;
  }, [programs.data]);
  const productsOfProgram = useMemo(() => {
    const counts: Record<string, number> = {};
    (links.data || []).forEach((link) => (counts[link.program_id] = (counts[link.program_id] || 0) + 1));
    return counts;
  }, [links.data]);

  const items = ((source.data || []) as Item[]).filter(
    (item) => !search.trim() || item.name.toLowerCase().includes(search.trim().toLowerCase()),
  );
  const [title, accusative] = TITLES[kind];

  const extra = (item: Item) => {
    if (kind === "directions") return `${programsCount[item.id] || 0} программ`;
    if (kind === "programs")
      return `${directionName[item.direction_id || ""] || "Без направления"} · продуктов: ${productsOfProgram[item.id] || 0}`;
    if (kind === "products") return `Вендор: ${vendorName[item.vendor_id || ""] || "не указан"}`;
    const vendor = item as unknown as Vendor;
    return `Контактов: ${(vendor.contacts || []).length}`;
  };

  return (
    <div className="page">
      <PageHeader
        title="Справочники"
        description={
          canEdit
            ? canLink
              ? undefined
              : "Записи справочников ведёт администратор; какие продукты используются в программе, задаёт руководитель."
            : canTemplates
              ? "Справочники ведёт администратор. Вы задаёте, какие ИТ-продукты используются в каждой ИТ-программе, и типовые шаблоны договоров."
              : "Справочники ведёт администратор. Вы задаёте, какие ИТ-продукты используются в каждой ИТ-программе."
        }
        actions={
          can("import") && (
            <Button variant="outline" icon={FileSpreadsheet} onClick={() => navigate("/admin/imports")}>
              Загрузить из Excel
            </Button>
          )
        }
      />
      <Tabs
        value={showTemplates ? "templates" : kind}
        onChange={(key) => setParams({ tab: key }, { replace: true })}
        label="Справочники"
        items={[
          ...(["programs", "directions", "products", "vendors"] as Kind[]).map((key) => ({
            key,
            label: TITLES[key][0],
            icon: TAB_ICONS[key],
            count: sources[key].data?.length,
          })),
          { key: "templates", label: "Шаблоны договоров", icon: FileSignature, hidden: !canTemplates },
        ]}
      />
      {showTemplates ? (
        <ContractTemplates />
      ) : (
        <>
          <div className="toolbar">
            <Field label="Поиск" className="field--grow">
              <SearchInput value={search} onChange={setSearch} placeholder="Название" />
            </Field>
            {canEdit && (
              <div className="toolbar__actions">
                <Button icon={Plus} onClick={() => setEdit({ kind, item: null })}>
                  Добавить {accusative}
                </Button>
              </div>
            )}
          </div>
          <Card flush title={`${title}: ${items.length}`}>
            {source.isPending ? (
              <Loading />
            ) : source.isError ? (
              <ErrorState error={source.error} onRetry={() => void source.refetch()} />
            ) : items.length === 0 ? (
              <EmptyState title="Записей нет" />
            ) : (
              <div className="table-wrap">
                <table className="data-table data-table--cards">
                  <thead>
                    <tr>
                      <th scope="col">Название</th>
                      <th scope="col">Сведения</th>
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
                            {canEdit || (canLink && kind === "programs") ? (
                              <button
                                type="button"
                                className="link-btn"
                                onClick={() => (canEdit ? setEdit({ kind, item }) : setLinksOf(item))}
                              >
                                {item.name}
                              </button>
                            ) : (
                              <strong>{item.name}</strong>
                            )}
                            {item.description && <small>{item.description}</small>}
                          </div>
                        </td>
                        <td data-label="Сведения">{extra(item)}</td>
                        <td data-label="Состояние">
                          {item.is_active ? (
                            <StatusBadge tone="success">Используется</StatusBadge>
                          ) : (
                            <StatusBadge>Выключен</StatusBadge>
                          )}
                        </td>
                        <td className="col-actions" data-label="">
                          {kind === "vendors" && (
                            <Button
                              variant="ghost"
                              size="s"
                              icon={UserPlus}
                              onClick={() => setContactsOf(item as unknown as Vendor)}
                            >
                              Контакты
                            </Button>
                          )}
                          {kind === "programs" && canLink && (
                            <Button variant="ghost" size="s" icon={Boxes} onClick={() => setLinksOf(item)}>
                              Продукты
                            </Button>
                          )}
                          {canEdit && (
                            <button
                              type="button"
                              className="icon-btn"
                              aria-label={`Изменить ${item.name}`}
                              onClick={() => setEdit({ kind, item })}
                            >
                              <Pencil size={16} />
                            </button>
                          )}
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}
          </Card>
        </>
      )}
      {canEdit && <ItemModal edit={edit} onClose={() => setEdit(null)} canLink={canLink} />}
      {canLink && <ProgramProductsModal program={linksOf} onClose={() => setLinksOf(null)} />}
      <VendorContacts vendor={contactsOf} onClose={() => setContactsOf(null)} readOnly={!canEdit} />
    </div>
  );
}
