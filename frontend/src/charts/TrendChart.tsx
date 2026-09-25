/**
 * Динамика по месяцам: линия с лёгкой заливкой.
 *
 * Вертикальная линия-прицел следует за указателем и привязывается к
 * ближайшему месяцу; подсказка показывает значение. Стрелки клавиатуры
 * переключают месяц, если график в фокусе.
 */
import { useLayoutEffect, useMemo, useRef, useState } from "react";
import type { ChartItem } from "./types";
import { formatNumber } from "../lib/format";

const HEIGHT = 240;
const PAD = { top: 16, right: 16, bottom: 28, left: 40 };

function niceMax(value: number): number {
  if (value <= 0) return 1;
  const power = 10 ** Math.floor(Math.log10(value));
  const step = [1, 2, 2.5, 5, 10].find((candidate) => candidate * power >= value / 4) || 10;
  return Math.ceil(value / (step * power)) * step * power;
}

export function TrendChart({ items, measure }: { items: ChartItem[]; measure: string }) {
  const [active, setActive] = useState<number | null>(null);
  const svgRef = useRef<SVGSVGElement>(null);
  const boxRef = useRef<HTMLDivElement>(null);
  // Рисуем в реальную ширину области: подписи остаются 11 px при любой ширине.
  const [WIDTH, setWidth] = useState(640);
  useLayoutEffect(() => {
    const element = boxRef.current;
    if (!element) return;
    const observer = new ResizeObserver(([entry]) => setWidth(Math.max(280, Math.round(entry.contentRect.width))));
    observer.observe(element);
    return () => observer.disconnect();
  }, []);

  const geometry = useMemo(() => {
    const max = niceMax(Math.max(...items.map((item) => item.value), 0));
    const innerWidth = WIDTH - PAD.left - PAD.right;
    const innerHeight = HEIGHT - PAD.top - PAD.bottom;
    const step = items.length > 1 ? innerWidth / (items.length - 1) : 0;
    const points = items.map((item, index) => ({
      x: PAD.left + (items.length > 1 ? index * step : innerWidth / 2),
      y: PAD.top + innerHeight - (item.value / max) * innerHeight,
    }));
    const ticks = [0, 0.25, 0.5, 0.75, 1].map((part) => ({
      value: Math.round(max * part),
      y: PAD.top + innerHeight - part * innerHeight,
    }));
    const line = points.map((point, index) => `${index ? "L" : "M"}${point.x},${point.y}`).join(" ");
    const baseline = PAD.top + innerHeight;
    const area = points.length ? `${line} L${points[points.length - 1].x},${baseline} L${points[0].x},${baseline} Z` : "";
    // Подписи оси X не должны налезать друг на друга: на подпись нужно ~70 px.
    const every = Math.max(1, Math.ceil(items.length / Math.max(2, Math.floor(innerWidth / 70))));
    return { points, ticks, line, area, baseline, every };
  }, [items, WIDTH]);

  const pick = (clientX: number) => {
    const svg = svgRef.current;
    if (!svg || geometry.points.length === 0) return;
    const rect = svg.getBoundingClientRect();
    const x = ((clientX - rect.left) / rect.width) * WIDTH;
    let nearest = 0;
    geometry.points.forEach((point, index) => {
      if (Math.abs(point.x - x) < Math.abs(geometry.points[nearest].x - x)) nearest = index;
    });
    setActive(nearest);
  };

  const current = active !== null ? items[active] : null;
  const currentPoint = active !== null ? geometry.points[active] : null;

  return (
    <div className="trend chart" style={{ position: "relative" }} ref={boxRef}>
      <svg
        ref={svgRef}
        width={WIDTH}
        height={HEIGHT}
        viewBox={`0 0 ${WIDTH} ${HEIGHT}`}
        role="img"
        aria-label={`Динамика, ${measure}: ${items.map((item) => `${item.label} - ${item.value}`).join(", ")}`}
        tabIndex={0}
        onPointerMove={(event) => pick(event.clientX)}
        onPointerLeave={() => setActive(null)}
        onFocus={() => setActive(items.length - 1)}
        onBlur={() => setActive(null)}
        onKeyDown={(event) => {
          if (event.key === "ArrowLeft") setActive((index) => Math.max(0, (index ?? items.length) - 1));
          if (event.key === "ArrowRight") setActive((index) => Math.min(items.length - 1, (index ?? -1) + 1));
        }}
      >
        {geometry.ticks.map((tick) => (
          <g key={tick.value}>
            <line x1={PAD.left} x2={WIDTH - PAD.right} y1={tick.y} y2={tick.y} stroke="var(--chart-grid)" strokeWidth={1} />
            <text x={PAD.left - 8} y={tick.y + 4} textAnchor="end" className="num">
              {formatNumber(tick.value)}
            </text>
          </g>
        ))}
        <line
          x1={PAD.left}
          x2={WIDTH - PAD.right}
          y1={geometry.baseline}
          y2={geometry.baseline}
          stroke="var(--chart-axis)"
          strokeWidth={1}
        />
        {items.map((item, index) =>
          index % geometry.every === 0 || index === items.length - 1 ? (
            <text key={item.label} x={geometry.points[index].x} y={HEIGHT - 8} textAnchor="middle">
              {item.label}
            </text>
          ) : null,
        )}
        <path d={geometry.area} fill="var(--chart-wash)" />
        <path
          d={geometry.line}
          fill="none"
          stroke="var(--chart-1)"
          strokeWidth={2}
          strokeLinejoin="round"
          strokeLinecap="round"
        />
        {/* Последняя точка подписана: это значение читают первым. */}
        {geometry.points.length > 0 && active === null && (
          <>
            <circle
              cx={geometry.points[geometry.points.length - 1].x}
              cy={geometry.points[geometry.points.length - 1].y}
              r={4.5}
              fill="var(--chart-1)"
              stroke="#fff"
              strokeWidth={2}
            />
            <text
              x={geometry.points[geometry.points.length - 1].x - 8}
              y={geometry.points[geometry.points.length - 1].y - 10}
              textAnchor="end"
              style={{ fill: "var(--text)", fontWeight: 700 }}
            >
              {formatNumber(items[items.length - 1].value)}
            </text>
          </>
        )}
        {currentPoint && (
          <>
            <line
              x1={currentPoint.x}
              x2={currentPoint.x}
              y1={PAD.top}
              y2={geometry.baseline}
              stroke="var(--text-muted)"
              strokeWidth={1}
            />
            <circle cx={currentPoint.x} cy={currentPoint.y} r={5} fill="var(--chart-1)" stroke="#fff" strokeWidth={2} />
          </>
        )}
      </svg>
      {current && currentPoint && (
        <div
          className="chart-tooltip"
          style={{ left: `${(currentPoint.x / WIDTH) * 100}%`, top: `${(currentPoint.y / HEIGHT) * 100}%` }}
        >
          <strong>{formatNumber(current.value)}</strong>
          <span className="key" style={{ background: "var(--chart-1)" }} />
          {measure} · {current.label}
        </div>
      )}
    </div>
  );
}
