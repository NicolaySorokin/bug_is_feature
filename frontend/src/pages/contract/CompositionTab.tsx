/**
 * Состав договора: ИТ-программы, ИТ-продукты и лицензии на продукты.
 *
 * Статус внедрения программы и передачи продукта меняется прямо в
 * строке. Лицензии видны у своего продукта с оставшимся сроком.
 */
import { KeyRound, Plus, Trash2 } from "lucide-react";
import { useEffect, useMemo, useState } from "react";
import {
  addContractProduct,
  addContractProgram,
  createLicense,
  deleteLicense,
  removeContractProduct,
  removeContractProgram,
  updateContractProduct,
  updateContractProgram,
  updateLicense,
} from "../../api/endpoints";
import { useApiMutation } from "../../api/mutations";
import { invalidateContractData, useDirections, useLabel, usePrograms, useProducts, useVendors } from "../../api/queries";
import type { ContractDetail, License, LicenseStatus } from "../../api/types";
import { useConfirm } from "../../components/Confirm";
import { Modal } from "../../components/Modal";
import { Button, Card, EmptyState, SelectField, StatusBadge, TextField } from "../../components/ui";
import { countLabel, DAYS, daysUntil, formatDate } from "../../lib/format";
import { LICENSE_TONE } from "../../lib/labels";

const IMPLEMENTATION = ["not_started", "in_progress", "implemented", "suspended"] as const;

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
  contractId,
  linkId,
  license,
  productName,
}: {
  open: boolean;
  onClose: () => void;
  contractId: string;
  linkId: string | null;
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
      return license ? updateLicense(license.id, body) : createLicense(contractId, linkId!, body);
    },
    {
      success: license ? "Лицензия сохранена" : "Лицензия добавлена",
      onSuccess: () => {
        invalidateContractData(contractId);
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
      description={productName}
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

export function CompositionTab({ contract }: { contract: ContractDetail }) {
  const label = useLabel();
  const confirm = useConfirm();
  const programs = usePrograms();
  const products = useProducts();
  const directions = useDirections();
  const vendors = useVendors();
  const [programId, setProgramId] = useState("");
  const [productId, setProductId] = useState("");
  const [licenseTarget, setLicenseTarget] = useState<{
    linkId: string | null;
    license: License | null;
    productName: string;
  } | null>(null);

  const directionName = useMemo(
    () => Object.fromEntries((directions.data || []).map((item) => [item.id, item.name])),
    [directions.data],
  );
  const vendorName = useMemo(() => Object.fromEntries((vendors.data || []).map((item) => [item.id, item.name])), [vendors.data]);
  const linkedPrograms = new Set((contract.programs || []).map((item) => item.program_id));
  const linkedProducts = new Set((contract.products || []).map((item) => item.product_id));
  const refresh = () => invalidateContractData(contract.id);

  const addProgram = useApiMutation((id: string) => addContractProgram(contract.id, id), {
    success: "Программа добавлена",
    onSuccess: () => {
      setProgramId("");
      refresh();
    },
  });
  const setProgramStatus = useApiMutation(
    ({ id, status }: { id: string; status: string }) => updateContractProgram(contract.id, id, status),
    {
      success: "Статус внедрения изменён",
      onSuccess: refresh,
    },
  );
  const removeProgram = useApiMutation((id: string) => removeContractProgram(contract.id, id), {
    success: "Программа убрана из договора",
    onSuccess: refresh,
  });
  const addProduct = useApiMutation((id: string) => addContractProduct(contract.id, id), {
    success: "Продукт добавлен",
    onSuccess: () => {
      setProductId("");
      refresh();
    },
  });
  const setProductStatus = useApiMutation(
    ({ id, status }: { id: string; status: string }) => updateContractProduct(contract.id, id, status),
    {
      success: "Статус передачи изменён",
      onSuccess: refresh,
    },
  );
  const removeProduct = useApiMutation((id: string) => removeContractProduct(contract.id, id), {
    success: "Продукт убран из договора",
    onSuccess: refresh,
  });
  const removeLicense = useApiMutation((id: string) => deleteLicense(id), { success: "Лицензия удалена", onSuccess: refresh });

  const statusOptions = IMPLEMENTATION.map((value) => ({ value, label: label("implementation_status", value) }));

  return (
    <div className="stack">
      <Card title="ИТ-программы" description="Программы обучения, которые вуз внедряет по договору." flush>
        {(contract.programs || []).length === 0 ? (
          <EmptyState title="Программы не добавлены">Добавьте программу из каталога ИТ Школы.</EmptyState>
        ) : (
          <div className="table-wrap">
            <table className="data-table data-table--cards">
              <thead>
                <tr>
                  <th scope="col">Программа</th>
                  <th scope="col">Направление</th>
                  <th scope="col">Статус внедрения</th>
                  <th scope="col" className="col-actions">
                    <span className="visually-hidden">Действия</span>
                  </th>
                </tr>
              </thead>
              <tbody>
                {(contract.programs || []).map((item) => (
                  <tr key={item.id}>
                    <td className="cell-primary">
                      <strong>{item.program?.name || "—"}</strong>
                    </td>
                    <td data-label="Направление">{directionName[item.program?.direction_id || ""] || "—"}</td>
                    <td data-label="Статус внедрения">
                      <SelectField
                        size="s"
                        value={item.implementation_status}
                        onChange={(status) => setProgramStatus.mutate({ id: item.id, status })}
                        options={statusOptions}
                      />
                    </td>
                    <td className="col-actions" data-label="">
                      <button
                        type="button"
                        className="icon-btn"
                        aria-label={`Убрать программу ${item.program?.name}`}
                        onClick={async () => {
                          const ok = await confirm({
                            title: `Убрать программу «${item.program?.name}»?`,
                            confirmLabel: "Убрать",
                            danger: true,
                          });
                          if (ok !== null) removeProgram.mutate(item.id);
                        }}
                      >
                        <Trash2 size={16} />
                      </button>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
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
            loading={addProgram.isPending}
            onClick={() => addProgram.mutate(programId)}
          >
            Добавить программу
          </Button>
        </div>
      </Card>

      <Card title="ИТ-продукты и лицензии" description="Продукты вендоров, которые передаются вузу, и лицензии на них." flush>
        {(contract.products || []).length === 0 ? (
          <EmptyState title="Продукты не добавлены">Добавьте продукт из каталога.</EmptyState>
        ) : (
          <div className="list">
            {(contract.products || []).map((item) => (
              <div key={item.id} className="list-item" style={{ alignItems: "flex-start", flexDirection: "column", gap: 10 }}>
                <div className="row-between" style={{ width: "100%" }}>
                  <div className="list-item__main">
                    <strong>{item.product?.name || "—"}</strong>
                    <small>Вендор: {vendorName[item.product?.vendor_id || ""] || "—"}</small>
                  </div>
                  <div className="row">
                    <SelectField
                      size="s"
                      label={<span className="visually-hidden">Статус передачи</span>}
                      value={item.transfer_status}
                      onChange={(status) => setProductStatus.mutate({ id: item.id, status })}
                      options={statusOptions}
                    />
                    <Button
                      variant="ghost"
                      size="s"
                      icon={KeyRound}
                      onClick={() => setLicenseTarget({ linkId: item.id, license: null, productName: item.product?.name || "" })}
                    >
                      Лицензия
                    </Button>
                    <button
                      type="button"
                      className="icon-btn"
                      aria-label={`Убрать продукт ${item.product?.name}`}
                      onClick={async () => {
                        const ok = await confirm({
                          title: `Убрать продукт «${item.product?.name}»?`,
                          message: "Вместе с продуктом удалятся его лицензии в этом договоре.",
                          confirmLabel: "Убрать",
                          danger: true,
                        });
                        if (ok !== null) removeProduct.mutate(item.id);
                      }}
                    >
                      <Trash2 size={16} />
                    </button>
                  </div>
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
                              onClick={() =>
                                setLicenseTarget({ linkId: item.id, license, productName: item.product?.name || "" })
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
                          <StatusBadge tone={LICENSE_TONE[license.status]}>{label("license_status", license.status)}</StatusBadge>
                          <button
                            type="button"
                            className="icon-btn"
                            aria-label="Удалить лицензию"
                            onClick={async () => {
                              const ok = await confirm({ title: "Удалить лицензию?", confirmLabel: "Удалить", danger: true });
                              if (ok !== null) removeLicense.mutate(license.id);
                            }}
                          >
                            <Trash2 size={16} />
                          </button>
                        </div>
                      );
                    })}
                  </div>
                )}
              </div>
            ))}
          </div>
        )}
        <div className="card__footer" style={{ justifyContent: "flex-start", flexWrap: "wrap" }}>
          <SelectField
            value={productId}
            onChange={setProductId}
            placeholder="Выберите продукт"
            options={(products.data || [])
              .filter((item) => item.is_active && !linkedProducts.has(item.id))
              .map((item) => ({
                value: item.id,
                label: vendorName[item.vendor_id || ""] ? `${item.name} (${vendorName[item.vendor_id || ""]})` : item.name,
              }))}
          />
          <Button
            variant="secondary"
            icon={Plus}
            disabled={!productId}
            loading={addProduct.isPending}
            onClick={() => addProduct.mutate(productId)}
          >
            Добавить продукт
          </Button>
        </div>
      </Card>

      <LicenseModal
        open={licenseTarget !== null}
        onClose={() => setLicenseTarget(null)}
        contractId={contract.id}
        linkId={licenseTarget?.linkId || null}
        license={licenseTarget?.license || null}
        productName={licenseTarget?.productName || ""}
      />
    </div>
  );
}
