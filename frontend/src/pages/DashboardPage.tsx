/**
 * Главная страница - своя для каждой роли.
 *
 * КАМ видит свои договоры: что сделать дальше, где процесс стоит дольше
 * нормы, какие проблемы. Руководитель - картину по всем вузам и нагрузку
 * ответственных. Администратор дополнительно - пользователей, обмен с
 * LMS и сайтом, последние загрузки справочников.
 */
import { useQuery } from "@tanstack/react-query";
import {
  AlertTriangle,
  ArrowRight,
  Building2,
  CheckCircle2,
  Clock,
  FileText,
  Hourglass,
  Lock,
  PlayCircle,
  Plus,
  Users,
} from "lucide-react";
import { useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import { exportReportChart, getDashboard } from "../api/endpoints";
import { useDownload } from "../api/mutations";
import { keys, useLabel } from "../api/queries";
import type { Alert, Dashboard, NextAction } from "../api/types";
import { useSession } from "../auth/session";
import { ChartCard } from "../charts/ChartCard";
import { Button, Card, EmptyState, ErrorState, Kpi, Loading, PageHeader, StatusBadge } from "../components/ui";
import { countLabel, DAYS, formatDateTime, formatLongDate, formatNumber } from "../lib/format";
import { IMPORT_TYPE_LABELS, SEVERITY_TONE, WORKFLOW_TONE } from "../lib/labels";
import { usePageTitle } from "../lib/usePageTitle";

function greeting(): string {
  const hour = new Date().getHours();
  if (hour < 5) return "Доброй ночи";
  if (hour < 12) return "Доброе утро";
  if (hour < 18) return "Добрый день";
  return "Добрый вечер";
}

function firstName(fullName: string): string {
  const parts = fullName.split(/\s+/);
  return parts[1] || parts[0];
}

function SlaMeter({ days, sla }: { days?: number | null; sla?: number | null }) {
  if (days === null || days === undefined || !sla) return null;
  const ratio = Math.min(days / sla, 1);
  const tone = days > sla ? "meter--bad" : ratio >= 0.75 ? "meter--warn" : "";
  return (
    <div className={`meter ${tone}`} role="img" aria-label={`${days} из ${sla} дней нормы`}>
      <div className="meter__fill" style={{ width: `${Math.max(ratio * 100, 4)}%` }} />
    </div>
  );
}

function NextActions({ items }: { items: NextAction[] }) {
  const label = useLabel();
  if (items.length === 0) {
    return (
      <EmptyState icon={CheckCircle2} title="Срочных шагов нет">
        Все ваши процессы идут в пределах нормы. Новые договоры можно завести в разделе «Договоры».
      </EmptyState>
    );
  }
  return (
    <div className="list">
      {items.map((item) => (
        <Link key={item.contract_id} className="list-item" to={`/contracts/${item.contract_id}?tab=process`}>
          <div className="list-item__main">
            <strong>{item.university_name}</strong>
            <small>
              {item.contract_number} · этап «{item.stage_name}»
            </small>
            {item.actions && item.actions.length > 0 && <small>Дальше: {item.actions.join(" или ")}</small>}
            <div style={{ maxWidth: 260, marginTop: 4 }}>
              <SlaMeter days={item.days_on_stage} sla={item.sla_days} />
            </div>
          </div>
          <div className="list-item__side">
            {item.process_status === "blocked" ? (
              <StatusBadge tone="error">{label("workflow_status", item.process_status)}</StatusBadge>
            ) : item.overdue ? (
              <StatusBadge tone="warning">Дольше нормы</StatusBadge>
            ) : (
              <StatusBadge tone={WORKFLOW_TONE[item.process_status]}>{label("workflow_status", item.process_status)}</StatusBadge>
            )}
            {item.days_on_stage !== null && item.days_on_stage !== undefined && (
              <small className="muted">
                {countLabel(item.days_on_stage, DAYS)} на этапе
                {item.sla_days ? ` из ${item.sla_days}` : ""}
              </small>
            )}
          </div>
        </Link>
      ))}
    </div>
  );
}

function AlertList({ alerts, limit = 8 }: { alerts: Alert[]; limit?: number }) {
  if (alerts.length === 0) {
    return (
      <EmptyState icon={CheckCircle2} title="Проблем нет">
        Сроки, лицензии и процессы в норме.
      </EmptyState>
    );
  }
  return (
    <div className="list">
      {alerts.slice(0, limit).map((alert, index) => {
        const content = (
          <>
            <AlertTriangle
              size={16}
              className={`alert-item__icon alert-item__icon--${alert.severity}`}
              aria-label={alert.severity_label}
            />
            <div className="list-item__main">
              <strong style={{ whiteSpace: "normal" }}>{alert.kind_label}</strong>
              <small>{alert.message}</small>
              <small>{[alert.university_name, alert.contract_number, alert.manager_name].filter(Boolean).join(" · ")}</small>
              <span style={{ marginTop: 4 }}>
                <StatusBadge tone={SEVERITY_TONE[alert.severity]}>{alert.severity_label}</StatusBadge>
              </span>
            </div>
          </>
        );
        return alert.contract_id ? (
          <Link key={index} className="list-item" to={`/contracts/${alert.contract_id}`}>
            {content}
          </Link>
        ) : (
          <div key={index} className="list-item">
            {content}
          </div>
        );
      })}
    </div>
  );
}

function Recent({ data }: { data: Dashboard }) {
  const items = data.recent || [];
  if (items.length === 0) return <p className="muted">Изменений пока не было.</p>;
  return (
    <ol className="timeline">
      {items.slice(0, 8).map((item, index) => (
        <li key={index} className="timeline__item">
          <span
            className={`timeline__dot ${
              item.event_type === "blocked" ? "timeline__dot--bad" : item.event_type === "completed" ? "timeline__dot--good" : ""
            }`}
          >
            {item.event_type === "blocked" ? <Lock size={14} /> : <ArrowRight size={14} />}
          </span>
          <div className="timeline__body">
            <Link to={`/contracts/${item.contract_id}?tab=history`}>
              <strong>{item.university_name}</strong>
            </Link>
            <span>
              {item.event_type_label}: «{item.stage}»
            </span>
            {item.comment && <span className="quote">{item.comment}</span>}
            <span className="timeline__meta">
              {item.user_name} · {formatDateTime(item.created_at)} · {item.contract_number}
            </span>
          </div>
        </li>
      ))}
    </ol>
  );
}

function ManagerLoadTable({ data }: { data: Dashboard }) {
  const [all, setAll] = useState(false);
  const everyone = data.manager_load || [];
  const rows = all ? everyone : everyone.slice(0, 8);
  const navigate = useNavigate();
  if (rows.length === 0) return <p className="muted">Ответственные ещё не назначены.</p>;
  return (
    <div className="table-wrap">
      <table className="data-table data-table--cards">
        <thead>
          <tr>
            <th scope="col">Ответственный</th>
            <th scope="col" className="col-num">
              Договоры
            </th>
            <th scope="col" className="col-num">
              В работе
            </th>
            <th scope="col" className="col-num">
              Заблокировано
            </th>
            <th scope="col" className="col-num">
              Проблемы
            </th>
          </tr>
        </thead>
        <tbody>
          {rows.map((row) => (
            <tr
              key={row.manager_id || "none"}
              className="clickable"
              onClick={() => navigate(row.manager_id ? `/contracts?manager_id=${row.manager_id}` : "/contracts?unassigned=true")}
            >
              <td className="cell-primary">
                <strong>{row.manager_name}</strong>
              </td>
              <td className="col-num" data-label="Договоры">
                {formatNumber(row.contracts)}
              </td>
              <td className="col-num" data-label="В работе">
                {formatNumber(row.active ?? 0)}
              </td>
              <td className="col-num" data-label="Заблокировано">
                {row.blocked ? <StatusBadge tone="error">{row.blocked}</StatusBadge> : "0"}
              </td>
              <td className="col-num" data-label="Проблемы">
                {row.problems ? <StatusBadge tone="warning">{row.problems}</StatusBadge> : "0"}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
      {everyone.length > 8 && (
        <div className="table-footer">
          <span>
            Показано {rows.length} из {everyone.length}
          </span>
          <button type="button" className="link-btn" onClick={() => setAll((value) => !value)}>
            {all ? "Свернуть" : "Показать всех"}
          </button>
        </div>
      )}
    </div>
  );
}

function AdminBlock({ data }: { data: Dashboard }) {
  const admin = data.admin;
  const label = useLabel();
  if (!admin) return null;
  return (
    <div className="grid-3">
      <Card title="Пользователи" actions={<Link to="/admin/users">Управление</Link>}>
        <div className="stack-s">
          <span className="kpi__value">{formatNumber(admin.users_active)}</span>
          <span className="muted">
            активных из {formatNumber(admin.users_total)}; заходили за неделю: {formatNumber(admin.users_seen_recently)}
          </span>
          <div className="tags">
            {Object.entries(admin.users_by_role || {}).map(([role, count]) => (
              <span key={role} className="tag">
                {label("role", role)}: {count}
              </span>
            ))}
          </div>
        </div>
      </Card>
      <Card title="Обмен с LMS и сайтом" actions={<Link to="/integrations">Открыть</Link>}>
        <div className="stack-s">
          {(admin.integrations || []).map((item) => (
            <div key={item.code} className="stack-s" style={{ gap: 2 }}>
              <div className="row-between">
                <strong>{item.name}</strong>
                {item.last_status ? (
                  <StatusBadge
                    tone={item.last_status === "success" ? "success" : item.last_status === "failed" ? "error" : "info"}
                  >
                    {label("integration_run_status", item.last_status)}
                  </StatusBadge>
                ) : (
                  <StatusBadge>Не запускался</StatusBadge>
                )}
              </div>
              <small className="muted">
                {item.last_started_at ? `Последний запуск ${formatDateTime(item.last_started_at)}` : "Запусков ещё не было"}
                {item.uses_fixture ? " · демонстрационный режим" : ""}
              </small>
              {item.last_error && <small className="field__error">{item.last_error}</small>}
            </div>
          ))}
        </div>
      </Card>
      <Card title="Загрузки из Excel" actions={<Link to="/admin/imports">Загрузить</Link>}>
        <div className="stack-s">
          {(admin.imports || []).length === 0 && <span className="muted">Загрузок не было</span>}
          {(admin.imports || []).map((item) => (
            <div key={item.id} className="stack-s" style={{ gap: 2 }}>
              <div className="row-between">
                <strong style={{ overflowWrap: "anywhere" }}>{item.filename}</strong>
                <StatusBadge tone={item.status === "completed" ? "success" : item.status === "failed" ? "error" : "info"}>
                  {label("import_run_status", item.status)}
                </StatusBadge>
              </div>
              <small className="muted">
                {IMPORT_TYPE_LABELS[item.import_type] || item.import_type} · {formatDateTime(item.created_at)} · добавлено{" "}
                {item.rows_created}, обновлено {item.rows_updated}
                {item.rows_failed ? `, ошибок ${item.rows_failed}` : ""}
              </small>
            </div>
          ))}
        </div>
      </Card>
    </div>
  );
}

export default function DashboardPage() {
  const { me, primaryRole, can } = useSession();
  const navigate = useNavigate();
  const [download] = useDownload();
  const dashboard = useQuery({ queryKey: keys.dashboard, queryFn: getDashboard, refetchInterval: 5 * 60_000 });
  usePageTitle("Главная");

  if (dashboard.isPending)
    return (
      <div className="page">
        <Loading />
      </div>
    );
  if (dashboard.isError) {
    return (
      <div className="page">
        <ErrorState error={dashboard.error} onRetry={() => void dashboard.refetch()} />
      </div>
    );
  }

  const data = dashboard.data;
  const counters = data.counters;
  const isManagerView = primaryRole === "manager" && !me.sees_all_contracts;
  // Нагрузка ответственных: руководителю - таблицей выше, менеджеру ни к
  // чему (в ней только он сам). Диаграмма есть в разделе «Отчёты».
  const charts = (data.charts || []).filter((chart) => chart.key !== "by_manager");

  return (
    <div className="page">
      <PageHeader
        eyebrow={formatLongDate()}
        title={`${greeting()}, ${firstName(me.full_name)}`}
        actions={
          <>
            <Button variant="outline" icon={FileText} onClick={() => navigate("/reports")}>
              Отчёт
            </Button>
            <Button icon={Plus} onClick={() => navigate("/contracts?create=1")}>
              Новый договор
            </Button>
          </>
        }
      />

      <div className="stack" style={{ gap: 20 }}>
        <div className="kpi-row">
          {isManagerView ? (
            <Kpi
              label="Мои договоры"
              icon={FileText}
              value={formatNumber(counters.my_contracts)}
              detail={`действует ${formatNumber(counters.contracts_active)}`}
              onClick={() => navigate(`/contracts?manager_id=${me.id}`)}
            />
          ) : (
            <Kpi
              label="Договоры"
              icon={FileText}
              value={formatNumber(counters.contracts)}
              detail={`действует ${formatNumber(counters.contracts_active)} · черновиков ${formatNumber(counters.contracts_draft)}`}
              onClick={() => navigate("/contracts")}
            />
          )}
          <Kpi
            label="Вузы"
            icon={Building2}
            value={formatNumber(counters.universities)}
            detail={isManagerView ? "за которые вы отвечаете" : "в работе ИТ Школы"}
            onClick={() => navigate("/universities")}
          />
          <Kpi
            label="Процессы в работе"
            icon={PlayCircle}
            value={formatNumber(counters.processes_in_progress)}
            detail={`завершено ${formatNumber(counters.processes_completed)}`}
            onClick={() => navigate("/contracts?process=in_progress")}
          />
          <Kpi
            label="Заблокировано"
            icon={Lock}
            tone={counters.processes_blocked ? "alert" : undefined}
            value={formatNumber(counters.processes_blocked)}
            detail="процессов ждут решения"
            onClick={() => navigate("/contracts?process=blocked")}
          />
          <Kpi
            label="Требует внимания"
            icon={AlertTriangle}
            tone={counters.alerts ? "alert" : undefined}
            value={formatNumber(counters.alerts)}
            detail="сроки, лицензии, процессы"
          />
        </div>

        <div className="grid-main-side">
          <div className="stack" style={{ gap: 20 }}>
            {(isManagerView || (data.next_actions || []).length > 0) && (
              <Card
                title="Следующие шаги"
                description="Договоры, по которым пора действовать: этап дольше нормы или процесс остановлен."
                flush
              >
                <NextActions items={data.next_actions || []} />
              </Card>
            )}
            {can("assign_responsible") && (
              <Card
                title="Нагрузка ответственных"
                description="Нажмите на строку, чтобы открыть договоры сотрудника."
                flush
                actions={
                  <Button variant="ghost" size="s" icon={Users} onClick={() => navigate("/universities?unassigned=true")}>
                    Вузы без ответственного
                  </Button>
                }
              >
                <ManagerLoadTable data={data} />
              </Card>
            )}
            <div className="grid-2">
              {charts.map((chart) => (
                <ChartCard
                  key={chart.key}
                  chart={chart}
                  refreshing={dashboard.isFetching}
                  onExport={(format) => download(() => exportReportChart({ filters: {} }, chart.key, format))}
                />
              ))}
            </div>
          </div>
          <div className="stack" style={{ gap: 20 }}>
            <Card
              title="Требует внимания"
              description={`${countLabel((data.alerts || []).length, ["проблема", "проблемы", "проблем"])} по вашим данным`}
              flush
            >
              <AlertList alerts={data.alerts || []} />
            </Card>
            <Card title="Последние изменения" actions={<Clock size={16} className="muted" />}>
              <Recent data={data} />
            </Card>
            {counters.processes_blocked > 0 && !isManagerView && (
              <Card title="Заблокированные процессы">
                <p className="muted" style={{ marginBottom: 12 }}>
                  {countLabel(counters.processes_blocked, ["процесс ждёт", "процесса ждут", "процессов ждут"])} решения.
                </p>
                <Button variant="secondary" icon={Hourglass} onClick={() => navigate("/contracts?process=blocked")}>
                  Показать
                </Button>
              </Card>
            )}
          </div>
        </div>

        <AdminBlock data={data} />
        <p className="muted" style={{ fontSize: 12 }}>
          Данные на {formatDateTime(data.generated_at)}. Обновляются автоматически раз в 5 минут и сразу после ваших действий.
        </p>
      </div>
    </div>
  );
}
