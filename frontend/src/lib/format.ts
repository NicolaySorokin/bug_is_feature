/** Форматирование дат, чисел и слов для русского интерфейса. */

const dateFormat = new Intl.DateTimeFormat("ru-RU", { day: "2-digit", month: "2-digit", year: "numeric" });
const dateTimeFormat = new Intl.DateTimeFormat("ru-RU", {
  day: "2-digit",
  month: "2-digit",
  year: "numeric",
  hour: "2-digit",
  minute: "2-digit",
});
const longDateFormat = new Intl.DateTimeFormat("ru-RU", { weekday: "long", day: "numeric", month: "long" });
const numberFormat = new Intl.NumberFormat("ru-RU");

function parse(value?: string | Date | null): Date | null {
  if (!value) return null;
  // Дата без времени (2026-09-25) - это день, а не полночь UTC: иначе
  // в часовых поясах западнее Гринвича она съехала бы на день назад.
  const date = typeof value === "string" && /^\d{4}-\d{2}-\d{2}$/.test(value) ? new Date(`${value}T12:00:00`) : new Date(value);
  return Number.isNaN(date.valueOf()) ? null : date;
}

export function formatDate(value?: string | Date | null, empty = "—"): string {
  const date = parse(value);
  return date ? dateFormat.format(date) : empty;
}

export function formatDateTime(value?: string | Date | null, empty = "—"): string {
  const date = parse(value);
  return date ? dateTimeFormat.format(date) : empty;
}

export function formatLongDate(value: Date = new Date()): string {
  const text = longDateFormat.format(value);
  return text.charAt(0).toUpperCase() + text.slice(1);
}

export function formatNumber(value?: number | null): string {
  return value === null || value === undefined ? "—" : numberFormat.format(value);
}

/** Склонение: plural(3, ["договор", "договора", "договоров"]) -> «договора». */
export function plural(count: number, forms: [string, string, string]): string {
  const mod10 = Math.abs(count) % 10;
  const mod100 = Math.abs(count) % 100;
  if (mod10 === 1 && mod100 !== 11) return forms[0];
  if (mod10 >= 2 && mod10 <= 4 && (mod100 < 12 || mod100 > 14)) return forms[1];
  return forms[2];
}

export function countLabel(count: number, forms: [string, string, string]): string {
  return `${formatNumber(count)} ${plural(count, forms)}`;
}

export const DAYS: [string, string, string] = ["день", "дня", "дней"];

/** Сколько дней до даты: отрицательное число - дата уже прошла. */
export function daysUntil(value?: string | null): number | null {
  const date = parse(value);
  if (!date) return null;
  const today = new Date();
  today.setHours(12, 0, 0, 0);
  return Math.round((date.valueOf() - today.valueOf()) / 86_400_000);
}

export function daysSince(value?: string | null): number | null {
  const left = daysUntil(value?.slice(0, 10));
  return left === null ? null : -left;
}

export function initials(name?: string | null): string {
  if (!name) return "—";
  return name
    .split(/\s+/)
    .filter(Boolean)
    .slice(0, 2)
    .map((part) => part[0])
    .join("")
    .toUpperCase();
}

/** «Петров Пётр Алексеевич» -> «Петров П. А.» для плотных таблиц. */
export function shortName(name?: string | null): string {
  if (!name) return "—";
  const [last, first, middle] = name.split(/\s+/);
  if (!first) return last;
  return `${last} ${first[0]}.${middle ? ` ${middle[0]}.` : ""}`;
}

export function fileSize(bytes?: number | null): string {
  if (!bytes) return "—";
  if (bytes < 1024) return `${bytes} Б`;
  if (bytes < 1024 * 1024) return `${Math.round(bytes / 1024)} КБ`;
  return `${(bytes / 1024 / 1024).toFixed(1).replace(".", ",")} МБ`;
}

/** yyyy-mm-dd в местном времени: значение для <input type="date">. */
export function toInputDate(value: Date): string {
  const pad = (part: number) => String(part).padStart(2, "0");
  return `${value.getFullYear()}-${pad(value.getMonth() + 1)}-${pad(value.getDate())}`;
}

export function yearsAgo(years: number): string {
  const date = new Date();
  date.setFullYear(date.getFullYear() - years);
  return toInputDate(date);
}
