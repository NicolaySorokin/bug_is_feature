/**
 * Вкладка «Программы и продукты». Продукт добавляется сразу с программами и без связи с программой
 * не существует. Связь вне справочника и ручное изменение статуса требуют комментария.
 */
import { useQuery } from "@tanstack/react-query";
import { KeyRound, Link2, Plus, Trash2, X } from "lucide-react";
import { useEffect, useMemo, useState } from "react";
import {
  addProduct,
  addProgram,
  createLicense,
  deleteLicense,
  linkProduct,
  listProgramProducts,
  removeProduct,
  removeProgram,
  unlinkProduct,
  updateLicense,
  updateProduct,
  updateProgram,
} from "../../api/endpoints";
import { useApiMutation } from "../../api/mutations";
import {
  invalidateInteractionData,
  keys,
  useDirections,
  useLabel,
  usePrograms,
  useProducts,
  useVendors,
} from "../../api/queries";
import type {
  InteractionDetail,
  InteractionProduct,
  License,
  LicenseStatus,
  ProductStatus,
  ProgramStatus,
} from "../../api/types";
import { useSession } from "../../auth/session";
import { useConfirm } from "../../components/Confirm";
import { Modal } from "../../components/Modal";
import {
  Button,
  Card,
  Checkbox,
  EmptyState,
  Hint,
  SelectField,
  StatusBadge,
  Tag,
  TextAreaField,
  TextField,
} from "../../components/ui";
import { countLabel, DAYS, daysUntil, formatDate } from "../../lib/format";
import { LICENSE_TONE, PRODUCT_STATUSES, PRODUCT_TONE, PROGRAM_STATUSES, PROGRAM_TONE } from "../../lib/labels";

interface LicenseForm {
  number: string;
  seats: string;
  signed_at: string;
  valid_from: string;
  valid_to: string;
  status: LicenseStatus;
}

function LicenseModal({
  open,
  onClose,
  interactionId,
  productLinkId,
  license,
  productName,
}: {
  open: boolean;
  onClose: () => void;
  interactionId: string;
  productLinkId: string | null;
  license: License | null;
  productName: string;
}) {
  const label = useLabel();
  const [form, setForm] = useState<LicenseForm>({
    number: "",
    seats: "",
    signed_at: "",
    valid_from: "",
    valid_to: "",
    status: "active",
  });
  useEffect(() => {
    if (open) {
      setForm({
        number: license?.number || "",
        seats: license?.seats ? String(license.seats) : "",
        signed_at: license?.signed_at || "",
        valid_from: license?.valid_from || "",
        valid_to: license?.valid_to || "",
        status: license?.status || "active",
      });
    }
  }, [open, license]);
  const invalidDates = Boolean(form.valid_from && form.valid_to && form.valid_to < form.valid_from);
  const save = useApiMutation(
    () => {
      const body = {
        number: form.number.trim() || null,
        seats: form.seats ? Number(form.seats) : null,
        signed_at: form.signed_at || null,
        valid_from: form.valid_from || null,
        valid_to: form.valid_to || null,
        status: form.status,
      };
      return license ? updateLicense(license.id, body) : createLicense(interactionId, productLinkId!, body);
    },
    {
      success: license ? "Лицензия сохранена" : "Лицензия добавлена",
      onSuccess: () => {
        invalidateInteractionData(interactionId);
        onClose();
      },
    },
  );
  const set = (key: keyof LicenseForm, value: string) => setForm((current) => ({ ...current, [key]: value }));
  return (
    <Modal
      open={open}
      onClose={onClose}
      title={license ? "Лицензия" : "Новая лицензия"}
      description={`${productName} · оформляется по договору взаимодействия`}
      footer={
        <>
          <Button variant="outline" onClick={onClose}>
            Отмена
          </Button>
          <Button loading={save.isPending} disabled={invalidDates} onClick={() => save.mutate(undefined)}>
            Сохранить
          </Button>
        </>
      }
    >
      <div className="form-grid">
        <TextField label="Номер лицензии" value={form.number} onChange={(value) => set("number", value)} maxLength={100} />
        <TextField
          label="Количество мест"
          type="number"
          min={0}
          value={form.seats}
          onChange={(value) => set("seats", value.replace(/\D/g, ""))}
        />
        <TextField label="Подписана" type="date" value={form.signed_at} onChange={(value) => set("signed_at", value)} />
        <SelectField
          label="Статус"
          value={form.status}
          onChange={(value) => set("status", value)}
          options={(["active", "expired", "revoked"] as const).map((value) => ({ value, label: label("license_status", value) }))}
          hint="Действующая с прошедшим сроком сама станет «Истекла»"
        />
        <TextField label="Действует с" type="date" value={form.valid_from} onChange={(value) => set("valid_from", value)} />
        <TextField
          label="Действует по"
          type="date"
          value={form.valid_to}
          onChange={(value) => set("valid_to", value)}
          error={invalidDates ? "Окончание раньше начала" : undefined}
          hint="За 60 дней до окончания система предупредит ответственного"
        />
      </div>
    </Modal>
  );
}

/** Добавление продукта сразу с программами взаимодействия, где он используется. */
function ProductModal({
  open,
  onClose,
  interaction,
  catalog,
}: {
  open: boolean;
  onClose: () => void;
  interaction: InteractionDetail;
  catalog: Set<string>;
}) {
  const { can } = useSession();
  const products = useProducts();
  const vendors = useVendors();
  const [productId, setProductId] = useState("");
  const [links, setLinks] = useState<string[]>([]);
  const [comment, setComment] = useState("");
  const programs = interaction.program_links || [];
  const taken = new Set((interaction.product_links || []).map((item) => item.product_id));
  const vendorName = Object.fromEntries((vendors.data || []).map((item) => [item.id, item.name]));

  useEffect(() => {
    if (!open) return;
    setProductId("");
    setLinks([]);
    setComment("");
  }, [open]);
  // Программы, где продукт используется по справочнику, отмечаются сами.
  useEffect(() => {
    if (!productId) return;
    setLinks(programs.filter((item) => catalog.has(`${item.program_id}:${productId}`)).map((item) => item.id));
  }, [productId]); // eslint-disable-line react-hooks/exhaustive-deps

  const exceptions = programs.filter((item) => links.includes(item.id) && !catalog.has(`${item.program_id}:${productId}`));
  const mayException = can("product_exception");
  const save = useApiMutation(
    () =>
      addProduct(interaction.id, {
        product_id: productId,
        program_link_ids: links,
        exception_comment: exceptions.length ? comment.trim() : null,
      }),
    {
      success: "Продукт добавлен",
      onSuccess: () => {
        invalidateInteractionData(interaction.id);
        onClose();
      },
    },
  );
  const blocked = !productId || links.length === 0 || (exceptions.length > 0 && (!mayException || !comment.trim()));

  return (
    <Modal
      open={open}
      onClose={onClose}
      title="Добавить ИТ-продукт"
      description="Продукт - инструмент программы: отметьте программы взаимодействия, где он используется."
      footer={
        <>
          <Button variant="outline" onClick={onClose}>
            Отмена
          </Button>
          <Button loading={save.isPending} disabled={blocked} onClick={() => save.mutate(undefined)}>
            Добавить
          </Button>
        </>
      }
    >
      <div className="stack">
        <SelectField
          label="Продукт"
          required
          value={productId}
          onChange={setProductId}
          placeholder="Выберите продукт"
          options={(products.data || [])
            .filter((item) => item.is_active && !taken.has(item.id))
            .map((item) => ({
              value: item.id,
              label: vendorName[item.vendor_id || ""] ? `${item.name} (${vendorName[item.vendor_id || ""]})` : item.name,
            }))}
        />
        {productId && (
          <div className="field">
            <span className="field__label">Используется в программах</span>
            <div className="choice-list">
              {programs.map((item) => {
                const inCatalog = catalog.has(`${item.program_id}:${productId}`);
                return (
                  <Checkbox
                    key={item.id}
                    checked={links.includes(item.id)}
                    onChange={(checked) =>
                      setLinks((current) => (checked ? [...current, item.id] : current.filter((id) => id !== item.id)))
                    }
                    label={
                      <span>
                        {item.program?.name || "Программа"}
                        {!inCatalog && <small className="muted"> · нет в справочнике - исключение</small>}
                      </span>
                    }
                  />
                );
              })}
            </div>
          </div>
        )}
        {exceptions.length > 0 &&
          (mayException ? (
            <TextAreaField
              label="Почему продукт нужен этой программе"
              required
              value={comment}
              onChange={setComment}
              rows={2}
              maxLength={2000}
              hint="Связь вне справочника сохраняется как исключение руководителя"
            />
          ) : (
            <p className="field__error">
              Связь продукта с программой, которой нет в справочнике, добавляет руководитель как исключение.
            </p>
          ))}
      </div>
    </Modal>
  );
}

export function CompositionTab({ interaction }: { interaction: InteractionDetail }) {
  const label = useLabel();
  const confirm = useConfirm();
  const { can } = useSession();
  const canWork = can("work_interaction");
  const programs = usePrograms();
  const directions = useDirections();
  const vendors = useVendors();
  const catalogLinks = useQuery({ queryKey: keys.programProducts, queryFn: listProgramProducts, staleTime: 5 * 60_000 });
  const [programId, setProgramId] = useState("");
  const [addingProduct, setAddingProduct] = useState(false);
  const [licenseTarget, setLicenseTarget] = useState<{
    productLinkId: string | null;
    license: License | null;
    productName: string;
  } | null>(null);

  const catalog = useMemo(
    () => new Set((catalogLinks.data || []).map((item) => `${item.program_id}:${item.product_id}`)),
    [catalogLinks.data],
  );
  const directionName = useMemo(
    () => Object.fromEntries((directions.data || []).map((item) => [item.id, item.name])),
    [directions.data],
  );
  const vendorName = useMemo(() => Object.fromEntries((vendors.data || []).map((item) => [item.id, item.name])), [vendors.data]);
  const programLinks = interaction.program_links || [];
  const productLinks = interaction.product_links || [];
  const pairs = interaction.links || [];
  const programById = Object.fromEntries(programLinks.map((item) => [item.id, item]));
  const productById = Object.fromEntries(productLinks.map((item) => [item.id, item]));
  const linkedPrograms = new Set(programLinks.map((item) => item.program_id));
  const hasContract = Boolean(interaction.contract);
  const refresh = () => invalidateInteractionData(interaction.id);

  const add = useApiMutation((id: string) => addProgram(interaction.id, id), {
    success: "Программа добавлена",
    onSuccess: () => {
      setProgramId("");
      refresh();
    },
  });
  const setProgramStatus = useApiMutation(
    ({ id, status, comment }: { id: string; status: ProgramStatus; comment: string }) =>
      updateProgram(interaction.id, id, status, comment),
    { success: "Статус внедрения изменён", onSuccess: refresh },
  );
  const dropProgram = useApiMutation((id: string) => removeProgram(interaction.id, id), {
    success: "Программа убрана",
    onSuccess: refresh,
  });
  const setProductStatus = useApiMutation(
    ({ id, status, comment }: { id: string; status: ProductStatus; comment: string }) =>
      updateProduct(interaction.id, id, status, comment),
    { success: "Статус передачи изменён", onSuccess: refresh },
  );
  const dropProduct = useApiMutation((id: string) => removeProduct(interaction.id, id), {
    success: "Продукт убран",
    onSuccess: refresh,
  });
  const link = useApiMutation(
    (body: { program_link_id: string; product_link_id: string; exception_comment?: string | null }) =>
      linkProduct(interaction.id, body),
    { success: "Продукт связан с программой", onSuccess: refresh },
  );
  const unlink = useApiMutation(
    ({ programLinkId, productLinkId }: { programLinkId: string; productLinkId: string }) =>
      unlinkProduct(interaction.id, programLinkId, productLinkId),
    { success: "Связь убрана", onSuccess: refresh },
  );
  const dropLicense = useApiMutation((id: string) => deleteLicense(id), { success: "Лицензия удалена", onSuccess: refresh });

  /** Ручное изменение статуса в обход процесса, с комментарием. */
  const changeStatus = async (kind: "program" | "product", id: string, name: string, status: string) => {
    const comment = await confirm({
      title: `Изменить статус «${name}» вручную?`,
      message:
        "Обычно статус ставит сам этап процесса. Ручное изменение - исключение: объясните его, комментарий попадёт в историю.",
      confirmLabel: "Изменить",
      reason: { label: "Комментарий", required: true, placeholder: "Например: продукт передан досрочно по письму вуза" },
    });
    if (!comment) return;
    if (kind === "program") setProgramStatus.mutate({ id, status: status as ProgramStatus, comment });
    else setProductStatus.mutate({ id, status: status as ProductStatus, comment });
  };

  const addLink = async (product: InteractionProduct, programLinkId: string) => {
    const program = programById[programLinkId];
    const inCatalog = catalog.has(`${program?.program_id}:${product.product_id}`);
    if (inCatalog) {
      link.mutate({ program_link_id: programLinkId, product_link_id: product.id });
      return;
    }
    if (!can("product_exception")) {
      await confirm({
        title: "Связи нет в справочнике",
        message: "Продукт не используется в этой программе по справочнику. Такую связь добавляет руководитель как исключение.",
        confirmLabel: "Понятно",
        notice: true,
      });
      return;
    }
    const comment = await confirm({
      title: "Связь вне справочника",
      message: `«${product.product?.name}» не связан с «${program?.program?.name}» в справочнике. Связь сохранится как исключение.`,
      confirmLabel: "Связать",
      reason: { label: "Почему продукт нужен программе", required: true },
    });
    if (comment) link.mutate({ program_link_id: programLinkId, product_link_id: product.id, exception_comment: comment });
  };

  return (
    <div className="stack">
      <Card title="ИТ-программы" description="Образовательные программы, которые вуз внедряет в этом взаимодействии." flush>
        {programLinks.length === 0 ? (
          <EmptyState title="Программы не добавлены">Добавьте программу из каталога ИТ Школы.</EmptyState>
        ) : (
          <div className="table-wrap">
            <table className="data-table data-table--cards">
              <thead>
                <tr>
                  <th scope="col">Программа</th>
                  <th scope="col">Направление</th>
                  <th scope="col">Продукты в программе</th>
                  <th scope="col">Статус внедрения</th>
                  <th scope="col" className="col-actions">
                    <span className="visually-hidden">Действия</span>
                  </th>
                </tr>
              </thead>
              <tbody>
                {programLinks.map((item) => {
                  const used = pairs.filter((pair) => pair.program_link_id === item.id);
                  return (
                    <tr key={item.id}>
                      <td className="cell-primary">
                        <strong>{item.program?.name || "—"}</strong>
                      </td>
                      <td data-label="Направление">{directionName[item.program?.direction_id || ""] || "—"}</td>
                      <td data-label="Продукты">
                        {used.length === 0 ? (
                          <span className="muted">—</span>
                        ) : (
                          <span className="tags">
                            {used.map((pair) => (
                              <Tag key={pair.product_link_id} tone={pair.is_exception ? "warn" : undefined}>
                                {productById[pair.product_link_id]?.product?.name || "Продукт"}
                              </Tag>
                            ))}
                          </span>
                        )}
                      </td>
                      <td data-label="Статус внедрения">
                        {canWork ? (
                          <SelectField
                            size="s"
                            value={item.implementation_status}
                            onChange={(status) =>
                              void changeStatus("program", item.id, item.program?.name || "Программа", status)
                            }
                            options={PROGRAM_STATUSES.map((value) => ({ value, label: label("program_status", value) }))}
                          />
                        ) : (
                          <StatusBadge tone={PROGRAM_TONE[item.implementation_status]}>
                            {label("program_status", item.implementation_status)}
                          </StatusBadge>
                        )}
                      </td>
                      <td className="col-actions" data-label="">
                        {canWork && (
                          <button
                            type="button"
                            className="icon-btn"
                            aria-label={`Убрать программу ${item.program?.name}`}
                            onClick={async () => {
                              // Программу со связанными продуктами сервер не
                              // уберёт, сначала связи переносят или убирают.
                              if (used.length) {
                                await confirm({
                                  title: `С программой «${item.program?.name}» связаны продукты`,
                                  message:
                                    "Сначала уберите связи в блоке «ИТ-продукты и лицензии» или свяжите продукты с другой программой - потом программу можно будет убрать.",
                                  confirmLabel: "Понятно",
                                  notice: true,
                                });
                                return;
                              }
                              const ok = await confirm({
                                title: `Убрать программу «${item.program?.name}»?`,
                                confirmLabel: "Убрать",
                                danger: true,
                              });
                              if (ok !== null) dropProgram.mutate(item.id);
                            }}
                          >
                            <Trash2 size={16} />
                          </button>
                        )}
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        )}
        {canWork && (
          <div className="card__footer" style={{ justifyContent: "flex-start", flexWrap: "wrap" }}>
            <SelectField
              value={programId}
              onChange={setProgramId}
              placeholder="Выберите программу"
              options={(programs.data || [])
                .filter((item) => item.is_active && !linkedPrograms.has(item.id))
                .map((item) => ({ value: item.id, label: item.name }))}
            />
            <Button
              variant="secondary"
              icon={Plus}
              disabled={!programId}
              loading={add.isPending}
              onClick={() => add.mutate(programId)}
            >
              Добавить программу
            </Button>
          </div>
        )}
      </Card>

      <Card
        title="ИТ-продукты и лицензии"
        description={
          hasContract
            ? "Продукты вендоров для программ взаимодействия и лицензии на них по договору."
            : "Продукты вендоров для программ взаимодействия. Лицензии добавляются, когда появится договор."
        }
        flush
      >
        {productLinks.length === 0 ? (
          <EmptyState title="Продукты не добавлены">
            {programLinks.length
              ? "Добавьте продукт и отметьте программы, где он используется."
              : "Сначала добавьте программу: продукт всегда используется в программе."}
          </EmptyState>
        ) : (
          <div className="list">
            {productLinks.map((item) => {
              const used = pairs.filter((pair) => pair.product_link_id === item.id);
              const free = programLinks.filter((program) => !used.some((pair) => pair.program_link_id === program.id));
              return (
                <div key={item.id} className="list-item" style={{ alignItems: "flex-start", flexDirection: "column", gap: 10 }}>
                  <div className="row-between" style={{ width: "100%" }}>
                    <div className="list-item__main">
                      <strong>{item.product?.name || "—"}</strong>
                      <small>Вендор: {vendorName[item.product?.vendor_id || ""] || "—"}</small>
                    </div>
                    <div className="row">
                      {canWork ? (
                        <SelectField
                          size="s"
                          label={<span className="visually-hidden">Статус передачи</span>}
                          value={item.transfer_status}
                          onChange={(status) => void changeStatus("product", item.id, item.product?.name || "Продукт", status)}
                          options={PRODUCT_STATUSES.map((value) => ({ value, label: label("product_status", value) }))}
                        />
                      ) : (
                        <StatusBadge tone={PRODUCT_TONE[item.transfer_status]}>
                          {label("product_status", item.transfer_status)}
                        </StatusBadge>
                      )}
                      {canWork && hasContract && (
                        <Button
                          variant="ghost"
                          size="s"
                          icon={KeyRound}
                          onClick={() =>
                            setLicenseTarget({ productLinkId: item.id, license: null, productName: item.product?.name || "" })
                          }
                        >
                          Лицензия
                        </Button>
                      )}
                      {canWork && (
                        <button
                          type="button"
                          className="icon-btn"
                          aria-label={`Убрать продукт ${item.product?.name}`}
                          onClick={async () => {
                            const ok = await confirm({
                              title: `Убрать продукт «${item.product?.name}»?`,
                              message: "Уберутся и его связи с программами. Продукт с лицензиями убрать нельзя.",
                              confirmLabel: "Убрать",
                              danger: true,
                            });
                            if (ok !== null) dropProduct.mutate(item.id);
                          }}
                        >
                          <Trash2 size={16} />
                        </button>
                      )}
                    </div>
                  </div>
                  <div className="row" style={{ gap: 6, flexWrap: "wrap" }}>
                    <span className="muted">
                      <Link2 size={13} aria-hidden="true" /> Используется в:
                    </span>
                    {used.length === 0 && <Tag tone="bad">ни в одной программе - поправьте данные</Tag>}
                    {used.map((pair) => (
                      <span key={pair.program_link_id} className={`tag ${pair.is_exception ? "tag--warn" : ""}`}>
                        {pair.is_exception ? (
                          <Hint
                            title="Связь вне справочника"
                            content={pair.exception_comment || "Без комментария"}
                            label={`${programById[pair.program_link_id]?.program?.name || "Программа"} · исключение: ${
                              pair.exception_comment || "без комментария"
                            }`}
                          >
                            <span>{programById[pair.program_link_id]?.program?.name || "Программа"} · исключение</span>
                          </Hint>
                        ) : (
                          programById[pair.program_link_id]?.program?.name || "Программа"
                        )}
                        {canWork && used.length > 1 && (
                          <button
                            type="button"
                            className="icon-btn"
                            style={{ width: 18, height: 18, marginLeft: 2 }}
                            aria-label="Убрать связь"
                            onClick={() => unlink.mutate({ programLinkId: pair.program_link_id, productLinkId: item.id })}
                          >
                            <X size={12} />
                          </button>
                        )}
                      </span>
                    ))}
                    {canWork && free.length > 0 && (
                      <select
                        className="control control--s"
                        aria-label={`Связать ${item.product?.name} с программой`}
                        value=""
                        onChange={(event) => event.target.value && void addLink(item, event.target.value)}
                        style={{ width: "auto" }}
                      >
                        <option value="">+ связать с программой</option>
                        {free.map((program) => (
                          <option key={program.id} value={program.id}>
                            {program.program?.name}
                          </option>
                        ))}
                      </select>
                    )}
                  </div>
                  {(item.licenses || []).length > 0 && (
                    <div className="files" style={{ width: "100%" }}>
                      {(item.licenses || []).map((license) => {
                        const left = daysUntil(license.valid_to);
                        return (
                          <div key={license.id} className="file-row">
                            <KeyRound size={16} />
                            <div className="file-row__name">
                              <button
                                type="button"
                                className="link-btn"
                                disabled={!canWork}
                                onClick={() =>
                                  setLicenseTarget({ productLinkId: item.id, license, productName: item.product?.name || "" })
                                }
                              >
                                {license.number || "Без номера"}
                                {license.seats ? ` · ${countLabel(license.seats, ["место", "места", "мест"])}` : ""}
                              </button>
                              <small>
                                {formatDate(license.valid_from)} — {formatDate(license.valid_to)}
                                {license.status === "active" && left !== null && left <= 60 && (
                                  <span className="field__error">
                                    {" "}
                                    · {left < 0 ? "срок истёк" : `осталось ${countLabel(left, DAYS)}`}
                                  </span>
                                )}
                              </small>
                            </div>
                            <StatusBadge tone={LICENSE_TONE[license.status]}>
                              {label("license_status", license.status)}
                            </StatusBadge>
                            {canWork && (
                              <button
                                type="button"
                                className="icon-btn"
                                aria-label="Удалить лицензию"
                                onClick={async () => {
                                  const ok = await confirm({ title: "Удалить лицензию?", confirmLabel: "Удалить", danger: true });
                                  if (ok !== null) dropLicense.mutate(license.id);
                                }}
                              >
                                <Trash2 size={16} />
                              </button>
                            )}
                          </div>
                        );
                      })}
                    </div>
                  )}
                </div>
              );
            })}
          </div>
        )}
        {canWork && (
          <div className="card__footer" style={{ justifyContent: "flex-start" }}>
            <Button variant="secondary" icon={Plus} disabled={programLinks.length === 0} onClick={() => setAddingProduct(true)}>
              Добавить продукт
            </Button>
            {programLinks.length === 0 && <span className="muted">Сначала добавьте программу.</span>}
          </div>
        )}
      </Card>

      <ProductModal open={addingProduct} onClose={() => setAddingProduct(false)} interaction={interaction} catalog={catalog} />
      <LicenseModal
        open={licenseTarget !== null}
        onClose={() => setLicenseTarget(null)}
        interactionId={interaction.id}
        productLinkId={licenseTarget?.productLinkId || null}
        license={licenseTarget?.license || null}
        productName={licenseTarget?.productName || ""}
      />
    </div>
  );
}
