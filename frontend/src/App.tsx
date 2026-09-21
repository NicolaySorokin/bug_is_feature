import { useEffect, useMemo, useState, type ReactNode } from "react";
import {
  AlertTriangle,
  ArrowLeft,
  ArrowRight,
  ArrowUpRight,
  BarChart3,
  Bell,
  Building2,
  CalendarDays,
  Check,
  CheckCircle2,
  ChevronDown,
  ChevronRight,
  CircleAlert,
  CircleDot,
  Clock3,
  Download,
  ExternalLink,
  FileBarChart2,
  FileSpreadsheet,
  FileText,
  Filter,
  Info,
  LayoutDashboard,
  ListFilter,
  LockKeyhole,
  Menu,
  MessageSquare,
  MoreHorizontal,
  Paperclip,
  PanelLeftClose,
  Plus,
  RefreshCw,
  Search,
  Settings2,
  ShieldCheck,
  SlidersHorizontal,
  UploadCloud,
  UserRound,
  Users,
  Workflow,
  X,
} from "lucide-react";
import {
  apiBaseUrl,
  blockWorkflow,
  exportReport,
  getDemoIdentity,
  loadContract,
  loadContracts,
  loadDashboard,
  loadMe,
  loadReport,
  loadUniversities,
  loadWorkflow,
  setDemoIdentity,
  transitionWorkflow,
  unblockWorkflow,
  updateContract,
} from "./api";
import { mockContracts, mockUsers, mockWorkflow } from "./mock";
import type {
  Alert,
  Contract,
  ContractStatus,
  Dashboard,
  DataSource,
  Loaded,
  Page,
  Report,
  Role,
  StageState,
  University,
  User,
  WorkflowStage,
  WorkflowView,
} from "./types";

type Route =
  | { name: "dashboard" }
  | { name: "contracts" }
  | { name: "contract"; id: string }
  | { name: "universities" }
  | { name: "reports" }
  | { name: "integrations" }
  | { name: "admin" };

type Toast = { id: number; tone: "success" | "warning" | "info"; message: string };

const roleLabels: Record<Role, string> = { manager: "Менеджер", head: "Руководитель", admin: "Администратор" };
const statusLabels: Record<ContractStatus, string> = { active: "Активен", draft: "Черновик", suspended: "Приостановлен", closed: "Закрыт" };
const stageLabels: Record<StageState, string> = { not_started: "Не начат", active: "В работе", completed: "Завершён", skipped: "Пропущен", blocked: "Заблокирован" };

function routeFromLocation(): Route {
  const path = window.location.pathname.replace(/\/+$/, "") || "/";
  if (path.startsWith("/contracts/") && path.split("/")[2]) return { name: "contract", id: path.split("/")[2] };
  if (path === "/contracts") return { name: "contracts" };
  if (path === "/universities") return { name: "universities" };
  if (path === "/reports") return { name: "reports" };
  if (path === "/integrations") return { name: "integrations" };
  if (path === "/admin") return { name: "admin" };
  return { name: "dashboard" };
}

function go(to: string): void {
  window.history.pushState({}, "", to);
  window.dispatchEvent(new PopStateEvent("popstate"));
}

function formatDate(value?: string | null): string {
  if (!value) return "—";
  const parsed = new Date(value);
  if (Number.isNaN(parsed.valueOf())) return value;
  return new Intl.DateTimeFormat("ru-RU", { day: "2-digit", month: "short", year: "numeric" }).format(parsed);
}

function formatDateTime(value?: string | null): string {
  if (!value) return "—";
  const parsed = new Date(value);
  if (Number.isNaN(parsed.valueOf())) return value;
  return new Intl.DateTimeFormat("ru-RU", { day: "2-digit", month: "short", hour: "2-digit", minute: "2-digit" }).format(parsed);
}

function initials(name: string): string {
  return name.split(" ").map((part) => part[0]).join("").slice(0, 2).toUpperCase();
}

function statusClass(value: string): string {
  return value.replaceAll("_", "-");
}

function StatusPill({ status, label }: { status: string; label?: string }): JSX.Element {
  return <span className={`status-pill status-${statusClass(status)}`}><span className="status-dot" />{label || status}</span>;
}

function EmptyState({ icon: Icon, title, description, action }: { icon: typeof FileText; title: string; description: string; action?: ReactNode }): JSX.Element {
  return <div className="empty-state"><div className="empty-icon"><Icon size={22} /></div><h3>{title}</h3><p>{description}</p>{action}</div>;
}

function LoadingState({ text = "Загружаем данные" }: { text?: string }): JSX.Element {
  return <div className="loading-state"><RefreshCw size={18} className="spin" />{text}…</div>;
}

function MetricCard({ label, value, detail, icon: Icon, tone, onClick }: { label: string; value: number | string; detail: string; icon: typeof FileText; tone?: string; onClick?: () => void }): JSX.Element {
  return <button className={`metric-card ${tone || ""}`} onClick={onClick} type="button"><span className="metric-icon"><Icon size={19} /></span><span className="metric-label">{label}</span><strong>{value}</strong><span className="metric-detail">{detail}<ArrowUpRight size={13} /></span></button>;
}

function SectionHeader({ eyebrow, title, description, actions }: { eyebrow?: string; title: string; description?: string; actions?: ReactNode }): JSX.Element {
  return <div className="section-header"><div>{eyebrow && <span className="eyebrow">{eyebrow}</span>}<h1>{title}</h1>{description && <p>{description}</p>}</div>{actions && <div className="section-actions">{actions}</div>}</div>;
}

function Button({ children, variant = "primary", icon: Icon, onClick, type = "button", disabled }: { children: ReactNode; variant?: "primary" | "secondary" | "ghost" | "danger"; icon?: typeof Plus; onClick?: () => void; type?: "button" | "submit"; disabled?: boolean }): JSX.Element {
  return <button type={type} className={`button button-${variant}`} onClick={onClick} disabled={disabled}>{Icon && <Icon size={16} />}{children}</button>;
}

function DataSourceBanner({ source, error }: { source?: DataSource; error?: string }): JSX.Element | null {
  if (!source) return null;
  return <div className={`source-banner ${source === "demo" ? "source-demo" : "source-api"}`}><span className="source-mark">{source === "api" ? <Check size={14} /> : <Info size={14} />}</span><span>{source === "api" ? "Подключено к API" : "Демо-режим: API пока недоступен"}</span>{source === "demo" && error && <span className="source-error" title={error}>Проверить подключение</span>}</div>;
}

function App(): JSX.Element {
  const [route, setRoute] = useState<Route>(routeFromLocation);
  const [collapsed, setCollapsed] = useState(false);
  const [mobileNav, setMobileNav] = useState(false);
  const [me, setMe] = useState<Loaded<User> | null>(null);
  const [toasts, setToasts] = useState<Toast[]>([]);

  useEffect(() => {
    const onPopState = () => setRoute(routeFromLocation());
    window.addEventListener("popstate", onPopState);
    loadMe().then(setMe).catch(() => undefined);
    return () => window.removeEventListener("popstate", onPopState);
  }, []);

  const addToast = (message: string, tone: Toast["tone"] = "info") => {
    const id = Date.now();
    setToasts((items) => [...items, { id, message, tone }]);
    window.setTimeout(() => setToasts((items) => items.filter((item) => item.id !== id)), 4200);
  };

  const identity = getDemoIdentity();
  const user = me?.data || mockUsers[0];
  const source = me?.source;
  const title = route.name === "dashboard" ? "Обзор" : route.name === "contracts" ? "Договоры" : route.name === "contract" ? "Карточка договора" : route.name === "universities" ? "Университеты" : route.name === "reports" ? "Отчёты" : route.name === "integrations" ? "Интеграции" : "Настройки";

  const navigate = (path: string) => {
    go(path);
    setMobileNav(false);
  };

  const changeIdentity = (username: string) => {
    const selected = mockUsers.find((item) => item.username === username) || mockUsers[0];
    setDemoIdentity({ username: selected.username, roles: selected.roles });
    setMe({ data: selected, source: "demo" });
    addToast(`Роль переключена: ${roleLabels[selected.roles[0]]}`, "success");
  };

  return <div className={`app ${collapsed ? "nav-collapsed" : ""} ${mobileNav ? "nav-open" : ""}`}>
    <aside className="sidebar">
      <div className="brand" onClick={() => navigate("/")} role="button" tabIndex={0}>
        <span className="brand-mark"><span /></span><span className="brand-copy"><strong>Ростелеком</strong><small>IT School CRM</small></span>
      </div>
      <nav className="main-nav">
        <NavItem icon={LayoutDashboard} label="Обзор" active={route.name === "dashboard"} collapsed={collapsed} onClick={() => navigate("/")} />
        <NavItem icon={FileText} label="Договоры" active={route.name === "contracts" || route.name === "contract"} collapsed={collapsed} onClick={() => navigate("/contracts")} badge="6" />
        <NavItem icon={Building2} label="Университеты" active={route.name === "universities"} collapsed={collapsed} onClick={() => navigate("/universities")} />
        <NavItem icon={BarChart3} label="Отчёты" active={route.name === "reports"} collapsed={collapsed} onClick={() => navigate("/reports")} />
        <div className="nav-divider" />
        <NavItem icon={Workflow} label="Интеграции" active={route.name === "integrations"} collapsed={collapsed} onClick={() => navigate("/integrations")} />
        <NavItem icon={Settings2} label="Настройки" active={route.name === "admin"} collapsed={collapsed} onClick={() => navigate("/admin")} />
      </nav>
      <div className="sidebar-bottom">
        <div className="security-note"><ShieldCheck size={17} /><span><strong>Защищённый контур</strong><small>Данные обрабатываются по 152-ФЗ</small></span></div>
        <button className="collapse-button" onClick={() => setCollapsed((value) => !value)} type="button" title={collapsed ? "Развернуть меню" : "Свернуть меню"}>{collapsed ? <ChevronRight size={17} /> : <PanelLeftClose size={17} />}</button>
      </div>
    </aside>
    <div className="main-area">
      <header className="topbar"><button className="mobile-menu" onClick={() => setMobileNav((value) => !value)} type="button"><Menu size={21} /></button><div className="breadcrumbs"><span>IT School CRM</span><ChevronRight size={14} /><strong>{title}</strong></div><div className="topbar-actions"><div className="api-indicator"><span className={`indicator-dot ${source === "api" ? "online" : "offline"}`} />{source === "api" ? "API онлайн" : "Демо-режим"}</div><button className="icon-button notification-button" type="button" onClick={() => addToast("Новых уведомлений нет", "info")}><Bell size={19} /><span>3</span></button><div className="profile-switcher"><div className="avatar">{initials(user.full_name)}</div><div className="profile-copy"><strong>{user.full_name}</strong><small>{roleLabels[user.roles[0] || "manager"]}</small></div><select aria-label="Переключить пользователя" value={identity.username} onChange={(event) => changeIdentity(event.target.value)}><option value="petrov">Пётр Петров</option><option value="ivanova">Мария Иванова</option><option value="orlova">Ольга Орлова</option><option value="admin">Администратор</option></select><ChevronDown size={15} /></div></div></header>
      <main className="content"><DataSourceBanner source={source} error={me?.error} />{route.name === "dashboard" && <DashboardPage navigate={navigate} onToast={addToast} />}{route.name === "contracts" && <ContractsPage navigate={navigate} onToast={addToast} />}{route.name === "contract" && <ContractPage id={route.id} navigate={navigate} onToast={addToast} />}{route.name === "universities" && <UniversitiesPage navigate={navigate} />}{route.name === "reports" && <ReportsPage onToast={addToast} />}{route.name === "integrations" && <PlaceholderPage kind="integrations" />}{route.name === "admin" && <PlaceholderPage kind="admin" />}</main>
    </div>
    <div className="toast-stack">{toasts.map((toast) => <div className={`toast toast-${toast.tone}`} key={toast.id}><span>{toast.tone === "success" ? <CheckCircle2 size={17} /> : toast.tone === "warning" ? <AlertTriangle size={17} /> : <Info size={17} />}</span>{toast.message}<button type="button" onClick={() => setToasts((items) => items.filter((item) => item.id !== toast.id))}><X size={15} /></button></div>)}</div>
  </div>;
}

function NavItem({ icon: Icon, label, active, collapsed, onClick, badge }: { icon: typeof FileText; label: string; active: boolean; collapsed: boolean; onClick: () => void; badge?: string }): JSX.Element {
  return <button className={`nav-item ${active ? "active" : ""}`} onClick={onClick} type="button" title={collapsed ? label : undefined}><Icon size={18} /><span>{label}</span>{badge && <em>{badge}</em>}</button>;
}

function DashboardPage({ navigate, onToast }: { navigate: (path: string) => void; onToast: (message: string, tone?: Toast["tone"]) => void }): JSX.Element {
  const [result, setResult] = useState<Loaded<Dashboard> | null>(null);
  useEffect(() => { loadDashboard().then(setResult).catch(() => setResult(null)); }, []);
  if (!result) return <><SectionHeader eyebrow="Рабочий стол" title="Обзор" description="Контроль договоров и взаимодействия с университетами" /><LoadingState /></>;
  const dashboard = result.data;
  return <>
    <SectionHeader eyebrow="Рабочий стол" title="Обзор" description="Контроль договоров и взаимодействия с университетами" actions={<><Button variant="secondary" icon={RefreshCw} onClick={() => { setResult(null); loadDashboard().then(setResult); }}>Обновить</Button><Button icon={Plus} onClick={() => navigate("/contracts")}>Новый договор</Button></>} />
    <div className="welcome-strip"><div><span className="welcome-kicker">Понедельник, 21 сентября 2026</span><h2>Добрый день, Пётр</h2><p>Вот как обстоят дела по вашему портфелю сегодня.</p></div><div className="welcome-art"><span className="art-ring ring-one" /><span className="art-ring ring-two" /><span className="art-dot" /></div></div>
    <div className="metric-grid"><MetricCard label="Всего договоров" value={dashboard.counters.contracts} detail={`${dashboard.counters.contracts_active} активных`} icon={FileText} tone="tone-purple" onClick={() => navigate("/contracts")} /><MetricCard label="В работе" value={dashboard.counters.processes_in_progress} detail="процессов сейчас" icon={Workflow} tone="tone-blue" onClick={() => navigate("/contracts")} /><MetricCard label="Нужно внимание" value={dashboard.counters.alerts} detail={`${dashboard.counters.processes_blocked} заблокировано`} icon={CircleAlert} tone="tone-orange" onClick={() => onToast("Фильтр внимания доступен в реестре договоров", "info")} /><MetricCard label="Университеты" value={dashboard.counters.universities} detail="в активном портфеле" icon={Building2} tone="tone-pink" onClick={() => navigate("/universities")} /></div>
    <div className="dashboard-grid"><section className="panel alerts-panel"><div className="panel-heading"><div><span className="eyebrow">Контроль сроков</span><h2>Требуют внимания <span className="heading-count">{dashboard.alerts.length}</span></h2></div><button className="text-button" onClick={() => navigate("/contracts")} type="button">Все договоры <ArrowRight size={15} /></button></div><div className="alert-list">{dashboard.alerts.map((alert) => <AlertRow alert={alert} key={`${alert.kind}-${alert.contract_id}`} onClick={() => alert.contract_id && navigate(`/contracts/${alert.contract_id}`)} />)}</div></section><section className="panel chart-panel"><div className="panel-heading"><div><span className="eyebrow">Состояние портфеля</span><h2>Договоры по статусам</h2></div><button className="icon-button" type="button" onClick={() => onToast("График обновлён", "success")}><MoreHorizontal size={19} /></button></div><StatusChart items={dashboard.charts[0]?.items || []} /></section></div>
    <div className="dashboard-grid bottom-grid"><section className="panel manager-panel"><div className="panel-heading"><div><span className="eyebrow">Нагрузка команды</span><h2>Ответственные</h2></div><button className="text-button" onClick={() => onToast("Распределение ответственных будет доступно в следующей версии", "info")} type="button">Настроить <ArrowRight size={15} /></button></div><div className="manager-list">{dashboard.manager_load.map((manager) => <div className="manager-row" key={manager.manager_id}><div className="avatar avatar-soft">{initials(manager.manager_name)}</div><div className="manager-info"><strong>{manager.manager_name}</strong><small>{manager.contracts} договора · {manager.active} активных</small></div><div className="load-track"><span style={{ width: `${Math.min(100, Math.max(16, manager.contracts * 16))}%` }} /></div><span className="load-value">{manager.contracts}</span></div>)}</div></section><section className="panel activity-panel"><div className="panel-heading"><div><span className="eyebrow">Журнал изменений</span><h2>Последняя активность</h2></div><button className="icon-button" type="button" onClick={() => onToast("Журнал активности синхронизирован", "success")}><RefreshCw size={17} /></button></div><div className="activity-list">{dashboard.recent.map((item) => <div className="activity-row" key={item.entity_id}><span className="activity-icon"><CheckCircle2 size={15} /></span><div><strong>{item.summary}</strong><small>{item.user_name} · {formatDateTime(item.created_at)}</small></div></div>)}</div></section></div>
  </>;
}

function AlertRow({ alert, onClick }: { alert: Alert; onClick: () => void }): JSX.Element {
  const Icon = alert.severity === "critical" ? CircleAlert : alert.severity === "warning" ? AlertTriangle : Info;
  return <button className="alert-row" onClick={onClick} type="button"><span className={`alert-icon alert-${alert.severity}`}><Icon size={16} /></span><span className="alert-copy"><strong>{alert.message}</strong><small>{alert.university_name} · {alert.contract_number}</small></span><ChevronRight size={16} className="alert-arrow" /></button>;
}

function StatusChart({ items }: { items: { label: string; value: number }[] }): JSX.Element {
  const max = Math.max(...items.map((item) => item.value), 1);
  const colors = ["#5d21b6", "#f60b59", "#2c86f3", "#9b91d9"];
  return <div className="status-chart"><div className="chart-donut" style={{ background: `conic-gradient(${colors[0]} 0 62%, ${colors[1]} 62% 84%, ${colors[2]} 84% 100%)` }}><div><strong>{items.reduce((sum, item) => sum + item.value, 0)}</strong><small>договоров</small></div></div><div className="chart-legend">{items.map((item, index) => <div className="legend-row" key={item.label}><span style={{ background: colors[index % colors.length] }} /> <span>{item.label}</span><strong>{item.value}</strong><div className="mini-track"><i style={{ width: `${(item.value / max) * 100}%`, background: colors[index % colors.length] }} /></div></div>)}</div></div>;
}

function ContractsPage({ navigate, onToast }: { navigate: (path: string) => void; onToast: (message: string, tone?: Toast["tone"]) => void }): JSX.Element {
  const [result, setResult] = useState<Loaded<Page<Contract>> | null>(null);
  const [search, setSearch] = useState("");
  const [status, setStatus] = useState("");
  useEffect(() => { loadContracts({ limit: 50 }).then(setResult).catch(() => setResult(null)); }, []);
  const contracts = useMemo(() => (result?.data.items || []).filter((item) => !status || item.status === status).filter((item) => !search || `${item.number} ${item.title || ""} ${item.university?.name || ""}`.toLowerCase().includes(search.toLowerCase())), [result, search, status]);
  if (!result) return <><SectionHeader eyebrow="Портфель" title="Договоры" description="Единый реестр договоров, лицензий и текущих процессов" /><LoadingState /></>;
  return <><SectionHeader eyebrow="Портфель" title="Договоры" description={`${result.data.total} записей · обновлено только что`} actions={<><Button variant="secondary" icon={Download} onClick={() => onToast("Отчёт сформирован в разделе «Отчёты»", "success")}>Экспорт</Button><Button icon={Plus} onClick={() => onToast("Создание договора подключим к форме backend API", "info")}>Новый договор</Button></>} /><div className="filter-bar"><div className="search-field"><Search size={17} /><input value={search} onChange={(event) => setSearch(event.target.value)} placeholder="Поиск по номеру, вузу или названию" /></div><select value={status} onChange={(event) => setStatus(event.target.value)} aria-label="Фильтр по статусу"><option value="">Все статусы</option><option value="active">Активен</option><option value="draft">Черновик</option><option value="suspended">Приостановлен</option><option value="closed">Закрыт</option></select><button className="filter-button" type="button" onClick={() => onToast("Доступны фильтры: срок, университет, направление, продукт и ответственный", "info")}><SlidersHorizontal size={16} />Фильтры<span>2</span></button><button className="icon-button" type="button" onClick={() => { setSearch(""); setStatus(""); }} title="Сбросить фильтры"><RefreshCw size={17} /></button></div><div className="table-meta"><span>Показано <strong>{contracts.length}</strong> из {result.data.total}</span><span className="meta-hint"><ListFilter size={15} /> Сортировка: дата обновления <ChevronDown size={14} /></span></div><div className="panel table-panel"><div className="table-scroll"><table className="data-table"><thead><tr><th>Договор</th><th>Университет</th><th>Ответственный</th><th>Срок действия</th><th>Статус</th><th /></tr></thead><tbody>{contracts.map((contract) => <ContractRow contract={contract} key={contract.id} onClick={() => navigate(`/contracts/${contract.id}`)} />)}</tbody></table>{contracts.length === 0 && <EmptyState icon={Search} title="Ничего не найдено" description="Измените поисковый запрос или сбросьте фильтры." />}</div></div></>;
}

function ContractRow({ contract, onClick }: { contract: Contract; onClick: () => void }): JSX.Element {
  const manager = mockUsers.find((item) => item.id === contract.manager_id);
  return <tr onClick={onClick} className="clickable-row"><td><div className="contract-cell"><span className="contract-icon"><FileText size={17} /></span><span><strong>{contract.number}</strong><small>{contract.title || "Без названия"}</small></span></div></td><td><strong>{contract.university?.short_name || contract.university?.name || "—"}</strong><small className="cell-subtitle">{contract.university?.city || ""}</small></td><td><div className="person-cell"><span className="avatar avatar-tiny">{initials(manager?.full_name || "—")}</span>{manager?.full_name || "Не назначен"}</div></td><td><span className={contract.valid_to && new Date(contract.valid_to) < new Date("2026-10-01") ? "date-warning" : ""}>{formatDate(contract.valid_to)}</span><small className="cell-subtitle">до окончания</small></td><td><StatusPill status={contract.status} label={statusLabels[contract.status]} /></td><td><button className="row-arrow" type="button" onClick={(event) => { event.stopPropagation(); onClick(); }}><ChevronRight size={18} /></button></td></tr>;
}

function ContractPage({ id, navigate, onToast }: { id: string; navigate: (path: string) => void; onToast: (message: string, tone?: Toast["tone"]) => void }): JSX.Element {
  const [contractResult, setContractResult] = useState<Loaded<Contract> | null>(null);
  const [workflowResult, setWorkflowResult] = useState<Loaded<WorkflowView> | null>(null);
  const [tab, setTab] = useState<"overview" | "workflow" | "history" | "files">("overview");
  const [selectedStage, setSelectedStage] = useState<string | null>(null);
  const [transitionTarget, setTransitionTarget] = useState<{ id: string; name: string; requiresComment: boolean } | null>(null);
  const [comment, setComment] = useState("");
  const [busy, setBusy] = useState(false);
  const [actionMenu, setActionMenu] = useState(false);
  const [editOpen, setEditOpen] = useState(false);
  const [editBusy, setEditBusy] = useState(false);
  const [editForm, setEditForm] = useState({ title: "", status: "active", valid_to: "", comment: "" });
  useEffect(() => { setContractResult(null); setWorkflowResult(null); setActionMenu(false); Promise.all([loadContract(id), loadWorkflow(id)]).then(([contract, workflow]) => { setContractResult(contract); setWorkflowResult(workflow); setEditForm({ title: contract.data.title || "", status: contract.data.status, valid_to: contract.data.valid_to || "", comment: contract.data.comment || "" }); }).catch(() => undefined); }, [id]);
  if (!contractResult || !workflowResult) return <><button className="back-link" type="button" onClick={() => navigate("/contracts")}><ArrowLeft size={16} />Назад к договорам</button><LoadingState text="Загружаем карточку договора" /></>;
  const contract = contractResult.data;
  const workflow = workflowResult.data;
  const stages = workflow.version.stages;
  const currentStage = stages.find((stage) => stage.id === workflow.current_stage_id);
  const manager = mockUsers.find((item) => item.id === contract.manager_id);
  const updateWorkflowLocally = (targetId: string, nextStatus: WorkflowView["status"] = "in_progress", nextComment?: string) => {
    setWorkflowResult({ ...workflowResult, data: localWorkflowTransition(workflow, targetId, nextStatus, nextComment) });
  };
  const updateWorkflowStatusLocally = (nextStatus: WorkflowView["status"], reason: string) => {
    setWorkflowResult({ ...workflowResult, data: localWorkflowStatus(workflow, nextStatus, reason) });
  };
  const handleTransition = async () => {
    if (!transitionTarget) return;
    setBusy(true);
    try {
      if (workflowResult.source === "api") setWorkflowResult({ data: await transitionWorkflow(workflow.id, transitionTarget.id, comment), source: "api" });
      else updateWorkflowLocally(transitionTarget.id, "in_progress", comment);
      onToast(`Процесс переведён на этап «${transitionTarget.name}»`, "success");
    } catch (error) {
      updateWorkflowLocally(transitionTarget.id, "in_progress", comment);
      onToast(error instanceof Error ? `${error.message}. Изменение сохранено в демо-сценарии.` : "Изменение сохранено в демо-сценарии", "warning");
    } finally { setBusy(false); setTransitionTarget(null); setComment(""); }
  };
  const handleBlock = async () => {
    const reason = window.prompt("Почему процесс нужно заблокировать?", "Ожидаем документы от университета") || "Ожидаем уточнения";
    setBusy(true);
    try { if (workflowResult.source === "api") setWorkflowResult({ data: await blockWorkflow(workflow.id, reason), source: "api" }); else updateWorkflowStatusLocally("blocked", reason); onToast("Процесс заблокирован, причина добавлена в историю", "warning"); } catch { updateWorkflowStatusLocally("blocked", reason); onToast("Процесс заблокирован в демо-сценарии", "warning"); } finally { setBusy(false); }
  };
  const handleUnblock = async () => {
    const reason = window.prompt("Что изменилось?", "Документы получены, можно продолжить процесс") || "Блокировка снята менеджером";
    setBusy(true);
    try { if (workflowResult.source === "api") setWorkflowResult({ data: await unblockWorkflow(workflow.id, reason), source: "api" }); else updateWorkflowStatusLocally("in_progress", reason); onToast("Блокировка снята, процесс снова в работе", "success"); } catch { updateWorkflowStatusLocally("in_progress", reason); onToast("Блокировка снята в демо-сценарии", "success"); } finally { setBusy(false); }
  };
  const saveContract = async () => {
    setEditBusy(true);
    const payload = { title: editForm.title || null, status: editForm.status, valid_to: editForm.valid_to || null, comment: editForm.comment || null };
    try {
      const updated = contractResult.source === "api" ? await updateContract(contract.id, payload) : { ...contract, ...payload } as Contract;
      setContractResult({ data: updated, source: contractResult.source });
      setEditOpen(false);
      setActionMenu(false);
      onToast("Реквизиты договора сохранены", "success");
    } catch (error) { onToast(error instanceof Error ? error.message : "Не удалось сохранить договор", "warning"); } finally { setEditBusy(false); }
  };
  const copyContractNumber = async () => {
    try { await navigator.clipboard.writeText(contract.number); onToast("Номер договора скопирован", "success"); } catch { onToast(`Номер договора: ${contract.number}`, "info"); }
    setActionMenu(false);
  };
  return <><button className="back-link" type="button" onClick={() => navigate("/contracts")}><ArrowLeft size={16} />Назад к договорам</button><div className="contract-heading"><div><div className="heading-line"><span className="contract-number">{contract.number}</span><StatusPill status={contract.status} label={statusLabels[contract.status]} /></div><h1>{contract.title || "Договор без названия"}</h1><p className="heading-subtitle"><Building2 size={16} />{contract.university?.name || "Университет не указан"}<span>·</span>{contract.university?.city || "Город не указан"}</p></div><div className="heading-buttons"><div className="action-menu-wrap"><Button variant="secondary" icon={MoreHorizontal} onClick={() => setActionMenu((value) => !value)}>Действия</Button>{actionMenu && <div className="action-menu"><button type="button" onClick={() => { setEditOpen(true); setActionMenu(false); }}><Settings2 size={15} />Редактировать реквизиты</button><button type="button" onClick={copyContractNumber}><FileText size={15} />Скопировать номер</button><button type="button" onClick={() => { setActionMenu(false); navigate("/reports"); }}><FileBarChart2 size={15} />Открыть отчёты</button></div>}</div><Button icon={FileBarChart2} onClick={() => navigate("/reports")}>Сформировать отчёт</Button></div></div><div className="detail-summary"><div><span>Ответственный</span><strong><span className="avatar avatar-tiny">{initials(manager?.full_name || "—")}</span>{manager?.full_name || "Не назначен"}</strong></div><div><span>Подписан</span><strong>{formatDate(contract.signed_at)}</strong></div><div><span>Действует до</span><strong className={contract.valid_to && new Date(contract.valid_to) < new Date("2026-10-01") ? "date-warning" : ""}>{formatDate(contract.valid_to)}</strong></div><div><span>Текущий этап</span><strong><span className="stage-pulse" />{currentStage?.name || "Не начат"}</strong></div></div><div className="tabs"><button className={tab === "overview" ? "active" : ""} onClick={() => setTab("overview")} type="button">Обзор</button><button className={tab === "workflow" ? "active" : ""} onClick={() => setTab("workflow")} type="button">Процесс <span>{stages.length}</span></button><button className={tab === "history" ? "active" : ""} onClick={() => setTab("history")} type="button">История <span>{workflow.events.length}</span></button><button className={tab === "files" ? "active" : ""} onClick={() => setTab("files")} type="button">Файлы</button></div>{tab === "overview" && <OverviewTab contract={contract} workflow={workflow} onWorkflow={() => setTab("workflow")} onToast={onToast} />}{tab === "workflow" && <WorkflowTab workflow={workflow} selectedStage={selectedStage} setSelectedStage={setSelectedStage} onTransition={(target) => setTransitionTarget(target)} onBlock={handleBlock} onUnblock={handleUnblock} busy={busy} />}{tab === "history" && <HistoryTab workflow={workflow} stages={stages} />}{tab === "files" && <FilesTab onToast={onToast} />}{editOpen && <div className="modal-backdrop" onMouseDown={() => !editBusy && setEditOpen(false)}><div className="modal" onMouseDown={(event) => event.stopPropagation()}><div className="modal-header"><div><span className="eyebrow">Карточка договора</span><h2>Редактировать реквизиты</h2></div><button className="icon-button" type="button" onClick={() => setEditOpen(false)}><X size={18} /></button></div><div className="edit-form"><label className="field-label">Название<input value={editForm.title} onChange={(event) => setEditForm({ ...editForm, title: event.target.value })} /></label><div className="edit-form-row"><label className="field-label">Статус<select value={editForm.status} onChange={(event) => setEditForm({ ...editForm, status: event.target.value })}><option value="draft">Черновик</option><option value="active">Активен</option><option value="suspended">Приостановлен</option><option value="closed">Закрыт</option></select></label><label className="field-label">Действует до<input type="date" value={editForm.valid_to} onChange={(event) => setEditForm({ ...editForm, valid_to: event.target.value })} /></label></div><label className="field-label">Комментарий<textarea value={editForm.comment} onChange={(event) => setEditForm({ ...editForm, comment: event.target.value })} placeholder="Комментарий менеджера" rows={4} /></label></div><div className="modal-actions"><Button variant="ghost" onClick={() => setEditOpen(false)}>Отмена</Button><Button onClick={saveContract} disabled={editBusy}>{editBusy ? "Сохраняем…" : "Сохранить"}</Button></div></div></div>}{transitionTarget && <div className="modal-backdrop" onMouseDown={() => !busy && setTransitionTarget(null)}><div className="modal" onMouseDown={(event) => event.stopPropagation()}><div className="modal-header"><div><span className="eyebrow">Смена этапа</span><h2>Перевести процесс?</h2></div><button className="icon-button" type="button" onClick={() => setTransitionTarget(null)}><X size={18} /></button></div><p>Следующим этапом станет <strong>«{transitionTarget.name}»</strong>. Изменение попадёт в историю договора.</p><label className="field-label">Комментарий {transitionTarget.requiresComment && <em>обязателен</em>}<textarea value={comment} onChange={(event) => setComment(event.target.value)} placeholder="Добавьте контекст для команды" rows={4} /></label><div className="modal-actions"><Button variant="ghost" onClick={() => setTransitionTarget(null)}>Отмена</Button><Button onClick={handleTransition} disabled={busy || (transitionTarget.requiresComment && !comment.trim())}>{busy ? "Сохраняем…" : "Подтвердить переход"}</Button></div></div></div>}</>;
}

function OverviewTab({ contract, workflow, onWorkflow, onToast }: { contract: Contract; workflow: WorkflowView; onWorkflow: () => void; onToast: (message: string, tone?: Toast["tone"]) => void }): JSX.Element {
  return <div className="detail-grid"><section className="panel detail-panel"><div className="panel-heading"><div><span className="eyebrow">Основная информация</span><h2>О договоре</h2></div><button className="icon-button" type="button" onClick={() => onToast("Редактирование договора подключим к backend API", "info")}><Settings2 size={18} /></button></div><div className="info-grid"><InfoItem label="Номер договора" value={contract.number} /><InfoItem label="Дата подписания" value={formatDate(contract.signed_at)} /><InfoItem label="Начало действия" value={formatDate(contract.valid_from)} /><InfoItem label="Окончание действия" value={formatDate(contract.valid_to)} /><InfoItem label="Статус лицензии" value="Передана в университет" /><InfoItem label="Последнее изменение" value={formatDateTime(workflow.events.at(-1)?.created_at)} /></div><div className="comment-box"><MessageSquare size={17} /><div><span>Комментарий менеджера</span><p>{contract.comment || "Комментарий пока не добавлен."}</p></div></div></section><section className="panel detail-panel"><div className="panel-heading"><div><span className="eyebrow">Взаимодействие</span><h2>Университет</h2></div><Building2 size={20} className="heading-icon" /></div><div className="university-card"><div className="university-logo">{(contract.university?.short_name || contract.university?.name || "У").slice(0, 1)}</div><div><h3>{contract.university?.name || "Университет не указан"}</h3><p>{contract.university?.city || "Город не указан"}</p></div></div><div className="contact-row"><span className="avatar avatar-soft">АС</span><div><strong>Анна Соколова</strong><small>Контактное лицо · {contract.university?.contacts?.[0]?.email || "email не указан"}</small></div><button className="icon-button" type="button" onClick={() => onToast("Контакты университета доступны в API карточки", "info")}><ExternalLink size={16} /></button></div><button className="wide-link" type="button" onClick={onWorkflow}>Открыть процесс взаимодействия <ArrowRight size={16} /></button></section><section className="panel detail-panel"><div className="panel-heading"><div><span className="eyebrow">ИТ-направления</span><h2>Программы</h2></div><button className="icon-button" type="button" onClick={() => onToast("Добавление программы подключим к форме договора", "info")}><Plus size={18} /></button></div><div className="tag-list">{contract.programs?.map((item) => <div className="catalog-row" key={item.id}><span className="catalog-icon"><Workflow size={16} /></span><div><strong>{item.program?.name || "Программа"}</strong><small>{item.program?.direction?.name || "Направление не указано"}</small></div><StatusPill status={item.implementation_status === "implemented" ? "completed" : item.implementation_status === "in_progress" ? "active" : "not-started"} label={item.implementation_status === "implemented" ? "Готово" : item.implementation_status === "in_progress" ? "В работе" : "Не начато"} /></div>)}</div></section><section className="panel detail-panel"><div className="panel-heading"><div><span className="eyebrow">Продукты</span><h2>Передача продуктов</h2></div><button className="icon-button" type="button" onClick={() => onToast("Каталог продуктов загружается из API", "info")}><Plus size={18} /></button></div><div className="tag-list">{contract.products?.length ? contract.products.map((item) => <div className="catalog-row" key={item.id}><span className="catalog-icon product-icon"><FileSpreadsheet size={16} /></span><div><strong>{item.product?.name || "Продукт"}</strong><small>{item.product?.vendor?.name || "Поставщик не указан"}</small></div><StatusPill status={item.transfer_status === "implemented" ? "completed" : item.transfer_status === "suspended" ? "blocked" : "active"} label={item.transfer_status === "implemented" ? "Передан" : item.transfer_status === "suspended" ? "Приостановлен" : "В работе"} /></div>) : <p className="muted-copy">Продукты ещё не назначены.</p>}</div></section></div>;
}

function InfoItem({ label, value }: { label: string; value: string }): JSX.Element { return <div className="info-item"><span>{label}</span><strong>{value}</strong></div>; }

function WorkflowTab({ workflow, selectedStage, setSelectedStage, onTransition, onBlock, onUnblock, busy }: { workflow: WorkflowView; selectedStage: string | null; setSelectedStage: (id: string | null) => void; onTransition: (target: { id: string; name: string; requiresComment: boolean }) => void; onBlock: () => void; onUnblock: () => void; busy: boolean }): JSX.Element {
  return <div className="workflow-layout"><section className="panel workflow-panel"><div className="panel-heading"><div><span className="eyebrow">Визуальный сценарий</span><h2>Процесс взаимодействия</h2></div><div className="workflow-tools"><span className="version-badge">Версия {workflow.version.version_number}</span><button className="icon-button" type="button" title="Обновить" onClick={() => window.location.reload()}><RefreshCw size={17} /></button></div></div><div className="workflow-legend"><span><i className="legend-dot dot-completed" />Завершён</span><span><i className="legend-dot dot-active" />В работе</span><span><i className="legend-dot dot-neutral" />Не начат</span><span><i className="legend-dot dot-blocked" />Заблокирован</span></div><WorkflowCanvas workflow={workflow} selectedStage={selectedStage} onSelect={setSelectedStage} /></section><WorkflowSidePanel workflow={workflow} selectedStage={selectedStage} onTransition={onTransition} onBlock={onBlock} onUnblock={onUnblock} busy={busy} /></div>;
}

function WorkflowCanvas({ workflow, selectedStage, onSelect }: { workflow: WorkflowView; selectedStage: string | null; onSelect: (id: string) => void }): JSX.Element {
  const stageState = new Map(workflow.stage_states.map((item) => [item.stage_id, item.state]));
  const stageMap = new Map(workflow.version.stages.map((stage) => [stage.id, stage]));
  return <div className="workflow-scroll"><div className="workflow-canvas"><svg viewBox="0 0 950 330" preserveAspectRatio="none" aria-hidden="true">{workflow.version.transitions.map((transition) => { const from = stageMap.get(transition.from_stage_id); const to = stageMap.get(transition.to_stage_id); if (!from || !to) return null; const x1 = (from.layout_x || 0) + 130; const y1 = (from.layout_y || 0) * 150 + 74; const x2 = (to.layout_x || 0) + 12; const y2 = (to.layout_y || 0) * 150 + 74; return <line key={transition.id} x1={x1} y1={y1} x2={x2} y2={y2} className={transition.is_backward ? "edge edge-backward" : "edge"} markerEnd="url(#arrow)" />; })}<defs><marker id="arrow" markerWidth="8" markerHeight="8" refX="6" refY="3" orient="auto"><path d="M0,0 L0,6 L6,3 z" fill="currentColor" /></marker></defs></svg>{workflow.version.stages.map((stage) => { const state = stageState.get(stage.id) || "not_started"; return <button type="button" className={`workflow-node node-${state} ${selectedStage === stage.id ? "selected" : ""}`} style={{ left: `${(stage.layout_x || 0) + 10}px`, top: `${(stage.layout_y || 0) * 150 + 28}px` }} onClick={() => onSelect(stage.id)} key={stage.id}><span className="node-number">{stage.sort_order}</span><span className="node-state-icon">{state === "completed" ? <Check size={14} /> : state === "active" ? <CircleDot size={14} /> : state === "blocked" ? <LockKeyhole size={13} /> : <span />}</span><strong>{stage.name}</strong><small>{stage.is_optional ? "Опциональный этап" : stage.is_final ? "Финальный этап" : `${stage.sla_days || "—"} дней SLA`}</small></button>; })}</div></div>;
}

function WorkflowSidePanel({ workflow, selectedStage, onTransition, onBlock, onUnblock, busy }: { workflow: WorkflowView; selectedStage: string | null; onTransition: (target: { id: string; name: string; requiresComment: boolean }) => void; onBlock: () => void; onUnblock: () => void; busy: boolean }): JSX.Element {
  const stage = workflow.version.stages.find((item) => item.id === (selectedStage || workflow.current_stage_id));
  return <aside className="panel workflow-side"><div className="side-stage-heading"><span className="eyebrow">Выбранный этап</span><StatusPill status={workflow.stage_states.find((item) => item.stage_id === stage?.id)?.state || "not_started"} label={stageLabels[workflow.stage_states.find((item) => item.stage_id === stage?.id)?.state || "not_started"]} /></div><h2>{stage?.name || "Этап не выбран"}</h2><p>{stage?.description || "Выберите этап на схеме, чтобы увидеть детали."}</p>{stage && <div className="stage-facts"><div><Clock3 size={15} /><span>SLA</span><strong>{stage.sla_days || "—"} дней</strong></div><div><UserRound size={15} /><span>Ответственный</span><strong>Пётр Петров</strong></div></div>}<div className="side-divider" /><span className="eyebrow">Доступные действия</span><div className="action-list">{workflow.available_transitions.length ? workflow.available_transitions.map((transition) => { const target = workflow.version.stages.find((item) => item.id === transition.to_stage_id); return <button className="workflow-action" type="button" key={transition.id} onClick={() => target && onTransition({ id: target.id, name: target.name, requiresComment: transition.requires_comment })} disabled={busy}><span className={transition.is_backward ? "action-back" : "action-forward"}>{transition.is_backward ? <ArrowLeft size={15} /> : <ArrowRight size={15} />}</span><span>{transition.name || `Перейти к ${target?.name}`}</span><ChevronRight size={15} /></button>; }) : <p className="muted-copy">Для выбранного этапа нет доступных переходов.</p>}{workflow.status === "blocked" ? <button className="workflow-action unblock-action" type="button" onClick={onUnblock} disabled={busy}><span className="action-unblock"><CheckCircle2 size={15} /></span><span>Разблокировать процесс</span><ChevronRight size={15} /></button> : <button className="workflow-action block-action" type="button" onClick={onBlock} disabled={busy}><span className="action-block"><LockKeyhole size={15} /></span><span>Заблокировать процесс</span><ChevronRight size={15} /></button>}</div><div className="side-tip"><Info size={16} /><span>Каждый переход сохраняется в журнале аудита и виден участникам процесса.</span></div></aside>;
}

function HistoryTab({ workflow, stages }: { workflow: WorkflowView; stages: WorkflowStage[] }): JSX.Element {
  const stageNames = new Map(stages.map((stage) => [stage.id, stage.name]));
  return <div className="panel history-panel"><div className="panel-heading"><div><span className="eyebrow">Аудит процесса</span><h2>История изменений</h2></div><span className="version-badge">{workflow.events.length} события</span></div><div className="timeline">{workflow.events.slice().reverse().map((event) => <div className="timeline-item" key={event.id}><span className="timeline-dot"><Check size={13} /></span><div className="timeline-content"><div className="timeline-top"><strong>{event.event_type === "started" ? "Процесс запущен" : event.event_type === "blocked" ? "Процесс заблокирован" : "Переход между этапами"}</strong><time>{formatDateTime(event.created_at)}</time></div><p>{event.comment || "Без комментария"}</p><small>{event.from_stage_id ? `${stageNames.get(event.from_stage_id)} → ` : ""}{stageNames.get(event.to_stage_id || "") || "—"} · Пётр Петров</small></div></div>)}</div></div>;
}

function FilesTab({ onToast }: { onToast: (message: string, tone?: Toast["tone"]) => void }): JSX.Element {
  return <div className="panel files-panel"><div className="panel-heading"><div><span className="eyebrow">Документы договора</span><h2>Файлы</h2></div><Button icon={UploadCloud} onClick={() => onToast("Загрузка файлов поддерживает PDF, DOCX, XLSX, ZIP и изображения", "info")}>Загрузить файл</Button></div><div className="upload-zone"><UploadCloud size={28} /><strong>Перетащите файл сюда</strong><span>или выберите файл с компьютера · до 50 МБ</span><button type="button" onClick={() => onToast("Диалог загрузки будет подключён к /attachments", "info")}>Выбрать файл</button></div><div className="file-row"><span className="file-type pdf-type">PDF</span><div><strong>Протокол встречи.pdf</strong><small>Добавлен 20 сентября 2026 · 2,4 МБ</small></div><button className="icon-button" type="button" onClick={() => onToast("Скачивание подключается к API /attachments/{id}/download", "info")}><Download size={17} /></button></div></div>;
}

function UniversitiesPage({ navigate }: { navigate: (path: string) => void }): JSX.Element {
  const [result, setResult] = useState<Loaded<Page<unknown>> | null>(null);
  useEffect(() => { loadUniversities().then(setResult).catch(() => undefined); }, []);
  if (!result) return <><SectionHeader eyebrow="Справочник" title="Университеты" description="Участники программы и контактные лица" /><LoadingState /></>;
  const universities = result.data.items as University[];
  return <><SectionHeader eyebrow="Справочник" title="Университеты" description={`${result.data.total} организаций в портфеле`} actions={<Button icon={Plus} onClick={() => navigate("/contracts")}>Добавить договор</Button>} /><div className="university-grid">{universities.map((university) => <article className="panel university-tile" key={university.id}><div className="tile-top"><div className="university-logo">{(university.short_name || university.name).slice(0, 1)}</div><StatusPill status={university.is_active ? "active" : "closed"} label={university.is_active ? "Активен" : "Архив"} /></div><h2>{university.short_name || university.name}</h2><p>{university.name}</p><div className="tile-meta"><span><Building2 size={14} />{university.city || "Город не указан"}</span><span><Users size={14} />{university.contacts?.length || 0} контакта</span></div><button className="wide-link" type="button" onClick={() => navigate(`/contracts`)}>Открыть договоры <ArrowRight size={15} /></button></article>)}</div></>;
}

function ReportsPage({ onToast }: { onToast: (message: string, tone?: Toast["tone"]) => void }): JSX.Element {
  const [result, setResult] = useState<Loaded<Report> | null>(null);
  const [filters, setFilters] = useState({ dateFrom: "2026-01-01", dateTo: "2026-09-21", status: "", manager: "" });
  const [loading, setLoading] = useState(false);
  useEffect(() => { loadReport(filters).then(setResult).catch(() => undefined); }, []);
  if (!result) return <><SectionHeader eyebrow="Аналитика" title="Отчёты" description="Сводные данные по договорам и этапам взаимодействия" /><LoadingState text="Готовим отчёт" /></>;
  const report = result.data;
  const apply = () => { setLoading(true); loadReport(filters).then(setResult).finally(() => setLoading(false)); };
  const download = async (format: "xlsx" | "pdf") => {
    try {
      if (result.source === "api") { const blob = await exportReport(filters, format); const url = URL.createObjectURL(blob); const link = document.createElement("a"); link.href = url; link.download = `edu-crm-report.${format}`; link.click(); URL.revokeObjectURL(url); }
      else { const blob = new Blob([JSON.stringify(report.rows, null, 2)], { type: "application/json" }); const url = URL.createObjectURL(blob); const link = document.createElement("a"); link.href = url; link.download = "edu-crm-report-demo.json"; link.click(); URL.revokeObjectURL(url); }
      onToast(`Отчёт ${format.toUpperCase()} подготовлен`, "success");
    } catch (error) { onToast(error instanceof Error ? error.message : "Не удалось скачать отчёт", "warning"); }
  };
  return <><SectionHeader eyebrow="Аналитика" title="Отчёты" description="Сводные данные по договорам и этапам взаимодействия" actions={<><Button variant="secondary" icon={FileSpreadsheet} onClick={() => download("xlsx")}>Excel</Button><Button icon={Download} onClick={() => download("pdf")}>PDF</Button></>} /><div className="report-filters panel"><div className="filter-field"><label>Период с</label><div><CalendarDays size={16} /><input type="date" value={filters.dateFrom} onChange={(event) => setFilters({ ...filters, dateFrom: event.target.value })} /></div></div><div className="filter-field"><label>По</label><div><CalendarDays size={16} /><input type="date" value={filters.dateTo} onChange={(event) => setFilters({ ...filters, dateTo: event.target.value })} /></div></div><div className="filter-field"><label>Статус договора</label><div><Filter size={16} /><select value={filters.status} onChange={(event) => setFilters({ ...filters, status: event.target.value })}><option value="">Все статусы</option><option value="active">Активен</option><option value="draft">Черновик</option></select></div></div><div className="filter-field"><label>Ответственный</label><div><UserRound size={16} /><select value={filters.manager} onChange={(event) => setFilters({ ...filters, manager: event.target.value })}><option value="">Все ответственные</option><option value="petrov">Пётр Петров</option><option value="ivanova">Мария Иванова</option><option value="orlova">Ольга Орлова</option></select></div></div><Button icon={loading ? RefreshCw : BarChart3} onClick={apply} disabled={loading}>{loading ? "Обновляем…" : "Показать"}</Button></div><div className="report-kpis"><div><span>Строк в отчёте</span><strong>{report.totals.rows}</strong><small>по выбранным фильтрам</small></div><div><span>Договоры</span><strong>{report.totals.contracts}</strong><small>{report.totals.universities} университета</small></div><div><span>Программы</span><strong>{report.totals.programs}</strong><small>в каталоге взаимодействия</small></div><div><span>Продукты</span><strong>{report.totals.products}</strong><small>в передаче вузам</small></div></div><div className="report-grid"><section className="panel report-chart-panel"><div className="panel-heading"><div><span className="eyebrow">Распределение</span><h2>Этапы процессов</h2></div><FileBarChart2 size={20} className="heading-icon" /></div><div className="horizontal-bars">{report.charts[1]?.items.map((item, index) => <div className="bar-row" key={item.label}><div><span>{item.label}</span><strong>{item.value}</strong></div><div className="bar-track"><i style={{ width: `${Math.max(10, (item.value / Math.max(...(report.charts[1]?.items.map((chartItem) => chartItem.value) || [1]))) * 100)}%`, background: ["#5d21b6", "#f60b59", "#2c86f3", "#9b91d9"][index % 4] }} /></div></div>)}</div></section><section className="panel report-chart-panel"><div className="panel-heading"><div><span className="eyebrow">Сроки</span><h2>Договоры с риском</h2></div><AlertTriangle size={20} className="heading-icon orange-icon" /></div><div className="risk-card"><div className="risk-number">{report.rows.filter((row) => (row.days_on_stage || 0) > 14).length}</div><div><strong>этапов дольше SLA</strong><p>Нужна проверка ответственных и комментариев.</p></div></div><div className="risk-items">{report.rows.filter((row) => (row.days_on_stage || 0) > 14).slice(0, 3).map((row) => <div key={row.contract_id}><span>{row.contract_number}</span><strong>{row.days_on_stage} дней</strong></div>)}</div></section></div><div className="panel table-panel report-table"><div className="panel-heading"><div><span className="eyebrow">Детализация</span><h2>{report.title}</h2></div><span className="version-badge">Сформирован {formatDateTime(report.generated_at)}</span></div><div className="table-scroll"><table className="data-table"><thead><tr>{report.columns.map((column) => <th key={column}>{report.column_titles[column] || column}</th>)}</tr></thead><tbody>{report.rows.map((row) => <tr key={row.contract_id}><td>{row.university}</td><td>{row.program}</td><td><strong>{row.contract_number}</strong></td><td><StatusPill status={row.contract_status} label={statusLabels[row.contract_status]} /></td><td>{row.stage}<small className="cell-subtitle">{row.days_on_stage} дней на этапе</small></td><td>{row.manager}</td></tr>)}</tbody></table></div></div></>;
}

function PlaceholderPage({ kind }: { kind: "integrations" | "admin" }): JSX.Element {
  const integrations = kind === "integrations";
  return <><SectionHeader eyebrow={integrations ? "Подключения" : "Администрирование"} title={integrations ? "Интеграции" : "Настройки"} description={integrations ? "Обмен данными с LMS и сайтом Ростелекома" : "Роли, шаблоны процессов и контроль доступа"} /><div className="placeholder-grid"><section className="panel placeholder-main"><div className="placeholder-illustration"><span className="placeholder-orbit orbit-a" /><span className="placeholder-orbit orbit-b" /><span className="placeholder-center">{integrations ? <Workflow size={30} /> : <ShieldCheck size={30} />}</span></div><span className="eyebrow">Следующий модуль</span><h2>{integrations ? "Интеграционный контур" : "Центр управления CRM"}</h2><p>{integrations ? "Сервер уже содержит адаптеры LMS и Laravel с fixture-режимом. На этой странице будут статусы подключений, журнал синхронизаций и ручной запуск обмена." : "Backend поддерживает Keycloak, роли manager / head / admin и версионирование workflow. Здесь появятся редактор шаблонов и управление пользователями."}</p><div className="placeholder-status"><span className="status-dot status-active" />API-методы доступны</div></section><section className="panel endpoint-panel"><div className="panel-heading"><div><span className="eyebrow">Backend API</span><h2>Готовые точки</h2></div><LockKeyhole size={20} className="heading-icon" /></div>{(integrations ? ["/integrations", "/integrations/{id}/sync", "/integrations/{id}/logs"] : ["/admin/workflow-templates", "/admin/workflow-versions", "/admin/users"]).map((endpoint) => <div className="endpoint-row" key={endpoint}><code>{endpoint}</code><CheckCircle2 size={16} /></div>)}</section></div></>;
}

function localWorkflowTransition(workflow: WorkflowView, targetId: string, nextStatus: WorkflowView["status"], comment?: string): WorkflowView {
  const currentId = workflow.current_stage_id;
  const nextStates = workflow.stage_states.map((item) => item.stage_id === targetId ? { ...item, state: "active" as StageState } : item.stage_id === currentId ? { ...item, state: "completed" as StageState } : item);
  return { ...workflow, current_stage_id: targetId, status: nextStatus, stage_states: nextStates, available_transitions: workflow.version.transitions.filter((item) => item.from_stage_id === targetId), events: [...workflow.events, { id: `local-${Date.now()}`, from_stage_id: currentId, to_stage_id: targetId, user_id: "u-petrov", event_type: "forward", comment: comment || "Переход выполнен из демо-интерфейса", created_at: new Date().toISOString() }] };
}

function localWorkflowStatus(workflow: WorkflowView, nextStatus: WorkflowView["status"], reason: string): WorkflowView {
  const currentId = workflow.current_stage_id;
  const nextState: StageState = nextStatus === "blocked" ? "blocked" : "active";
  return { ...workflow, status: nextStatus, stage_states: workflow.stage_states.map((item) => item.stage_id === currentId ? { ...item, state: nextState } : item), events: [...workflow.events, { id: `local-${Date.now()}`, from_stage_id: currentId, to_stage_id: currentId, user_id: "u-petrov", event_type: nextStatus === "blocked" ? "blocked" : "unblocked", comment: reason, created_at: new Date().toISOString() }] };
}

export default App;
