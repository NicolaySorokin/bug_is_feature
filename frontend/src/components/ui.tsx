/**
 * Базовые элементы интерфейса.
 *
 * Кнопки, поля ввода, переключатели, вкладки, бейджи и уведомления - это
 * компоненты дизайн-системы Atomaro (@atomaro/ui-kit) в теме Ростелекома.
 * Обёртки задают им единые размеры и варианты, чтобы экраны выглядели
 * одинаково и не повторяли настройки в каждом месте.
 */
import {
  Badge as AtomaroBadge,
  Button as AtomaroButton,
  Checkbox as AtomaroCheckbox,
  InlineNotification as AtomaroNotification,
  Input as AtomaroInput,
  Loader as AtomaroLoader,
  Switch as AtomaroSwitch,
  TextArea as AtomaroTextArea,
  Tooltip as AtomaroTooltip,
} from "@atomaro/ui-kit";
import { AlertTriangle, Inbox, Search, type LucideIcon } from "lucide-react";
import { useEffect, useId, useRef, type ChangeEvent, type KeyboardEvent, type ReactNode } from "react";
import { ApiError, errorMessage } from "../api/client";
import type { Tone } from "../lib/labels";

// --- Кнопки -------------------------------------------------------------------

type ButtonVariant = "primary" | "secondary" | "outline" | "ghost" | "danger";

export interface ButtonProps {
  children?: ReactNode;
  variant?: ButtonVariant;
  size?: "s" | "m" | "l";
  icon?: LucideIcon;
  iconRight?: LucideIcon;
  type?: "button" | "submit";
  disabled?: boolean;
  loading?: boolean;
  onClick?: () => void;
  title?: string;
  className?: string;
  form?: string;
}

export function Button({
  children,
  variant = "primary",
  size = "m",
  icon: Icon,
  iconRight: IconRight,
  type = "button",
  disabled,
  loading,
  onClick,
  title,
  className = "",
  form,
}: ButtonProps) {
  const iconSize = size === "s" ? 14 : 16;
  const prefix = loading ? <AtomaroLoader size="2xs" variant="secondary" /> : Icon ? <Icon size={iconSize} /> : undefined;
  return (
    <AtomaroButton
      type={type}
      size={size}
      variant={variant === "danger" ? "outline" : variant}
      colorScheme={variant === "outline" || variant === "ghost" || variant === "danger" ? "neutral" : "accent"}
      className={`${variant === "danger" ? "btn-danger" : ""} ${className}`.trim()}
      iconPrefix={prefix}
      iconSuffix={IconRight ? <IconRight size={iconSize} /> : undefined}
      label={children}
      disabled={disabled || loading}
      onClick={onClick}
      title={title}
      form={form}
      aria-busy={loading || undefined}
    />
  );
}

/** Квадратная кнопка с иконкой: подпись обязательна - её читает экранный диктор. */
export function IconButton({
  icon: Icon,
  label,
  onClick,
  disabled,
  badge,
  className = "",
  size = 18,
  expanded,
}: {
  icon: LucideIcon;
  label: string;
  onClick?: () => void;
  disabled?: boolean;
  badge?: number;
  className?: string;
  size?: number;
  expanded?: boolean;
}) {
  return (
    <button
      type="button"
      className={`icon-btn ${className}`}
      aria-label={label}
      title={label}
      onClick={onClick}
      disabled={disabled}
      aria-expanded={expanded}
    >
      <Icon size={size} />
      {badge ? <span className="icon-btn__dot">{badge > 99 ? "99+" : badge}</span> : null}
    </button>
  );
}

// --- Состояния ------------------------------------------------------------------

export function Loading({ text = "Загружаем данные" }: { text?: string }) {
  return (
    <div className="loading" role="status">
      <AtomaroLoader size="s" variant="primary" />
      <span>{text}…</span>
    </div>
  );
}

export function Spinner() {
  return <AtomaroLoader size="2xs" variant="primary" />;
}

export function EmptyState({
  icon: Icon = Inbox,
  title,
  children,
  action,
}: {
  icon?: LucideIcon;
  title: string;
  children?: ReactNode;
  action?: ReactNode;
}) {
  return (
    <div className="state">
      <div className="state__icon">
        <Icon size={22} />
      </div>
      <h3>{title}</h3>
      {children && <p>{children}</p>}
      {action}
    </div>
  );
}

/** Ошибка загрузки: сообщение для человека и код ошибки API для поддержки. */
export function ErrorState({
  error,
  onRetry,
  title = "Не удалось загрузить данные",
}: {
  error: unknown;
  onRetry?: () => void;
  title?: string;
}) {
  const code = error instanceof ApiError ? error.code : null;
  const status = error instanceof ApiError && error.status ? error.status : null;
  return (
    <div className="state state--error" role="alert">
      <div className="state__icon">
        <AlertTriangle size={22} />
      </div>
      <h3>{title}</h3>
      <p>{errorMessage(error)}</p>
      {code && (
        <p className="muted">
          Код ошибки: <code>{code}</code>
          {status ? <> · HTTP {status}</> : null}
        </p>
      )}
      {onRetry && (
        <Button variant="secondary" onClick={onRetry}>
          Повторить
        </Button>
      )}
    </div>
  );
}

export function Notice({
  tone = "info",
  title,
  children,
  actions,
}: {
  tone?: "info" | "warning" | "error" | "success";
  title: string;
  children?: string;
  actions?: { label: string; onClick: () => void }[];
}) {
  return (
    <AtomaroNotification
      className="notice"
      colorScheme={tone}
      title={title}
      subtitle={children}
      closeButton={false}
      actionButtons={actions?.map((action) => ({ label: action.label, action: action.onClick }))}
    />
  );
}

// --- Бейджи ------------------------------------------------------------------------

const BADGE_SCHEME: Record<Tone, "success" | "warning" | "error" | "info" | "neutral" | "status-04"> = {
  success: "success",
  warning: "warning",
  error: "error",
  info: "info",
  neutral: "neutral",
  accent: "status-04",
};

/** Статус с цветом и подписью: цвет никогда не единственный носитель смысла. */
export function StatusBadge({ tone = "neutral", children, title }: { tone?: Tone; children: ReactNode; title?: string }) {
  return (
    <AtomaroBadge
      className="status-badge"
      size="s"
      variant="secondary"
      colorScheme={BADGE_SCHEME[tone]}
      title={title}
      label={
        <>
          <span className="status-badge__dot" aria-hidden="true" />
          {children}
        </>
      }
    />
  );
}

export function Tag({ children, tone }: { children: ReactNode; tone?: "accent" | "warn" | "bad" }) {
  return <span className={`tag ${tone ? `tag--${tone}` : ""}`}>{children}</span>;
}

/**
 * Всплывающая подсказка дизайн-системы (Tooltip Atomaro) вместо системной
 * подсказки браузера из атрибута title: появляется при наведении, с
 * заголовком и в оформлении системы.
 *
 * Atomaro скрывает содержимое триггера от экранного диктора (aria-hidden),
 * поэтому значение вместе с подсказкой продублировано скрытым текстом label.
 * По той же причине внутрь не кладутся кнопки и ссылки.
 */
export function Hint({
  title,
  content,
  label,
  children,
  placement = "top",
}: {
  title?: string;
  content?: ReactNode;
  /** Значение и подсказка одной фразой - для экранного диктора. */
  label: string;
  children: ReactNode;
  placement?: "top" | "bottom" | "left" | "right";
}) {
  return (
    <span className="hint">
      <AtomaroTooltip
        className="hint__tooltip"
        trigger="hover"
        size="m"
        closeButton={false}
        placement={placement}
        title={title}
        subtitle={content}
      >
        {children}
      </AtomaroTooltip>
      <span className="visually-hidden">{label}</span>
    </span>
  );
}

// --- Раскладка -----------------------------------------------------------------------

export function PageHeader({
  title,
  description,
  actions,
  back,
  eyebrow,
}: {
  title: ReactNode;
  description?: ReactNode;
  actions?: ReactNode;
  back?: ReactNode;
  eyebrow?: ReactNode;
}) {
  return (
    <header className="page-header">
      <div className="page-header__text">
        {back}
        {eyebrow && <span className="eyebrow">{eyebrow}</span>}
        <h1>{title}</h1>
        {description && <p>{description}</p>}
      </div>
      {actions && <div className="page-header__actions">{actions}</div>}
    </header>
  );
}

export function Card({
  title,
  description,
  actions,
  children,
  footer,
  flush,
  className = "",
  id,
}: {
  title?: ReactNode;
  description?: ReactNode;
  actions?: ReactNode;
  children?: ReactNode;
  footer?: ReactNode;
  flush?: boolean;
  className?: string;
  id?: string;
}) {
  return (
    <section className={`card ${className}`} id={id}>
      {(title || actions) && (
        <div className="card__header">
          <div>
            {title && <h2>{title}</h2>}
            {description && <p>{description}</p>}
          </div>
          {actions && <div className="row">{actions}</div>}
        </div>
      )}
      <div className={flush ? "card__body--flush" : "card__body"}>{children}</div>
      {footer && <div className="card__footer">{footer}</div>}
    </section>
  );
}

export function Kpi({
  label,
  value,
  detail,
  icon: Icon,
  tone,
  to,
  onClick,
}: {
  label: string;
  value: ReactNode;
  detail?: ReactNode;
  icon?: LucideIcon;
  tone?: "alert";
  to?: string;
  onClick?: () => void;
}) {
  const content = (
    <>
      <span className="kpi__label">
        {Icon && <Icon size={16} />}
        {label}
      </span>
      <span className="kpi__value">{value}</span>
      {detail && <span className="kpi__detail">{detail}</span>}
    </>
  );
  const className = `kpi ${tone === "alert" ? "kpi--alert" : ""}`;
  if (to) {
    return (
      <a className={className} href={to} onClick={(event) => (onClick ? (event.preventDefault(), onClick()) : undefined)}>
        {content}
      </a>
    );
  }
  if (onClick) {
    return (
      <button type="button" className={className} onClick={onClick}>
        {content}
      </button>
    );
  }
  return <div className={className}>{content}</div>;
}

export function DescriptionList({ items }: { items: [ReactNode, ReactNode][] }) {
  return (
    <dl className="dl">
      {items.map(([term, value], index) => (
        <div key={index} style={{ display: "contents" }}>
          <dt>{term}</dt>
          <dd>{value === null || value === undefined || value === "" ? "—" : value}</dd>
        </div>
      ))}
    </dl>
  );
}

export function Avatar({ name, large }: { name?: string | null; large?: boolean }) {
  const letters = (name || "?")
    .split(/\s+/)
    .filter(Boolean)
    .slice(0, 2)
    .map((part) => part[0])
    .join("")
    .toUpperCase();
  return (
    <span className={`avatar ${large ? "avatar--l" : ""}`} aria-hidden="true">
      {letters}
    </span>
  );
}

// --- Вкладки -------------------------------------------------------------------------

export interface TabItem {
  key: string;
  label: string;
  icon?: LucideIcon;
  /** Число рядом с названием: сколько записей на вкладке. */
  count?: number;
  /** Точка-метка: на вкладке есть то, что требует внимания. */
  dot?: boolean;
  hidden?: boolean;
}

/**
 * Вкладки раздела: подчёркивание фирменным цветом у выбранной, счётчики
 * записей. Разметка по WAI-ARIA (tablist / tab), стрелки влево-вправо,
 * Home и End переключают вкладки с клавиатуры. На узком экране строка
 * прокручивается, выбранная вкладка всегда видна.
 */
export function Tabs({
  items,
  value,
  onChange,
  label = "Разделы",
}: {
  items: TabItem[];
  value: string;
  onChange: (key: string) => void;
  label?: string;
}) {
  const visible = items.filter((item) => !item.hidden);
  const refs = useRef(new Map<string, HTMLButtonElement>());

  useEffect(() => {
    refs.current.get(value)?.scrollIntoView({ block: "nearest", inline: "nearest" });
  }, [value]);

  const onKeyDown = (event: KeyboardEvent<HTMLDivElement>) => {
    const index = visible.findIndex((item) => item.key === value);
    const next =
      event.key === "ArrowRight"
        ? visible[(index + 1) % visible.length]
        : event.key === "ArrowLeft"
          ? visible[(index - 1 + visible.length) % visible.length]
          : event.key === "Home"
            ? visible[0]
            : event.key === "End"
              ? visible[visible.length - 1]
              : null;
    if (!next) return;
    event.preventDefault();
    onChange(next.key);
    refs.current.get(next.key)?.focus();
  };

  return (
    <div className="tabs" role="tablist" aria-label={label} onKeyDown={onKeyDown}>
      {visible.map((item) => {
        const selected = item.key === value;
        const Icon = item.icon;
        return (
          <button
            key={item.key}
            ref={(node) => {
              if (node) refs.current.set(item.key, node);
              else refs.current.delete(item.key);
            }}
            type="button"
            role="tab"
            className="tab"
            aria-selected={selected}
            tabIndex={selected ? 0 : -1}
            onClick={() => onChange(item.key)}
          >
            {Icon && <Icon size={16} aria-hidden="true" />}
            <span>{item.label}</span>
            {item.count !== undefined && <span className="tab__count">{item.count}</span>}
            {item.dot && <span className="tab__dot" aria-label="есть что проверить" />}
          </button>
        );
      })}
    </div>
  );
}

// --- Поля формы ------------------------------------------------------------------------

export function Field({
  label,
  hint,
  error,
  required,
  children,
  htmlFor,
  className = "",
}: {
  label?: ReactNode;
  hint?: ReactNode;
  error?: ReactNode;
  required?: boolean;
  children: ReactNode;
  htmlFor?: string;
  className?: string;
}) {
  return (
    <div className={`field ${className}`}>
      {label && (
        <label className="field__label" htmlFor={htmlFor}>
          {label}
          {required && <span className="req"> *</span>}
        </label>
      )}
      {children}
      {error ? <span className="field__error">{error}</span> : hint ? <span className="field__hint">{hint}</span> : null}
    </div>
  );
}

interface TextFieldProps {
  label?: ReactNode;
  value: string;
  onChange: (value: string) => void;
  type?: "text" | "email" | "tel" | "number" | "date" | "password" | "url" | "search";
  placeholder?: string;
  hint?: ReactNode;
  error?: ReactNode;
  required?: boolean;
  disabled?: boolean;
  autoFocus?: boolean;
  className?: string;
  maxLength?: number;
  min?: string | number;
  max?: string | number;
  name?: string;
  autoComplete?: string;
}

// Поле Atomaro управляет кареткой ввода, а у полей даты, числа и почты
// браузер каретку не даёт - для них системное поле в том же оформлении.
const NATIVE_TYPES = new Set(["number", "date", "email"]);

export function TextField({
  label,
  value,
  onChange,
  hint,
  error,
  required,
  className = "",
  type = "text",
  ...rest
}: TextFieldProps) {
  const id = useId();
  return (
    <Field label={label} hint={hint} error={error} required={required} htmlFor={id} className={className}>
      {NATIVE_TYPES.has(type) ? (
        <input
          id={id}
          className={`control ${error ? "control--invalid" : ""}`}
          type={type}
          value={value}
          required={required}
          aria-invalid={Boolean(error) || undefined}
          onChange={(event) => onChange(event.target.value)}
          {...rest}
        />
      ) : (
        <AtomaroInput
          id={id}
          className="input-full"
          size="m"
          type={type}
          value={value}
          hideLabel
          forceError={Boolean(error)}
          required={required}
          onChange={(event: ChangeEvent<HTMLInputElement>) => onChange(event.target.value)}
          {...rest}
        />
      )}
    </Field>
  );
}

export function TextAreaField({
  label,
  value,
  onChange,
  hint,
  error,
  required,
  rows = 4,
  placeholder,
  disabled,
  className = "",
  maxLength,
}: {
  label?: ReactNode;
  value: string;
  onChange: (value: string) => void;
  hint?: ReactNode;
  error?: ReactNode;
  required?: boolean;
  rows?: number;
  placeholder?: string;
  disabled?: boolean;
  className?: string;
  maxLength?: number;
}) {
  const id = useId();
  return (
    <Field label={label} hint={hint} error={error} required={required} htmlFor={id} className={className}>
      <AtomaroTextArea
        id={id}
        className="textarea-full"
        value={value}
        rows={Math.max(rows, 3)}
        hideLabel
        placeholder={placeholder}
        disabled={disabled}
        maxLength={maxLength}
        onChange={(event: ChangeEvent<HTMLTextAreaElement>) => onChange(event.target.value)}
      />
    </Field>
  );
}

export interface Option {
  value: string;
  label: string;
  hint?: string;
  disabled?: boolean;
}

/** Выпадающий список: системный select - на телефоне открывается родной выбор. */
export function SelectField({
  label,
  value,
  onChange,
  options,
  placeholder,
  hint,
  error,
  required,
  disabled,
  className = "",
  size,
}: {
  label?: ReactNode;
  value: string;
  onChange: (value: string) => void;
  options: Option[];
  placeholder?: string;
  hint?: ReactNode;
  error?: ReactNode;
  required?: boolean;
  disabled?: boolean;
  className?: string;
  size?: "s";
}) {
  const id = useId();
  return (
    <Field label={label} hint={hint} error={error} required={required} htmlFor={id} className={className}>
      <select
        id={id}
        className={`control ${size === "s" ? "control--s" : ""} ${error ? "control--invalid" : ""}`}
        value={value}
        onChange={(event) => onChange(event.target.value)}
        disabled={disabled}
        required={required}
        aria-invalid={Boolean(error) || undefined}
      >
        {placeholder !== undefined && <option value="">{placeholder}</option>}
        {options.map((option) => (
          <option key={option.value} value={option.value} disabled={option.disabled}>
            {option.label}
          </option>
        ))}
      </select>
    </Field>
  );
}

export function Checkbox({
  label,
  checked,
  onChange,
  disabled,
}: {
  label: ReactNode;
  checked: boolean;
  onChange: (value: boolean) => void;
  disabled?: boolean;
}) {
  return <AtomaroCheckbox label={label} checked={checked} disabled={disabled} onChange={(value: boolean) => onChange(value)} />;
}

export function Switch({
  label,
  checked,
  onChange,
  disabled,
}: {
  label: ReactNode;
  checked: boolean;
  onChange: (value: boolean) => void;
  disabled?: boolean;
}) {
  return (
    <AtomaroSwitch label={label} checked={checked} disabled={disabled} size="s" onChange={(value: boolean) => onChange(value)} />
  );
}

export function SearchInput({
  value,
  onChange,
  placeholder = "Поиск",
  label = "Поиск",
  autoFocus,
}: {
  value: string;
  onChange: (value: string) => void;
  placeholder?: string;
  label?: string;
  autoFocus?: boolean;
}) {
  return (
    <div className="search-input">
      <Search size={16} />
      <input
        className="control"
        type="search"
        value={value}
        placeholder={placeholder}
        aria-label={label}
        autoFocus={autoFocus}
        onChange={(event) => onChange(event.target.value)}
      />
    </div>
  );
}
