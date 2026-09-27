/**
 * Главная страница - своя для каждой роли (пункты 32-35 перечня исправлений).
 *
 * Менеджер - «Следующие шаги» по своим взаимодействиям: отдельно статус,
 * текущий этап со следующим действием и срок этапа. Руководитель -
 * состояние команды: показатели, очередь решений (без ответственного,
 * заблокированные, просроченные), нагрузка менеджеров и диаграммы; если он
 * сам ведёт вузы - ещё и свои шаги. Администратор - технические сводки:
 * обмен, загрузки, пользователи, очереди проверки.
 *
 * Главное действие - «Новое взаимодействие»: договор заводится внутри
 * взаимодействия, когда до него дойдёт.
 */
import { useQuery } from "@tanstack/react-query";
import {
  AlertTriangle,
  ArrowRight,
  Ban,
  Building2,
  CheckCircle2,
  Clock,
  FileQuestion,
  Handshake,
  Lock,
  PlayCircle,
  Plus,
  UserX,
  Users,
} from "lucide-react";
import { useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import { exportReportChart, getDashboard } from "../api/endpoints";
import { useDownload } from "../api/mutations";
import { keys, useLabel } from "../api/queries";
import type { Alert, ControlItem, Dashboard, NextStep } from "../api/types";
import { useSession } from "../auth/session";
import { ChartCard } from "../charts/ChartCard";
import { Button, Card, EmptyState, ErrorState, Kpi, Loading, PageHeader, StatusBadge } from "../components/ui";
import { interactionTitle, SlaBlock, StatusCell, UniversityName } from "../features/interaction/parts";
import { countLabel, formatDateTime, formatLongDate, formatNumber } from "../lib/format";
import { IMPORT_TYPE_LABELS, RUN_TONE, SEVERITY_TONE } from "../lib/labels";
import { usePageTitle } from "../lib/usePageTitle";

const DASHBOARD_CHARTS = ["by_status", "by_outcome"];
const DASHBOARD_CHARTS_HEAD = ["by_status", "by_outcome", "by_stage", "by_program"];

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

/** Строка шага: три независимых блока - статус, этап со следующим действием, срок. */
function StepRow({ item, reason }: { item: NextStep | ControlItem; reason?: string }) {
  const next = (item.next_actions || [])[0];
  return (
    <Link className="step-row" to={`/interactions/${item.interaction_id}?tab=process`}>
      <div className="step-row__who">
        <strong>
          <UniversityName university={item.university} link={false} />
        </strong>
        <small className="muted">{interactionTitle(item)}</small>
        {reason && <small className="field__error">{reason}</small>}
      </div>
      <div className="step-row__status">
        <span className="step-row__label">Статус</span>
        <StatusCell status={item.status} />
        {item.status === "blocked" && item.blocked_reason && (
          <small className="muted clamp-2" title={item.blocked_reason}>
            {item.blocked_reason}
          </small>
        )}
      </div>
      <div className="step-row__stage">
        <span className="step-row__label">Этап</span>
        <span>{item.status === "draft" ? "Процесс не запущен" : item.stage_name || "—"}</span>
        {next && item.status === "in_progress" && <small className="muted">Дальше: {next}</small>}
      </div>
      <div className="step-row__sla">
        <span className="step-row__label">Срок этапа</span>
        <SlaBlock sla={item.sla} status={item.status} />
      </div>
    </Link>
  );
}

function NextSteps({ items }: { items: NextStep[] }) {
  if (items.length === 0) {
    return (
      <EmptyState icon={CheckCircle2} title="Срочных шагов нет">
        Ваши взаимодействия идут в пределах нормы.
      </EmptyState>
    );
  }
  return (
    <div className="steps-list">
      {items.map((item) => (
        <StepRow key={item.interaction_id} item={item} />
      ))}
    </div>
  );
}

function ControlQueue({ items }: { items: ControlItem[] }) {
  if (items.length === 0) {
    return (
      <EmptyState icon={CheckCircle2} title="Решений не ждут">
        Все взаимодействия команды с ответственными, без блокировок и просрочек.
      </EmptyState>
    );
  }
  return (
    <div className="steps-list">
      {items.map((item) => (
        // Блокировку и так видно по статусу - причину очереди повторяем только для остальных.
        <StepRow
          key={`${item.reason}-${item.interaction_id}`}
          item={item}
          reason={item.reason === "blocked" ? undefined : item.reason_label}
        />
      ))}
    </div>
  );
}

function AlertList({ alerts, limit = 8 }: { alerts: Alert[]; limit?: number }) {
  if (alerts.length === 0) {
    return (
      <EmptyState icon={CheckCircle2} title="Проблем нет">
        Сроки договоров и лицензий, документы и данные в порядке.
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
              <small title={alert.university_full_name || undefined}>
                {[alert.university_name, alert.contract_number, alert.manager_name].filter(Boolean).join(" · ")}
              </small>
              <span style={{ marginTop: 4 }}>
                <StatusBadge tone={SEVERITY_TONE[alert.severity]}>{alert.severity_label}</StatusBadge>
              </span>
            </div>
          </>
        );
        const target = alert.interaction_id ? `/interactions/${alert.interaction_id}` : alert.link;
        return target ? (
          <Link key={index} className="list-item" to={target}>
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
              item.event_type === "blocked" || item.event_type === "cancelled"
                ? "timeline__dot--bad"
                : item.event_type === "completed"
                  ? "timeline__dot--good"
                  : ""
            }`}
          >
            {item.event_type === "blocked" ? <Lock size={14} /> : <ArrowRight size={14} />}
          </span>
          <div className="timeline__body">
            <Link to={`/interactions/${item.interaction_id}?tab=history`} title={item.university.name}>
              <strong>{item.university.short_name || item.university.name}</strong>
            </Link>
            <span>
              {item.event_type_label}
              {item.stage ? `: «${item.stage}»` : ""}
            </span>
            {item.comment && <span className="quote">{item.comment}</span>}
            <span className="timeline__meta">
              {item.user_name} · {formatDateTime(item.created_at)}
            </span>
          </div>
        </li>
      ))}
    </ol>
  );
}

function TeamLoadTable({ data }: { data: Dashboard }) {
  const [all, setAll] = useState(false);
  const everyone = data.team_load || [];
  const rows = all ? everyone : everyone.slice(0, 8);
  const navigate = useNavigate();
  if (rows.length === 0) return <p className="muted">В команде пока нет взаимодействий.</p>;
  return (
    <div className="table-wrap">
      <table className="data-table data-table--cards">
        <thead>
          <tr>
            <th scope="col">Менеджер</th>
            <th scope="col" className="col-num">
              Активные
            </th>
            <th scope="col" className="col-num">
              Просрочено
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
              onClick={() =>
                navigate(row.manager_id ? `/interactions?manager_id=${row.manager_id}` : "/interactions?unassigned=true")
              }
            >
              <td className="cell-primary">
                <strong>{row.manager_name}</strong>
              </td>
              <td className="col-num" data-label="Активные">
                {formatNumber(row.open)}
              </td>
              <td className="col-num" data-label="Просрочено">
                {row.overdue ? <StatusBadge tone="warning">{row.overdue}</StatusBadge> : "0"}
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
  const navigate = useNavigate();
  if (!admin) return null;
  return (
    <>
      <div className="kpi-row">
        <Kpi
          label="Пользователи"
          icon={Users}
          value={formatNumber(admin.users_active)}
          detail={`активных из ${formatNumber(admin.users_total)} · заходили за неделю: ${formatNumber(admin.users_seen_recently)}`}
          onClick={() => navigate("/admin/users")}
        />
        <Kpi
          label="Ждут сопоставления"
          icon={FileQuestion}
          tone={admin.mappings_pending ? "alert" : undefined}
          value={formatNumber(admin.mappings_pending)}
          detail="записи LMS и сайта без пары"
          onClick={() => navigate("/integrations?tab=mappings")}
        />
        <Kpi
          label="Вузы на проверке"
          icon={Building2}
          tone={admin.universities_pending ? "alert" : undefined}
          value={formatNumber(admin.universities_pending)}
          detail="заведены импортом, обменом или менеджером"
          onClick={() => navigate("/universities?status=pending")}
        />
        <Kpi
          label="Временный доступ"
          icon={Clock}
          value={formatNumber(admin.temporary_access)}
          detail="области и доступы к вузам со сроком"
          onClick={() => navigate("/admin/users")}
        />
      </div>
      <div className="grid-3">
        <Card title="Пользователи по ролям" actions={<Link to="/admin/users">Управление</Link>}>
          <div className="tags">
            {Object.entries(admin.users_by_role || {}).map(([role, count]) => (
              <span key={role} className="tag">
                {label("role", role)}: {count}
              </span>
            ))}
          </div>
          <p className="muted" style={{ marginTop: 12 }}>
            Роли не наследуются: совмещение задаётся несколькими ролями явно.
          </p>
        </Card>
        <Card title="Обмен с LMS и сайтом" actions={<Link to="/integrations">Открыть</Link>}>
          <div className="stack-s">
            {(admin.integrations || []).map((item) => (
              <div key={item.code} className="stack-s" style={{ gap: 2 }}>
                <div className="row-between">
                  <strong>{item.name}</strong>
                  {item.last_status ? (
                    <StatusBadge tone={RUN_TONE[item.last_status]}>
                      {label("integration_run_status", item.last_status)}
                    </StatusBadge>
                  ) : (
                    <StatusBadge>Не запускался</StatusBadge>
                  )}
                </div>
                <small className="muted">
                  {item.last_started_at ? `Последний запуск ${formatDateTime(item.last_started_at)}` : "Запусков ещё не было"}
                  {item.uses_fixture ? " · тестовые данные" : ""}
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
    </>
  );
}

export default function DashboardPage() {
  const { me, can } = useSession();
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
  // Показатели с сервера приходят без нулевых полей - дополняем их нулями.
  const counters: Required<Dashboard["counters"]> = {
    open: 0,
    drafts: 0,
    in_progress: 0,
    blocked: 0,
    overdue: 0,
    near_deadline: 0,
    unassigned: 0,
    completed: 0,
    cancelled: 0,
    successful: 0,
    partial: 0,
    unsuccessful: 0,
    universities: 0,
    mine_open: 0,
    alerts: 0,
    ...data.counters,
  };
  const role = data.role;
  const business = data.scope !== "none";
  const head = can("assign_responsible");
  const canCreate = can("create_interaction");
  // Руководителю - статусы и результаты, текущие этапы и программы (пункт 35);
  // нагрузку менеджеров показывает таблица команды, диаграмма её не дублирует.
  const chartKeys = head ? DASHBOARD_CHARTS_HEAD : DASHBOARD_CHARTS;
  const charts = chartKeys.flatMap((key) => (data.charts || []).filter((chart) => chart.key === key));
  const listByStatus = (status: string) => navigate(`/interactions?status=${status}`);

  return (
    <div className="page">
      <PageHeader
        eyebrow={formatLongDate()}
        title={`${greeting()}, ${firstName(me.full_name)}`}
        description={
          business ? `Сводка ${data.scope_label}.` : "Технические сводки: обмен, загрузки, пользователи и очереди проверки."
        }
        actions={
          canCreate && (
            <Button icon={Plus} onClick={() => navigate("/interactions?create=1")}>
              Новое взаимодействие
            </Button>
          )
        }
      />

      <div className="stack" style={{ gap: 20 }}>
        {business && (
          <div className="kpi-row">
            <Kpi
              label={role === "manager" ? "Мои активные" : "Активные"}
              icon={Handshake}
              value={formatNumber(counters.open)}
              detail={`в работе ${formatNumber(counters.in_progress)} · черновиков ${formatNumber(counters.drafts)}`}
              onClick={() => listByStatus("draft,in_progress,blocked")}
            />
            <Kpi
              label="Заблокированы"
              icon={Lock}
              tone={counters.blocked ? "alert" : undefined}
              value={formatNumber(counters.blocked)}
              detail="ждут решения"
              onClick={() => listByStatus("blocked")}
            />
            <Kpi
              label="Просрочен этап"
              icon={Clock}
              tone={counters.overdue ? "alert" : undefined}
              value={formatNumber(counters.overdue)}
              detail={`скоро срок: ${formatNumber(counters.near_deadline)}`}
              onClick={() => navigate("/interactions?overdue=true")}
            />
            {head ? (
              <Kpi
                label="Без ответственного"
                icon={UserX}
                tone={counters.unassigned ? "alert" : undefined}
                value={formatNumber(counters.unassigned)}
                detail="назначьте менеджера"
                onClick={() => navigate("/interactions?unassigned=true")}
              />
            ) : (
              <Kpi
                label="Вузы"
                icon={Building2}
                value={formatNumber(counters.universities)}
                detail="в вашей работе"
                onClick={() => navigate("/universities")}
              />
            )}
            <Kpi
              label="Завершены"
              icon={CheckCircle2}
              value={formatNumber(counters.completed + counters.cancelled)}
              detail={`успешно ${formatNumber(counters.successful)} · частично ${formatNumber(counters.partial)} · без успеха ${formatNumber(counters.unsuccessful)}`}
              onClick={() => listByStatus("completed,cancelled")}
            />
          </div>
        )}

        {business && (
          <div className="grid-main-side">
            <div className="stack" style={{ gap: 20 }}>
              {head && (
                <Card
                  title="Очередь решений"
                  description="Взаимодействия команды, где нужно решение руководителя: назначить, снять блокировку, разобраться со сроком."
                  flush
                >
                  <ControlQueue items={data.control_queue || []} />
                </Card>
              )}
              {role === "manager" || (data.next_steps || []).length > 0 ? (
                <Card
                  title={head ? "Мои шаги" : "Следующие шаги"}
                  description="Ваши взаимодействия: статус, этап со следующим действием и срок этапа. Сначала заблокированные и просроченные."
                  flush
                >
                  <NextSteps items={data.next_steps || []} />
                </Card>
              ) : null}
              {head && (
                <Card
                  title="Нагрузка команды"
                  description="Активные взаимодействия менеджеров, просрочки, блокировки и проблемы. Нажмите на строку, чтобы открыть список."
                  flush
                >
                  <TeamLoadTable data={data} />
                </Card>
              )}
              {charts.length > 0 && (
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
              )}
            </div>
            <div className="stack" style={{ gap: 20 }}>
              <Card
                title="Требует внимания"
                description={`${countLabel(counters.alerts, ["повод", "повода", "поводов"])} ${data.scope_label}`}
                flush
              >
                <AlertList alerts={data.alerts || []} />
              </Card>
              <Card title="Последние изменения" actions={<Clock size={16} className="muted" />}>
                <Recent data={data} />
              </Card>
              {role === "head" && counters.unsuccessful > 0 && (
                <Card title="Закрыто без успеха">
                  <p className="muted" style={{ marginBottom: 12 }}>
                    {countLabel(counters.unsuccessful, ["взаимодействие", "взаимодействия", "взаимодействий"])} с причиной
                    закрытия - разберите в отчётах.
                  </p>
                  <Button variant="secondary" icon={Ban} onClick={() => navigate("/interactions?outcome=unsuccessful")}>
                    Показать
                  </Button>
                </Card>
              )}
            </div>
          </div>
        )}

        {!business && !data.admin && (
          <Card>
            <EmptyState icon={PlayCircle} title="Бизнес-данные недоступны">
              У вашей учётной записи нет области данных. Если доступ нужен для работы, администратор может выдать его, в том числе
              временно.
            </EmptyState>
          </Card>
        )}

        {!business && data.alerts && data.alerts.length > 0 && (
          <Card title="Требует внимания" flush>
            <AlertList alerts={data.alerts} />
          </Card>
        )}

        <AdminBlock data={data} />
        <p className="muted" style={{ fontSize: 12 }}>
          Данные на {formatDateTime(data.generated_at)}
        </p>
      </div>
    </div>
  );
}
