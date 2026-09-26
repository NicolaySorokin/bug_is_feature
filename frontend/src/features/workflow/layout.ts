/**
 * Геометрия схемы процесса.
 *
 * Если расположение этапа не сохранено, этапы раскладываются «змейкой»
 * по порядку: слева направо, следующая строка - справа налево. Так
 * соседние этапы стоят рядом, и стрелки почти не пересекаются.
 */

export const NODE_WIDTH = 188;
export const NODE_HEIGHT = 58;
const GAP_X = 52;
const GAP_Y = 60;

export interface Point {
  x: number;
  y: number;
}

export interface LayoutStage {
  id: string;
  sort_order: number;
  layout_x?: number | null;
  layout_y?: number | null;
}

/**
 * Сколько этапов ставить в ряд, чтобы схема целиком поместилась в область
 * заданного размера с наибольшим масштабом - то есть читалась лучше всего.
 */
export function bestPerRow(count: number, width: number, height: number, padding = 32): number {
  let best = 1;
  let bestScale = 0;
  for (let perRow = 1; perRow <= Math.min(Math.max(count, 1), 6); perRow += 1) {
    const rows = Math.ceil(count / perRow);
    const layoutWidth = perRow * NODE_WIDTH + (perRow - 1) * GAP_X;
    const layoutHeight = rows * NODE_HEIGHT + (rows - 1) * GAP_Y;
    const scale = Math.min((width - padding * 2) / layoutWidth, (height - padding * 2) / layoutHeight);
    // При почти равном масштабе предпочитаем более широкую раскладку.
    if (scale > bestScale * 1.02) {
      best = perRow;
      bestScale = scale;
    }
  }
  return best;
}

/** Центры этапов: сохранённые координаты или раскладка по порядку. */
export function computeLayout(stages: LayoutStage[], perRow = 4): Record<string, Point> {
  const ordered = [...stages].sort((left, right) => left.sort_order - right.sort_order);
  const result: Record<string, Point> = {};
  ordered.forEach((stage, index) => {
    if (stage.layout_x !== null && stage.layout_x !== undefined && stage.layout_y !== null && stage.layout_y !== undefined) {
      result[stage.id] = { x: stage.layout_x, y: stage.layout_y };
      return;
    }
    const row = Math.floor(index / perRow);
    const column = index % perRow;
    const position = row % 2 === 0 ? column : perRow - 1 - column;
    result[stage.id] = {
      x: NODE_WIDTH / 2 + position * (NODE_WIDTH + GAP_X),
      y: NODE_HEIGHT / 2 + row * (NODE_HEIGHT + GAP_Y),
    };
  });
  return result;
}

export interface Bounds {
  minX: number;
  minY: number;
  maxX: number;
  maxY: number;
}

export function boundsOf(points: Point[]): Bounds {
  if (points.length === 0) return { minX: 0, minY: 0, maxX: NODE_WIDTH, maxY: NODE_HEIGHT };
  return {
    minX: Math.min(...points.map((point) => point.x)) - NODE_WIDTH / 2,
    minY: Math.min(...points.map((point) => point.y)) - NODE_HEIGHT / 2,
    maxX: Math.max(...points.map((point) => point.x)) + NODE_WIDTH / 2,
    maxY: Math.max(...points.map((point) => point.y)) + NODE_HEIGHT / 2,
  };
}

/**
 * Кривая стрелки между этапами. Точки крепления - середины сторон,
 * обращённых друг к другу. Возвраты назад выгнуты в сторону, чтобы не
 * лечь на прямой переход между теми же этапами.
 */
export function edgePath(from: Point, to: Point, backward: boolean): { d: string; label: Point } {
  const dx = to.x - from.x;
  const dy = to.y - from.y;
  const horizontal = Math.abs(dx) * NODE_HEIGHT >= Math.abs(dy) * NODE_WIDTH;
  let start: Point;
  let end: Point;
  let direction: Point;
  if (horizontal) {
    const sign = Math.sign(dx) || 1;
    start = { x: from.x + (sign * NODE_WIDTH) / 2, y: from.y };
    end = { x: to.x - (sign * NODE_WIDTH) / 2, y: to.y };
    direction = { x: sign, y: 0 };
  } else {
    const sign = Math.sign(dy) || 1;
    start = { x: from.x, y: from.y + (sign * NODE_HEIGHT) / 2 };
    end = { x: to.x, y: to.y - (sign * NODE_HEIGHT) / 2 };
    direction = { x: 0, y: sign };
  }
  const distance = Math.hypot(end.x - start.x, end.y - start.y);
  const reach = Math.max(28, Math.min(distance / 2, 120));
  // Перпендикуляр к направлению: в эту сторону выгибается возврат.
  const normal = { x: -direction.y, y: direction.x };
  const bow = backward ? 46 : 0;
  if (backward) {
    start = { x: start.x + normal.x * 12, y: start.y + normal.y * 12 };
    end = { x: end.x + normal.x * 12, y: end.y + normal.y * 12 };
  }
  const c1 = { x: start.x + direction.x * reach + normal.x * bow, y: start.y + direction.y * reach + normal.y * bow };
  const c2 = { x: end.x - direction.x * reach + normal.x * bow, y: end.y - direction.y * reach + normal.y * bow };
  const label = {
    x: 0.125 * start.x + 0.375 * c1.x + 0.375 * c2.x + 0.125 * end.x,
    y: 0.125 * start.y + 0.375 * c1.y + 0.375 * c2.y + 0.125 * end.y,
  };
  // Между соседними узлами одного ряда подписи мало места: она легла бы
  // на карточки этапов. Поднимаем её над рядом, в промежуток между рядами.
  if (horizontal && !backward) label.y = Math.min(from.y, to.y) - NODE_HEIGHT / 2;
  return { d: `M${start.x},${start.y} C${c1.x},${c1.y} ${c2.x},${c2.y} ${end.x},${end.y}`, label };
}

/** Обрезка длинного названия этапа под ширину карточки. */
export function clip(text: string, max = 24): string {
  return text.length > max ? `${text.slice(0, max - 1).trimEnd()}…` : text;
}
