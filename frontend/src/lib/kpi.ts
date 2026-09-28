/**
 * Сколько колонок в ряду показателей, чтобы ряды были поровну, а не «5 + 1».
 *
 * fit: сколько карточек помещается в ряд. Сначала наименьшее число рядов, затем карточки поровну:
 * шесть при fit = 5 дают 3 + 3, пять при fit = 4 дают 3 + 2.
 */
export function kpiColumns(count: number, fit: number): number {
  if (count <= 0) return 1;
  const rows = Math.ceil(count / Math.max(1, Math.min(fit, count)));
  return Math.ceil(count / rows);
}
