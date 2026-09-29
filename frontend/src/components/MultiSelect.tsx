/** Выбор нескольких значений с поиском: фильтры отчётов и реестров. */
import { useEffect, useId, useMemo, useRef, useState, type ReactNode } from "react";
import type { Option } from "./ui";
import { Field } from "./ui";

export function MultiSelect({
  label,
  options,
  value,
  onChange,
  placeholder = "Все",
  hint,
  searchPlaceholder = "Найти",
  className = "",
}: {
  label?: ReactNode;
  options: Option[];
  value: string[];
  onChange: (value: string[]) => void;
  placeholder?: string;
  hint?: ReactNode;
  searchPlaceholder?: string;
  className?: string;
}) {
  const [open, setOpen] = useState(false);
  const [query, setQuery] = useState("");
  const rootRef = useRef<HTMLDivElement>(null);
  const id = useId();
  const panelId = `${id}-listbox`;

  useEffect(() => {
    if (!open) return;
    const onDocumentClick = (event: MouseEvent) => {
      if (!rootRef.current?.contains(event.target as Node)) setOpen(false);
    };
    const onKey = (event: KeyboardEvent) => {
      if (event.key === "Escape") setOpen(false);
    };
    document.addEventListener("click", onDocumentClick);
    document.addEventListener("keydown", onKey);
    return () => {
      document.removeEventListener("click", onDocumentClick);
      document.removeEventListener("keydown", onKey);
    };
  }, [open]);

  const selected = useMemo(() => new Set(value), [value]);
  const filtered = useMemo(() => {
    const needle = query.trim().toLowerCase();
    return needle ? options.filter((option) => option.label.toLowerCase().includes(needle)) : options;
  }, [options, query]);

  const toggle = (optionValue: string) => {
    const next = new Set(selected);
    if (next.has(optionValue)) next.delete(optionValue);
    else next.add(optionValue);
    // Порядок как в списке: одинаковые выборки дают одинаковый ключ кэша.
    onChange(options.filter((option) => next.has(option.value)).map((option) => option.value));
  };

  const labels = options.filter((option) => selected.has(option.value)).map((option) => option.label);
  const summary = labels.length === 0 ? null : labels.length === 1 ? labels[0] : `${labels[0]} и ещё ${labels.length - 1}`;

  return (
    <Field label={label} hint={hint} htmlFor={id} className={className}>
      <div className={`multi ${open ? "is-open" : ""}`} ref={rootRef}>
        <button
          id={id}
          type="button"
          className="multi__button"
          aria-haspopup="listbox"
          aria-expanded={open}
          aria-controls={panelId}
          onClick={() => setOpen((current) => !current)}
          onKeyDown={(event) => {
            if (event.key === "ArrowDown" || event.key === "Enter" || event.key === " ") {
              event.preventDefault();
              setOpen(true);
            }
          }}
        >
          <span className={`multi__value ${summary ? "" : "multi__placeholder"}`}>{summary || placeholder}</span>
          {labels.length > 1 && <span className="multi__count">{labels.length}</span>}
        </button>
        {open && (
          <div id={panelId} className="popover multi__panel" role="listbox" aria-multiselectable="true">
            {options.length > 8 && (
              <input
                className="control control--s"
                type="search"
                placeholder={searchPlaceholder}
                aria-label={searchPlaceholder}
                value={query}
                autoFocus
                onChange={(event) => setQuery(event.target.value)}
              />
            )}
            <div className="multi__options">
              {filtered.length === 0 && (
                <div className="muted" style={{ padding: 8 }}>
                  Ничего не найдено
                </div>
              )}
              {filtered.map((option) => (
                <label key={option.value} className="multi__option">
                  <input type="checkbox" checked={selected.has(option.value)} onChange={() => toggle(option.value)} />
                  <span>
                    {option.label}
                    {option.hint && <small>{option.hint}</small>}
                  </span>
                </label>
              ))}
            </div>
            <div className="multi__footer">
              <button type="button" className="link-btn" onClick={() => onChange(filtered.map((option) => option.value))}>
                Выбрать {query ? "найденные" : "все"}
              </button>
              <button type="button" className="link-btn" onClick={() => onChange([])} disabled={value.length === 0}>
                Сбросить
              </button>
            </div>
          </div>
        )}
      </div>
    </Field>
  );
}
