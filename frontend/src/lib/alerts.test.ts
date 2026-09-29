import { describe, expect, it } from "vitest";
import type { Alert } from "../api/types";
import { alertAge, alertMeta } from "./alerts";

function alert(extra: Partial<Alert>): Alert {
  return {
    kind: "process_blocked",
    kind_label: "Процесс заблокирован",
    severity: "critical",
    severity_label: "Критично",
    message: "Заблокировано",
    key: "k",
    ...extra,
  } as Alert;
}

describe("alertAge", () => {
  it("сколько ситуация не меняется", () => {
    expect(alertAge(alert({ kind: "no_manager", days: 5 }))).toBe("без изменений 5 дней");
    expect(alertAge(alert({ kind: "process_blocked", days: 1 }))).toBe("без изменений 1 день");
    expect(alertAge(alert({ kind: "no_documents", days: 0 }))).toBe("без изменений меньше дня");
  });

  it("не повторяет дни из текста и не путает с остатком срока", () => {
    expect(alertAge(alert({ kind: "stage_stale", days: 30 }))).toBeNull();
    expect(alertAge(alert({ kind: "contract_expiring", days: 10 }))).toBeNull();
    expect(alertAge(alert({ kind: "license_expiring", days: -5 }))).toBeNull();
    expect(alertAge(alert({ kind: "no_manager", days: null }))).toBeNull();
  });
});

describe("alertMeta", () => {
  it("вуз, договор, ответственный и срок одной строкой", () => {
    const text = alertMeta(alert({ university_name: "МТУСИ", contract_number: "ДГ-1", manager_name: "Петров П. А.", days: 3 }));
    expect(text).toBe("МТУСИ · ДГ-1 · Петров П. А. · без изменений 3 дня");
  });
});
