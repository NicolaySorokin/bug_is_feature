/**
 * Выбор файлов: перетаскиванием или через проводник.
 *
 * Типы и размер проверяются сразу, до отправки: список разрешённых
 * расширений (ТЗ, раздел «Функциональные требования», п. 6) и предел
 * размера приходят с сервера, так что клиент и сервер не расходятся.
 */
import { Paperclip, Upload, X } from "lucide-react";
import { useRef, useState } from "react";
import { useEnums } from "../api/queries";
import { fileSize } from "../lib/format";

export function extensionOf(name: string): string {
  const match = /\.([^.]+)$/.exec(name.toLowerCase());
  return match ? match[1] : "";
}

export function FilePicker({
  files,
  onChange,
  multiple = true,
  accept,
  title = "Перетащите файлы сюда или выберите на компьютере",
}: {
  files: File[];
  onChange: (files: File[]) => void;
  multiple?: boolean;
  /** Свои расширения (например, ["xlsx", "xls"]); по умолчанию - разрешённые для вложений. */
  accept?: string[];
  title?: string;
}) {
  const inputRef = useRef<HTMLInputElement>(null);
  const [over, setOver] = useState(false);
  const [problem, setProblem] = useState<string | null>(null);
  const { data: enums } = useEnums();
  const allowed = accept || enums?.uploads.allowed_extensions || [];
  const maxBytes = (enums?.uploads.max_size_mb || 25) * 1024 * 1024;

  const add = (list: FileList | null) => {
    if (!list) return;
    const accepted: File[] = [];
    const rejected: string[] = [];
    Array.from(list).forEach((file) => {
      if (allowed.length && !allowed.includes(extensionOf(file.name))) rejected.push(`${file.name}: тип не поддерживается`);
      else if (file.size > maxBytes) rejected.push(`${file.name}: больше ${enums?.uploads.max_size_mb || 25} МБ`);
      else accepted.push(file);
    });
    setProblem(rejected.length ? rejected.join("; ") : null);
    if (accepted.length) onChange(multiple ? [...files, ...accepted] : accepted.slice(0, 1));
  };

  return (
    <div className="stack-s">
      <div
        className={`dropzone ${over ? "dropzone--over" : ""}`}
        role="button"
        tabIndex={0}
        onClick={() => inputRef.current?.click()}
        onKeyDown={(event) => {
          if (event.key === "Enter" || event.key === " ") {
            event.preventDefault();
            inputRef.current?.click();
          }
        }}
        onDragOver={(event) => {
          event.preventDefault();
          setOver(true);
        }}
        onDragLeave={() => setOver(false)}
        onDrop={(event) => {
          event.preventDefault();
          setOver(false);
          add(event.dataTransfer.files);
        }}
      >
        <Upload size={20} />
        <strong>{title}</strong>
        <span>
          {allowed.length ? allowed.map((item) => item.toUpperCase()).join(", ") : "Любые файлы"} · до{" "}
          {enums?.uploads.max_size_mb || 25} МБ
        </span>
        <input
          ref={inputRef}
          type="file"
          hidden
          multiple={multiple}
          accept={allowed.map((item) => `.${item}`).join(",")}
          onChange={(event) => {
            add(event.target.files);
            event.target.value = "";
          }}
        />
      </div>
      {problem && <span className="field__error">{problem}</span>}
      {files.length > 0 && (
        <div className="files">
          {files.map((file, index) => (
            <div key={`${file.name}-${index}`} className="file-row">
              <Paperclip size={16} />
              <div className="file-row__name">
                <span>{file.name}</span>
                <small>{fileSize(file.size)}</small>
              </div>
              <button
                type="button"
                className="icon-btn"
                aria-label={`Убрать ${file.name}`}
                onClick={() => onChange(files.filter((_, position) => position !== index))}
              >
                <X size={16} />
              </button>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
