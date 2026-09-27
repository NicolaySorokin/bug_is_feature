/**
 * Сколько колонок в ряду показателей: ряды поровну, а не «5 + 1».
 *
 * fit - сколько карточек помещается в ряд по ширине. Сначала находим
 * наименьшее число рядов, затем раскладываем карточки по ним поровну:
 * шесть при fit = 5 - это 3 + 3, пять при fit = 4 - 3 + 2.
 */
export function kpiColumns(count: number, fit: number): number {
  if (count <= 0) return 1;
  const rows = Math.ceil(count / Math.max(1, Math.min(fit, count)));
  return Math.ceil(count / rows);
}
