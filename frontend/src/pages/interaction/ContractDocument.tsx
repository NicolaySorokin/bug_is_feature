/**
 * Проект договора по типовому шаблону. Реквизиты, подписант, программы и продукты подставляются
 * сами, предпросмотр показывает, чего не хватает. Файл DOCX скачивается или прикладывается
 * к взаимодействию на текущем этапе.
 */
import { useQuery } from "@tanstack/react-query";
import { Download, Paperclip } from "lucide-react";
import { useEffect, useState } from "react";
import {
  attachContractDocument,
  downloadContractDocument,
  listContractTemplates,
  previewContractDocument,
} from "../../api/endpoints";
import { useApiMutation, useDownload } from "../../api/mutations";
import { invalidateInteractionData, keys } from "../../api/queries";
import type { InteractionDetail, WorkflowView } from "../../api/types";
import { useSession } from "../../auth/session";
import { Modal } from "../../components/Modal";
import { Button, Checkbox, ErrorState, Loading, Notice, SelectField } from "../../components/ui";

/** Текст договора как в DOCX: «# » заголовок, «## » раздел. */
function DocumentPreview({ text, label }: { text: string; label: string }) {
  return (
    <div className="document-preview" role="document" aria-label={label}>
      {text.split("\n").map((line, index) => {
        const value = line.trim();
        if (!value) return <div key={index} className="document-preview__gap" />;
        if (value.startsWith("# ")) return <h3 key={index}>{value.slice(2)}</h3>;
        if (value.startsWith("## ")) return <h4 key={index}>{value.slice(3)}</h4>;
        return (
          <p key={index} className={value.startsWith("- ") ? "document-preview__item" : undefined}>
            {line}
          </p>
        );
      })}
    </div>
  );
}

export function ContractDocumentModal({
  interaction,
  workflow,
  open,
  onClose,
}: {
  interaction: InteractionDetail;
  workflow: WorkflowView | null;
  open: boolean;
  onClose: () => void;
}) {
  const { can } = useSession();
  const [download, downloading] = useDownload();
  const [templateId, setTemplateId] = useState("");
  const [toStage, setToStage] = useState(true);

  const templates = useQuery({ queryKey: keys.contractTemplates, queryFn: listContractTemplates, enabled: open });
  const active = (templates.data || []).filter((item) => item.is_active);
  useEffect(() => {
    if (!templateId && active[0]) setTemplateId(active[0].id);
  }, [active, templateId]);

  const preview = useQuery({
    queryKey: [...keys.interaction(interaction.id), "contract-document", templateId],
    queryFn: () => previewContractDocument(interaction.id, templateId),
    enabled: open && Boolean(templateId),
  });

  // Файл привязывается к текущему этапу, то есть к событию, которым процесс на него пришёл.
  const stage = (workflow?.version.stages || []).find((item) => item.id === workflow?.current_stage_id);
  const arrival = [...(workflow?.events || [])]
    .filter((event) => event.to_stage_id === workflow?.current_stage_id)
    .sort((a, b) => b.created_at.localeCompare(a.created_at))[0];

  const attach = useApiMutation(
    () => attachContractDocument(interaction.id, templateId, toStage && arrival ? arrival.id : null),
    {
      success: (file) => `Проект договора приложен: «${file.original_name}» - на вкладке «Файлы и комментарии»`,
      onSuccess: () => {
        invalidateInteractionData(interaction.id);
        onClose();
      },
    },
  );

  const missing = preview.data?.missing || [];
  // «ИНН вуза, реквизиты вуза (...)»: со строчной, кроме сокращений вроде «ИНН».
  const inline = (label: string) =>
    label[1] && label[1] === label[1].toLowerCase() ? label[0].toLowerCase() + label.slice(1) : label;
  const canAttach = can("work_interaction") && interaction.status !== "cancelled";

  return (
    <Modal
      open={open}
      onClose={onClose}
      size="wide"
      title="Договор по шаблону"
      description="Реквизиты вуза, подписант, программы и продукты подставляются из системы. Файл - DOCX: его можно поправить перед подписанием."
      footer={
        <>
          <Button variant="outline" onClick={onClose}>
            Закрыть
          </Button>
          <Button
            variant="secondary"
            icon={Download}
            loading={downloading}
            disabled={!preview.data}
            onClick={() => void download(() => downloadContractDocument(interaction.id, templateId))}
          >
            Скачать DOCX
          </Button>
          {canAttach && (
            <Button icon={Paperclip} loading={attach.isPending} disabled={!preview.data} onClick={() => attach.mutate()}>
              Приложить к взаимодействию
            </Button>
          )}
        </>
      }
    >
      {templates.isPending ? (
        <Loading />
      ) : templates.isError ? (
        <ErrorState error={templates.error} onRetry={() => void templates.refetch()} />
      ) : active.length === 0 ? (
        <Notice tone="warning" title="Нет действующих шаблонов">
          Шаблоны договоров ведёт руководитель: «Справочники» → «Шаблоны договоров».
        </Notice>
      ) : (
        <div className="stack">
          {active.length > 1 && (
            <SelectField
              label="Шаблон"
              value={templateId}
              onChange={setTemplateId}
              options={active.map((item) => ({ value: item.id, label: item.name }))}
            />
          )}
          {missing.length > 0 && (
            <Notice tone="warning" title="Не всё заполнено">
              {`Нет данных: ${missing.map((item) => inline(item.label)).join(", ")}. На их месте в документе будет пропуск - дополните карточку вуза или договор либо впишите от руки.`}
            </Notice>
          )}
          {canAttach && arrival && stage && (
            <Checkbox label={`Привязать к текущему этапу «${stage.name}»`} checked={toStage} onChange={setToStage} />
          )}
          {preview.isPending ? (
            <Loading />
          ) : preview.isError ? (
            <ErrorState error={preview.error} onRetry={() => void preview.refetch()} />
          ) : (
            <>
              <DocumentPreview text={preview.data.text} label={`Предпросмотр: ${preview.data.filename}`} />
              <small className="muted">Файл: {preview.data.filename}</small>
            </>
          )}
        </div>
      )}
    </Modal>
  );
}
