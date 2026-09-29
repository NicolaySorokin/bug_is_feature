/** Подписи к уведомлениям «Требует внимания». */
import type { Alert } from "../api/types";
import { countLabel, DAYS } from "./format";

// У этих видов days значит «сколько дней ситуация не меняется», а в тексте повода числа нет.
// У просрочки этапа дни уже в тексте, у сроков договора и лицензии days это остаток срока.
const AGE_KINDS = new Set<Alert["kind"]>([
  "process_blocked",
  "process_not_started",
  "no_manager",
  "no_documents",
  "implementation_not_started",
  "integration_failed",
]);

/** Сколько ситуация остаётся без изменений: «без изменений 5 дней». */
export function alertAge(alert: Pick<Alert, "kind" | "days">): string | null {
  const days = alert.days;
  if (days === null || days === undefined || days < 0 || !AGE_KINDS.has(alert.kind)) return null;
  return days === 0 ? "без изменений меньше дня" : `без изменений ${countLabel(days, DAYS)}`;
}

/** Строка под поводом: вуз, договор, ответственный и срок. */
export function alertMeta(alert: Alert): string {
  return [alert.university_name, alert.contract_number, alert.manager_name, alertAge(alert)].filter(Boolean).join(" · ");
}
