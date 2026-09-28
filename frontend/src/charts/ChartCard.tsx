/**
 * Карточка диаграммы: заголовок, переключатель «диаграмма / таблица»
 * и выгрузка в PNG или PDF (п. 3 функциональных требований ТЗ).
 *
 * Табличный вид - равноценная замена диаграмме: в нём те же числа, и его
 * читает экранный диктор.
 *
 * Карточки диаграмм в одном ряду - одной высоты: столбцы короткой диаграммы
 * расходятся по высоте соседней (не дальше двойного шага), а «Нет данных»
 * стоит посередине - без пустого хвоста внизу.
 */
import { Download, Table2, BarChart3 } from "lucide-react";
import { useState } from "react";
import type { ChartData } from "../api/types";
import { formatNumber } from "../lib/format";
import { IconButton } from "../components/ui";
import { BarList } from "./BarList";
import { TrendChart } from "./TrendChart";
import type { ChartItem } from "./types";

export function ChartCard({
  chart,
  kind = "bars",
  onExport,
  onSelect,
  refreshing,
}: {
  chart: ChartData;
  kind?: "bars" | "trend";
  onExport?: (format: "png" | "pdf") => Promise<void> | void;
  onSelect?: (item: ChartItem) => void;
  refreshing?: boolean;
}) {
  const [asTable, setAsTable] = useState(false);
  const [menu, setMenu] = useState(false);
  const [busy, setBusy] = useState(false);
  const items = chart.items || [];
  const total = items.reduce((sum, item) => sum + item.value, 0);

  const exportAs = async (format: "png" | "pdf") => {
    setMenu(false);
    if (!onExport) return;
    setBusy(true);
    try {
      await onExport(format);
    } finally {
      setBusy(false);
    }
  };

  return (
    <section className={`card card--spread chart-card ${refreshing ? "is-refreshing" : ""}`}>
      <div className="card__header">
        <div>
          <h2>{chart.title}</h2>
          <p>
            Всего: {formatNumber(total)} {chart.measure}
          </p>
        </div>
        <div className="row" style={{ position: "relative" }}>
          <IconButton
            icon={asTable ? BarChart3 : Table2}
            label={asTable ? "Показать диаграмму" : "Показать таблицей"}
            onClick={() => setAsTable((value) => !value)}
          />
          {onExport && (
            <>
              <IconButton
                icon={Download}
                label="Скачать диаграмму"
                disabled={busy || items.length === 0}
                expanded={menu}
                onClick={() => setMenu((value) => !value)}
              />
              {menu && (
                <div className="menu" style={{ width: 200 }} onMouseLeave={() => setMenu(false)}>
                  <button type="button" className="menu__item" onClick={() => exportAs("png")}>
                    Картинка PNG
                  </button>
                  <button type="button" className="menu__item" onClick={() => exportAs("pdf")}>
                    Документ PDF
                  </button>
                </div>
              )}
            </>
          )}
        </div>
      </div>
      <div className="card__body">
        {items.length === 0 ? (
          <p className="muted card-empty">Нет данных за выбранный период.</p>
        ) : asTable ? (
          <table className="data-table chart-table">
            <thead>
              <tr>
                <th scope="col">Категория</th>
                <th scope="col" className="col-num">
                  Значение, {chart.measure}
                </th>
                <th scope="col" className="col-num">
                  Доля
                </th>
              </tr>
            </thead>
            <tbody>
              {items.map((item, index) => (
                <tr key={`${item.label}-${index}`}>
                  <td>{item.label}</td>
                  <td className="col-num">{formatNumber(item.value)}</td>
                  <td className="col-num">
                    {total ? `${Math.round((item.value / total) * 1000) / 10}%`.replace(".", ",") : "—"}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        ) : kind === "trend" ? (
          <TrendChart items={items} measure={chart.measure} />
        ) : (
          <BarList items={items} measure={chart.measure} onSelect={onSelect} />
        )}
      </div>
    </section>
  );
}
