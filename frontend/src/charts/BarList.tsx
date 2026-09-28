/**
 * Горизонтальные столбцы одного цвета. Значение подписано у конца, подсказка добавляет долю от общего.
 */
import { useState, type CSSProperties } from "react";
import type { ChartItem } from "./types";
import { formatNumber } from "../lib/format";

export function BarList({
  items,
  measure,
  onSelect,
}: {
  items: ChartItem[];
  measure: string;
  onSelect?: (item: ChartItem) => void;
}) {
  const [hovered, setHovered] = useState<number | null>(null);
  const max = Math.max(1, ...items.map((item) => item.value));
  const total = items.reduce((sum, item) => sum + item.value, 0);

  return (
    <ul className="bars" aria-label={`Значения, ${measure}`} style={{ "--bars": items.length } as CSSProperties}>
      {items.map((item, index) => {
        const share = total ? Math.round((item.value / total) * 1000) / 10 : 0;
        const width = `${Math.max((item.value / max) * 100, item.value ? 1.5 : 0)}%`;
        return (
          <li
            key={`${item.label}-${index}`}
            className="bar-row"
            tabIndex={0}
            aria-label={`${item.label}: ${formatNumber(item.value)} ${measure}, ${String(share).replace(".", ",")}%`}
            onPointerEnter={() => setHovered(index)}
            onPointerLeave={() => setHovered(null)}
            onFocus={() => setHovered(index)}
            onBlur={() => setHovered(null)}
            onClick={onSelect ? () => onSelect(item) : undefined}
            onKeyDown={
              onSelect
                ? (event) => {
                    if (event.key === "Enter") onSelect(item);
                  }
                : undefined
            }
            style={{ cursor: onSelect ? "pointer" : undefined, position: "relative" }}
          >
            <span className="bar-row__label">{item.label}</span>
            <span className="bar-row__value">{formatNumber(item.value)}</span>
            <span className="bar-row__track" aria-hidden="true">
              <span className="bar-row__bar" style={{ width }} />
            </span>
            {hovered === index && (
              <span className="chart-tooltip" style={{ left: "70%", top: 0 }} role="presentation">
                <strong>{formatNumber(item.value)}</strong>
                {measure} · {String(share).replace(".", ",")}% от всех
              </span>
            )}
          </li>
        );
      })}
    </ul>
  );
}
