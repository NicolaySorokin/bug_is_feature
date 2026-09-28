/**
 * Общие элементы взаимодействия: статус, этап со следующим действием и срок этапа. Это три
 * независимые вещи, цвет относится только к сроку.
 */
import { Clock } from "lucide-react";
import { Link } from "react-router-dom";
import { useLabel } from "../../api/queries";
import type { ContractBrief, InteractionOutcome, InteractionStatus, StageSla, UniversityBrief } from "../../api/types";
import { StatusBadge } from "../../components/ui";
import { countLabel, DAYS, formatDate, formatNumber } from "../../lib/format";
import { CONTRACT_STATUS_TONE, INTERACTION_TONE, OUTCOME_TONE } from "../../lib/labels";

export function InteractionStatusBadge({ status }: { status: InteractionStatus }) {
  const label = useLabel();
  return <StatusBadge tone={INTERACTION_TONE[status]}>{label("interaction_status", status)}</StatusBadge>;
}

export function OutcomeBadge({ outcome }: { outcome?: InteractionOutcome | null }) {
  const label = useLabel();
  if (!outcome) return null;
  return <StatusBadge tone={OUTCOME_TONE[outcome]}>{label("interaction_outcome", outcome)}</StatusBadge>;
}

/** Статус взаимодействия, у закрытого ещё и результат. */
export function StatusCell({ status, outcome }: { status: InteractionStatus; outcome?: InteractionOutcome | null }) {
  return (
    <span className="row" style={{ gap: 6, flexWrap: "wrap" }}>
      <InteractionStatusBadge status={status} />
      {(status === "completed" || status === "cancelled") && <OutcomeBadge outcome={outcome} />}
    </span>
  );
}

/** Краткое название вуза, полное в подсказке. */
export function UniversityName({ university, link = true }: { university?: UniversityBrief | null; link?: boolean }) {
  if (!university) return <span className="muted">—</span>;
  const text = university.short_name || university.display_name || university.name;
  if (!link) return <span title={university.name}>{text}</span>;
  return (
    <Link to={`/universities/${university.id}`} title={university.name} onClick={(event) => event.stopPropagation()}>
      {text}
    </Link>
  );
}

/** Этап и следующее действие, без цвета срока. */
export function StageCell({
  stageName,
  nextActions,
  status,
}: {
  stageName?: string | null;
  nextActions?: string[] | null;
  status: InteractionStatus;
}) {
  if (status === "draft") return <span className="muted">Процесс не запущен</span>;
  if (!stageName) return <span className="muted">—</span>;
  const next = (nextActions || [])[0];
  const open = status === "in_progress" || status === "blocked";
  return (
    <div className="cell-title">
      <span>{stageName}</span>
      {open && next && <small>Дальше: {next}</small>}
    </div>
  );
}

/** После «из»: «из 21 дня», «из 14 дней». */
const OF_DAYS: [string, string, string] = ["дня", "дней", "дней"];

/** Фактические и нормативные дни этапа: «16 из 21 дня». */
export function slaUsage(sla: StageSla): string {
  return `${formatNumber(sla.days_on_stage)} из ${countLabel(sla.sla_days, OF_DAYS)}`;
}

/** «Осталось 5 дней», «последний день» или «просрочено на 7 дней». */
export function slaRemainder(sla: StageSla): string {
  if (sla.days_left < 0) return `просрочено на ${countLabel(-sla.days_left, DAYS)}`;
  if (sla.days_left === 0) return "последний день";
  return `осталось ${countLabel(sla.days_left, DAYS)}`;
}

/** Срок считается и у заблокированного процесса: блокировка не прячет просрочку. */
function tracksSla(status: InteractionStatus): boolean {
  return status === "in_progress" || status === "blocked";
}

/** Срок этапа в таблицах: дни из нормы и остаток. */
export function SlaChip({ sla, status }: { sla?: StageSla | null; status: InteractionStatus }) {
  if (!tracksSla(status)) return <span className="muted">—</span>;
  if (!sla) return <span className="muted">Норма не задана</span>;
  return (
    <div className="cell-title">
      <span className={`sla-chip sla-chip--${sla.state}`}>
        <Clock size={12} aria-hidden="true" />
        {slaUsage(sla)}
      </span>
      <small className={sla.state === "overdue" ? "field__error" : undefined}>{slaRemainder(sla)}</small>
    </div>
  );
}

/** Полоса «Срок этапа»: зелёная в норме, жёлтая от 75% срока, красная при просрочке. */
export function SlaMeter({ sla }: { sla: StageSla }) {
  const cls = sla.state === "overdue" ? "meter--bad" : sla.state === "warning" ? "meter--warn" : "meter--ok";
  return (
    <div
      className={`meter ${cls}`}
      role="meter"
      aria-label="Срок этапа"
      aria-valuemin={0}
      aria-valuemax={sla.sla_days}
      aria-valuenow={Math.min(sla.days_on_stage, sla.sla_days)}
      aria-valuetext={`${slaUsage(sla)}, ${slaRemainder(sla)}`}
    >
      <div className="meter__fill" style={{ width: `${Math.min(100, Math.max(4, sla.used_percent))}%` }} />
    </div>
  );
}

/** Блок «Срок этапа» для «Следующих шагов» и обзора: подписанная полоса, дни и остаток. */
export function SlaBlock({ sla, status }: { sla?: StageSla | null; status: InteractionStatus }) {
  if (!tracksSla(status))
    return <span className="muted">{status === "draft" ? "—" : "Не отслеживается: взаимодействие закрыто"}</span>;
  if (!sla) return <span className="muted">Норма не задана</span>;
  return (
    <div className="sla-block">
      <SlaMeter sla={sla} />
      <span className="sla-block__text">
        <strong>{slaUsage(sla)}</strong>
        <span className={sla.state === "overdue" ? "field__error" : "muted"}>{slaRemainder(sla)}</span>
      </span>
    </div>
  );
}

/** Договор, необязательный блок взаимодействия. */
export function ContractCell({ contract }: { contract?: ContractBrief | null }) {
  const label = useLabel();
  if (!contract) return <span className="muted">Нет договора</span>;
  const left = contract.days_left;
  return (
    <div className="cell-title">
      <span className="row" style={{ gap: 6 }}>
        <strong className="nowrap">{contract.number}</strong>
        <StatusBadge tone={CONTRACT_STATUS_TONE[contract.status]}>{label("contract_status", contract.status)}</StatusBadge>
      </span>
      {contract.valid_to && (
        <small
          className={
            contract.status === "active" && left !== null && left !== undefined && left <= 60 ? "field__error" : undefined
          }
        >
          до {formatDate(contract.valid_to)}
          {contract.status === "active" && left !== null && left !== undefined && left <= 60
            ? left < 0
              ? " · истёк"
              : ` · осталось ${countLabel(left, DAYS)}`
            : ""}
        </small>
      )}
    </div>
  );
}

/** Название взаимодействия: своё или «Взаимодействие с <вуз>». */
export function interactionTitle(item: { title?: string | null; university?: UniversityBrief | null }): string {
  if (item.title) return item.title;
  const university = item.university;
  return university ? `Взаимодействие с ${university.short_name || university.name}` : "Взаимодействие";
}
