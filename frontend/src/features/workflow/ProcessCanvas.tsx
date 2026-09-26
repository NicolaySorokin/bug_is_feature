/**
 * Схема рабочего процесса (п. 4 функциональных требований ТЗ).
 *
 * Этапы - карточки, переходы - стрелки. Цвет карточки показывает
 * состояние этапа, подпись дублирует его словами. Схему можно двигать
 * мышью или пальцем, масштабировать кнопками, Ctrl + колесом или щипком.
 * Руководитель и администратор могут перетаскивать этапы и сохранить
 * расположение - оно станет общим для всех договоров этой версии.
 */
import { Maximize2, Minus, Plus } from "lucide-react";
import { useCallback, useEffect, useLayoutEffect, useMemo, useRef, useState } from "react";
import type { StageState } from "../../api/types";
import { bestPerRow, boundsOf, clip, computeLayout, edgePath, NODE_HEIGHT, NODE_WIDTH, type Point } from "./layout";

export interface CanvasStage {
  id: string;
  name: string;
  sort_order: number;
  layout_x?: number | null;
  layout_y?: number | null;
  sla_days?: number | null;
  is_optional?: boolean;
  is_final?: boolean;
}

export interface CanvasTransition {
  id: string;
  from_stage_id: string;
  to_stage_id: string;
  is_backward: boolean;
  name?: string | null;
}

const STATE_TEXT: Record<StageState, string> = {
  not_started: "не начат",
  active: "текущий этап",
  completed: "пройден",
  skipped: "пропущен",
  blocked: "заблокирован",
};

interface View {
  x: number;
  y: number;
  k: number;
}

const MIN_ZOOM = 0.3;
const MAX_ZOOM = 1.8;

function clampZoom(value: number): number {
  return Math.min(MAX_ZOOM, Math.max(MIN_ZOOM, value));
}

export function ProcessCanvas({
  stages,
  transitions,
  states,
  selectedId,
  onSelect,
  availableTransitionIds,
  editable = false,
  onPositionsChange,
  resetKey,
  height,
}: {
  stages: CanvasStage[];
  transitions: CanvasTransition[];
  states?: Record<string, StageState>;
  selectedId?: string | null;
  onSelect?: (stageId: string) => void;
  availableTransitionIds?: Set<string>;
  /** Этапы можно перетаскивать. */
  editable?: boolean;
  /** Новое расположение после перетаскивания (для кнопки «Сохранить»). */
  onPositionsChange?: (positions: Record<string, Point>) => void;
  /** Смена ключа сбрасывает несохранённое расположение. */
  resetKey?: string | number;
  height?: number;
}) {
  const containerRef = useRef<HTMLDivElement>(null);
  const [view, setView] = useState<View>({ x: 0, y: 0, k: 1 });
  const [size, setSize] = useState({ width: 0, height: height || 560 });
  // Число этапов в ряду подбирается под размер области - для схем без
  // сохранённого расположения.
  const perRow = useMemo(
    () => bestPerRow(stages.length, size.width || 800, size.height),
    [stages.length, size.width, size.height],
  );
  const initial = useMemo(() => computeLayout(stages, perRow), [stages, perRow]);
  const [positions, setPositions] = useState<Record<string, Point>>(initial);
  const positionsRef = useRef(positions);
  positionsRef.current = positions;
  const [panning, setPanning] = useState(false);
  const pointers = useRef(new Map<number, Point>());
  const gesture = useRef<
    | { kind: "pan"; start: Point; view: View }
    | { kind: "node"; id: string; start: Point; origin: Point; moved: boolean }
    | { kind: "pinch"; distance: number; view: View; center: Point }
    | null
  >(null);

  const fitTo = useCallback(
    (points: Point[]) => {
      if (!size.width) return;
      const bounds = boundsOf(points);
      const padding = 32;
      const k = clampZoom(
        Math.min(
          (size.width - padding * 2) / Math.max(bounds.maxX - bounds.minX, 1),
          (size.height - padding * 2) / Math.max(bounds.maxY - bounds.minY, 1),
          1.1,
        ),
      );
      setView({
        k,
        x: (size.width - (bounds.maxX - bounds.minX) * k) / 2 - bounds.minX * k,
        y: (size.height - (bounds.maxY - bounds.minY) * k) / 2 - bounds.minY * k,
      });
    },
    [size.width, size.height],
  );
  const fit = () => fitTo(Object.values(positionsRef.current));

  // Новая схема, другой размер области или сброс - раскладываем и вписываем заново.
  useEffect(() => {
    setPositions(initial);
    fitTo(Object.values(initial));
  }, [initial, resetKey, fitTo]);

  useLayoutEffect(() => {
    const element = containerRef.current;
    if (!element) return;
    const observer = new ResizeObserver(([entry]) => {
      setSize({ width: Math.round(entry.contentRect.width), height: Math.round(entry.contentRect.height) });
    });
    observer.observe(element);
    return () => observer.disconnect();
  }, []);

  const zoomAt = (factor: number, center: Point = { x: size.width / 2, y: size.height / 2 }) => {
    setView((current) => {
      const k = clampZoom(current.k * factor);
      const ratio = k / current.k;
      return { k, x: center.x - (center.x - current.x) * ratio, y: center.y - (center.y - current.y) * ratio };
    });
  };

  const local = (event: { clientX: number; clientY: number }): Point => {
    const rect = containerRef.current!.getBoundingClientRect();
    return { x: event.clientX - rect.left, y: event.clientY - rect.top };
  };

  const onPointerDown = (event: React.PointerEvent<SVGSVGElement>) => {
    const point = local(event);
    pointers.current.set(event.pointerId, point);
    (event.currentTarget as Element).setPointerCapture(event.pointerId);
    if (pointers.current.size === 2) {
      const [a, b] = Array.from(pointers.current.values());
      gesture.current = {
        kind: "pinch",
        distance: Math.hypot(a.x - b.x, a.y - b.y),
        view,
        center: { x: (a.x + b.x) / 2, y: (a.y + b.y) / 2 },
      };
      return;
    }
    const nodeId = (event.target as Element).closest<SVGGElement>("[data-stage]")?.dataset.stage;
    if (nodeId) {
      gesture.current = { kind: "node", id: nodeId, start: point, origin: positions[nodeId], moved: false };
    } else {
      gesture.current = { kind: "pan", start: point, view };
      setPanning(true);
    }
  };

  const onPointerMove = (event: React.PointerEvent<SVGSVGElement>) => {
    if (!pointers.current.has(event.pointerId)) return;
    const point = local(event);
    pointers.current.set(event.pointerId, point);
    const current = gesture.current;
    if (!current) return;
    if (current.kind === "pinch" && pointers.current.size >= 2) {
      const [a, b] = Array.from(pointers.current.values());
      const distance = Math.hypot(a.x - b.x, a.y - b.y);
      const k = clampZoom(current.view.k * (distance / current.distance));
      const ratio = k / current.view.k;
      setView({
        k,
        x: current.center.x - (current.center.x - current.view.x) * ratio,
        y: current.center.y - (current.center.y - current.view.y) * ratio,
      });
    } else if (current.kind === "pan") {
      setView({
        ...current.view,
        x: current.view.x + point.x - current.start.x,
        y: current.view.y + point.y - current.start.y,
      });
    } else if (current.kind === "node") {
      const dx = (point.x - current.start.x) / view.k;
      const dy = (point.y - current.start.y) / view.k;
      if (!current.moved && Math.hypot(dx, dy) < 4) return;
      current.moved = true;
      if (!editable) return;
      setPositions((all) => ({
        ...all,
        [current.id]: { x: Math.round(current.origin.x + dx), y: Math.round(current.origin.y + dy) },
      }));
    }
  };

  const onPointerUp = (event: React.PointerEvent<SVGSVGElement>) => {
    pointers.current.delete(event.pointerId);
    const current = gesture.current;
    if (current?.kind === "node") {
      if (!current.moved) onSelect?.(current.id);
      else if (editable) onPositionsChange?.(positionsRef.current);
    }
    if (pointers.current.size === 0) {
      gesture.current = null;
      setPanning(false);
    }
  };

  const onWheel = (event: React.WheelEvent<SVGSVGElement>) => {
    // Колесо без Ctrl прокручивает страницу; с Ctrl (и щипок на тачпаде) - масштаб.
    if (!event.ctrlKey && !event.metaKey) return;
    event.preventDefault();
    zoomAt(event.deltaY < 0 ? 1.12 : 1 / 1.12, local(event));
  };

  // preventDefault в onWheel React не срабатывает у пассивного слушателя.
  useEffect(() => {
    const element = containerRef.current;
    if (!element) return;
    const stop = (event: WheelEvent) => {
      if (event.ctrlKey || event.metaKey) event.preventDefault();
    };
    element.addEventListener("wheel", stop, { passive: false });
    return () => element.removeEventListener("wheel", stop);
  }, []);

  const byId = useMemo(() => Object.fromEntries(stages.map((stage) => [stage.id, stage])), [stages]);
  const ordered = useMemo(() => [...stages].sort((left, right) => left.sort_order - right.sort_order), [stages]);
  const numbers = useMemo(() => Object.fromEntries(ordered.map((stage, index) => [stage.id, index + 1])), [ordered]);

  const edgeClass = (transition: CanvasTransition) => {
    const classes = ["edge"];
    if (transition.is_backward) classes.push("edge--backward");
    if (availableTransitionIds?.has(transition.id)) classes.push("edge--available");
    else if (
      !transition.is_backward &&
      states?.[transition.from_stage_id] === "completed" &&
      states?.[transition.to_stage_id] !== "not_started"
    ) {
      classes.push("edge--passed");
    }
    return classes.join(" ");
  };

  return (
    <div className="process-canvas" style={height ? { height } : undefined}>
      <div className="process-canvas__viewport" ref={containerRef}>
        <svg
          className={panning ? "is-panning" : undefined}
          onPointerDown={onPointerDown}
          onPointerMove={onPointerMove}
          onPointerUp={onPointerUp}
          onPointerCancel={onPointerUp}
          onWheel={onWheel}
          role="group"
          aria-label="Схема рабочего процесса"
        >
          <defs>
            <marker id="arrow" viewBox="0 0 10 10" refX="9" refY="5" markerWidth="7" markerHeight="7" orient="auto-start-reverse">
              <path d="M0,0 L10,5 L0,10 z" fill="#a2a9b8" />
            </marker>
            <marker
              id="arrow-active"
              viewBox="0 0 10 10"
              refX="9"
              refY="5"
              markerWidth="7"
              markerHeight="7"
              orient="auto-start-reverse"
            >
              <path d="M0,0 L10,5 L0,10 z" fill="#7700ff" />
            </marker>
            <marker
              id="arrow-passed"
              viewBox="0 0 10 10"
              refX="9"
              refY="5"
              markerWidth="7"
              markerHeight="7"
              orient="auto-start-reverse"
            >
              <path d="M0,0 L10,5 L0,10 z" fill="#5ac180" />
            </marker>
          </defs>
          <g transform={`translate(${view.x},${view.y}) scale(${view.k})`}>
            {transitions.map((transition) => {
              const from = positions[transition.from_stage_id];
              const to = positions[transition.to_stage_id];
              if (!from || !to) return null;
              const { d } = edgePath(from, to, transition.is_backward);
              const className = edgeClass(transition);
              const marker = className.includes("available")
                ? "url(#arrow-active)"
                : className.includes("passed")
                  ? "url(#arrow-passed)"
                  : "url(#arrow)";
              return (
                <g key={transition.id}>
                  <path className={className} d={d} markerEnd={marker}>
                    <title>
                      {byId[transition.from_stage_id]?.name} → {byId[transition.to_stage_id]?.name}
                      {transition.name ? ` (${transition.name})` : ""}
                    </title>
                  </path>
                </g>
              );
            })}
            {ordered.map((stage) => {
              const point = positions[stage.id];
              if (!point) return null;
              const state = states?.[stage.id];
              const classes = ["node"];
              if (state && state !== "not_started") classes.push(`node--${state}`);
              if (selectedId === stage.id) classes.push("node--selected");
              const meta = [
                `№ ${numbers[stage.id]}`,
                state ? STATE_TEXT[state] : stage.sla_days ? `норма ${stage.sla_days} дн.` : null,
                stage.is_optional ? "необязательный" : null,
                stage.is_final ? "финиш" : null,
              ]
                .filter(Boolean)
                .join(" · ");
              return (
                <g
                  key={stage.id}
                  className={classes.join(" ")}
                  data-stage={stage.id}
                  transform={`translate(${point.x - NODE_WIDTH / 2},${point.y - NODE_HEIGHT / 2})`}
                  tabIndex={0}
                  role="button"
                  aria-label={`Этап ${numbers[stage.id]}: ${stage.name}${state ? `, ${STATE_TEXT[state]}` : ""}`}
                  aria-pressed={selectedId === stage.id}
                  onKeyDown={(event) => {
                    if (event.key === "Enter" || event.key === " ") {
                      event.preventDefault();
                      onSelect?.(stage.id);
                    }
                  }}
                  style={{ cursor: editable ? "move" : "pointer" }}
                >
                  <title>{stage.name}</title>
                  <rect className="node__box" width={NODE_WIDTH} height={NODE_HEIGHT} rx={12} />
                  <text className="node__title" x={12} y={24}>
                    {clip(stage.name)}
                  </text>
                  <text className="node__meta" x={12} y={42}>
                    {meta}
                  </text>
                </g>
              );
            })}
            {transitions.map((transition) => {
              const from = positions[transition.from_stage_id];
              const to = positions[transition.to_stage_id];
              if (!from || !to || !transition.name || !availableTransitionIds?.has(transition.id)) return null;
              const { label } = edgePath(from, to, transition.is_backward);
              return (
                <text key={`label-${transition.id}`} className="edge-label" x={label.x} y={label.y - 6} textAnchor="middle">
                  {clip(transition.name, 22)}
                </text>
              );
            })}
          </g>
        </svg>
      </div>
      <div className="process-canvas__bar">
        {states ? (
          <div className="process-canvas__legend" aria-hidden="true">
            <span>
              <i style={{ borderColor: "#7700ff", background: "#f8f2ff" }} /> текущий
            </span>
            <span>
              <i style={{ borderColor: "#5ac180", background: "#f2faf5" }} /> пройден
            </span>
            <span>
              <i style={{ borderColor: "#d91528", background: "#fdf3f4" }} /> заблокирован
            </span>
            <span>
              <i style={{ borderColor: "#a2a9b8", borderStyle: "dashed" }} /> пропущен
            </span>
            <span>
              <i style={{ borderColor: "#c5cad6" }} /> впереди
            </span>
            <span>
              <i style={{ borderColor: "#ff4f12" }} /> выбран
            </span>
          </div>
        ) : (
          <span className="muted" style={{ fontSize: 12 }}>
            Перетаскивайте схему мышью; Ctrl + колесо - масштаб
          </span>
        )}
        <div className="process-canvas__tools">
          <button type="button" className="icon-btn" aria-label="Увеличить" title="Увеличить" onClick={() => zoomAt(1.2)}>
            <Plus size={16} />
          </button>
          <button type="button" className="icon-btn" aria-label="Уменьшить" title="Уменьшить" onClick={() => zoomAt(1 / 1.2)}>
            <Minus size={16} />
          </button>
          <button type="button" className="icon-btn" aria-label="Вписать схему" title="Вписать схему" onClick={fit}>
            <Maximize2 size={16} />
          </button>
        </div>
      </div>
    </div>
  );
}
