/**
 * Таблица реестра.
 *
 * На широком экране - обычная таблица с сортировкой по заголовкам, на
 * телефоне каждая строка превращается в карточку «подпись - значение».
 * Строка открывается кликом, а в главной ячейке стоит обычная ссылка:
 * её можно открыть в новой вкладке.
 */
import { ArrowDown, ArrowUp, ArrowUpDown, ChevronLeft, ChevronRight } from "lucide-react";
import type { ReactNode } from "react";
import { countLabel } from "../lib/format";

export interface Column<T> {
  key: string;
  title: string;
  render: (row: T) => ReactNode;
  /** Ключ сортировки: если задан, заголовок кликабелен. */
  sortKey?: string;
  className?: string;
  /** Главная ячейка: на телефоне она заголовок карточки. */
  primary?: boolean;
}

export interface SortState {
  key: string;
  direction: "asc" | "desc";
}

export function DataTable<T>({
  columns,
  rows,
  rowKey,
  onRowClick,
  sort,
  onSortChange,
  empty,
  refreshing,
  caption,
}: {
  columns: Column<T>[];
  rows: T[];
  rowKey: (row: T) => string;
  onRowClick?: (row: T) => void;
  sort?: SortState;
  onSortChange?: (sort: SortState) => void;
  empty?: ReactNode;
  refreshing?: boolean;
  caption?: string;
}) {
  if (rows.length === 0 && empty) return <>{empty}</>;

  const header = (column: Column<T>) => {
    if (!column.sortKey || !onSortChange) return column.title;
    const active = sort?.key === column.sortKey;
    const Icon = !active ? ArrowUpDown : sort?.direction === "asc" ? ArrowUp : ArrowDown;
    return (
      <button
        type="button"
        className="sort-btn"
        data-active={active}
        onClick={() =>
          onSortChange({
            key: column.sortKey!,
            direction: active && sort?.direction === "asc" ? "desc" : "asc",
          })
        }
      >
        {column.title}
        <Icon size={13} />
      </button>
    );
  };

  return (
    <div className={`table-wrap ${refreshing ? "is-refreshing" : ""}`}>
      <table className="data-table data-table--cards">
        {caption && <caption className="visually-hidden">{caption}</caption>}
        <thead>
          <tr>
            {columns.map((column) => (
              <th
                key={column.key}
                className={column.className}
                scope="col"
                aria-sort={sort?.key === column.sortKey ? (sort?.direction === "asc" ? "ascending" : "descending") : undefined}
              >
                {header(column)}
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {rows.map((row) => (
            <tr
              key={rowKey(row)}
              className={onRowClick ? "clickable" : undefined}
              onClick={
                onRowClick
                  ? (event) => {
                      // Клик по ссылке или кнопке в строке - это их действие, не открытие строки.
                      if ((event.target as HTMLElement).closest("a, button, input, select, label")) return;
                      onRowClick(row);
                    }
                  : undefined
              }
            >
              {columns.map((column) => (
                <td
                  key={column.key}
                  className={`${column.className || ""} ${column.primary ? "cell-primary" : ""}`.trim() || undefined}
                  data-label={column.primary ? "" : column.title}
                >
                  {column.render(row)}
                </td>
              ))}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

/** Подвал таблицы: сколько записей и переключатель страниц. */
export function Pager({
  total,
  limit,
  offset,
  onChange,
  forms = ["запись", "записи", "записей"],
}: {
  total: number;
  limit: number;
  offset: number;
  onChange: (offset: number) => void;
  forms?: [string, string, string];
}) {
  const pages = Math.max(1, Math.ceil(total / limit));
  const page = Math.floor(offset / limit) + 1;
  const numbers: (number | "…")[] = [];
  for (let index = 1; index <= pages; index += 1) {
    if (index === 1 || index === pages || Math.abs(index - page) <= 1) numbers.push(index);
    else if (numbers[numbers.length - 1] !== "…") numbers.push("…");
  }
  const from = total === 0 ? 0 : offset + 1;
  const to = Math.min(offset + limit, total);
  return (
    <div className="table-footer">
      <span>{total === 0 ? "Нет записей" : `${from}–${to} из ${countLabel(total, forms)}`}</span>
      {pages > 1 && (
        <nav className="pager" aria-label="Страницы">
          <button type="button" aria-label="Предыдущая страница" disabled={page === 1} onClick={() => onChange(offset - limit)}>
            <ChevronLeft size={16} />
          </button>
          {numbers.map((number, index) =>
            number === "…" ? (
              <span key={`gap-${index}`} className="muted">
                …
              </span>
            ) : (
              <button
                key={number}
                type="button"
                aria-current={number === page ? "page" : undefined}
                onClick={() => onChange((number - 1) * limit)}
              >
                {number}
              </button>
            ),
          )}
          <button
            type="button"
            aria-label="Следующая страница"
            disabled={page === pages}
            onClick={() => onChange(offset + limit)}
          >
            <ChevronRight size={16} />
          </button>
        </nav>
      )}
    </div>
  );
}
