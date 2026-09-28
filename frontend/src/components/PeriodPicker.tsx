/**
 * Период отчёта: готовые варианты и свои даты. Пустой период значит «за всё время».
 */
import { Field } from "./ui";
import { toInputDate } from "../lib/format";

export interface Period {
  date_from: string;
  date_to: string;
}

function preset(key: string): Period {
  const today = new Date();
  const end = toInputDate(today);
  const start = new Date(today);
  switch (key) {
    case "30d":
      start.setDate(start.getDate() - 29);
      return { date_from: toInputDate(start), date_to: end };
    case "90d":
      start.setDate(start.getDate() - 89);
      return { date_from: toInputDate(start), date_to: end };
    case "quarter": {
      const quarterStart = new Date(today.getFullYear(), Math.floor(today.getMonth() / 3) * 3, 1);
      return { date_from: toInputDate(quarterStart), date_to: end };
    }
    case "year":
      return { date_from: `${today.getFullYear()}-01-01`, date_to: end };
    case "academic": {
      // Учебный год: с 1 сентября.
      const year = today.getMonth() >= 8 ? today.getFullYear() : today.getFullYear() - 1;
      return { date_from: `${year}-09-01`, date_to: end };
    }
    case "last-year":
      return { date_from: `${today.getFullYear() - 1}-01-01`, date_to: `${today.getFullYear() - 1}-12-31` };
    default:
      return { date_from: "", date_to: "" };
  }
}

const PRESETS = [
  { key: "all", label: "За всё время" },
  { key: "30d", label: "Последние 30 дней" },
  { key: "90d", label: "Последние 90 дней" },
  { key: "quarter", label: "Текущий квартал" },
  { key: "year", label: "С начала года" },
  { key: "academic", label: "Учебный год" },
  { key: "last-year", label: "Прошлый год" },
];

function currentPreset(value: Period): string {
  const match = PRESETS.find((item) => {
    const candidate = preset(item.key);
    return candidate.date_from === value.date_from && candidate.date_to === value.date_to;
  });
  return match ? match.key : "custom";
}

export function PeriodPicker({ value, onChange }: { value: Period; onChange: (value: Period) => void }) {
  const selected = currentPreset(value);
  return (
    <>
      <Field label="Период">
        <select
          className="control"
          value={selected}
          onChange={(event) => {
            if (event.target.value !== "custom") onChange(preset(event.target.value));
          }}
        >
          {PRESETS.map((item) => (
            <option key={item.key} value={item.key}>
              {item.label}
            </option>
          ))}
          <option value="custom">Свои даты</option>
        </select>
      </Field>
      <Field label="С">
        <input
          className="control"
          type="date"
          value={value.date_from}
          max={value.date_to || undefined}
          onChange={(event) => onChange({ ...value, date_from: event.target.value })}
        />
      </Field>
      <Field label="По">
        <input
          className="control"
          type="date"
          value={value.date_to}
          min={value.date_from || undefined}
          onChange={(event) => onChange({ ...value, date_to: event.target.value })}
        />
      </Field>
    </>
  );
}
