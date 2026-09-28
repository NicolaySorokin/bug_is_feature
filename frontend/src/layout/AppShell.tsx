/**
 * Каркас: боковое меню по ролям, верхняя строка с поиском, уведомлениями
 * о проблемах и меню пользователя.
 */
import { useMutation, useQuery } from "@tanstack/react-query";
import {
  BarChart3,
  Bell,
  BookOpen,
  Check,
  Building2,
  ClipboardList,
  FileSpreadsheet,
  GitBranch,
  Handshake,
  History,
  LayoutDashboard,
  LibraryBig,
  LogOut,
  Menu,
  PlugZap,
  Search,
  Settings,
  UserCog,
  Users,
  X,
  type LucideIcon,
} from "lucide-react";
import { useEffect, useRef, useState } from "react";
import { Link, NavLink, Outlet, useLocation, useNavigate, useNavigationType } from "react-router-dom";
import { getAlerts, listInteractions, listUniversities, markAlertsRead } from "../api/endpoints";
import { keys, queryClient } from "../api/queries";
import type { Alert } from "../api/types";
import { logout } from "../auth/auth";
import { useSession, type Action, type Session } from "../auth/session";
import { RtLogo } from "../components/Brand";
import { useToast } from "../components/Toasts";
import { Avatar, IconButton } from "../components/ui";
import { countLabel } from "../lib/format";
import { ROLE_SHORT } from "../lib/labels";

interface NavItem {
  to: string;
  label: string;
  icon: LucideIcon;
  /** Пункт виден, если есть хотя бы одно из действий. */
  any?: Action[];
  /** Пункт виден только при доступе к бизнес-данным. */
  business?: boolean;
  end?: boolean;
}

const WORK: NavItem[] = [
  { to: "/", label: "Главная", icon: LayoutDashboard, end: true },
  { to: "/interactions", label: "Взаимодействия", icon: Handshake, business: true },
  { to: "/universities", label: "Вузы", icon: Building2 },
  { to: "/reports", label: "Отчёты и статистика", icon: BarChart3, any: ["view_reports", "view_statistics"] },
  // Технический раздел: журнал обмена и сопоставление - не для бизнес-ролей (пункт 28).
  {
    to: "/integrations",
    label: "LMS и сайт",
    icon: PlugZap,
    any: ["view_integration_log", "sync_integrations", "resolve_mappings"],
  },
];

const ADMIN: NavItem[] = [
  { to: "/admin/users", label: "Пользователи и права", icon: Users, any: ["manage_users"] },
  {
    to: "/admin/catalog",
    label: "Справочники",
    icon: LibraryBig,
    any: ["edit_catalog", "edit_program_products", "edit_contract_templates"],
  },
  { to: "/admin/imports", label: "Загрузка из Excel", icon: FileSpreadsheet, any: ["import"] },
  { to: "/admin/workflows", label: "Рабочие процессы", icon: GitBranch, any: ["edit_templates"] },
  { to: "/admin/audit", label: "Журнал изменений", icon: History, any: ["view_audit"] },
  { to: "/admin/settings", label: "Настройки", icon: Settings, any: ["edit_settings"] },
];

function visible(item: NavItem, session: Session): boolean {
  if (item.business && !session.business) return false;
  return !item.any || item.any.some((action) => session.can(action));
}

function useOutsideClose(open: boolean, close: () => void) {
  const ref = useRef<HTMLDivElement>(null);
  useEffect(() => {
    if (!open) return;
    const onPointer = (event: PointerEvent) => {
      if (!ref.current?.contains(event.target as Node)) close();
    };
    const onKey = (event: KeyboardEvent) => {
      if (event.key === "Escape") close();
    };
    document.addEventListener("pointerdown", onPointer);
    document.addEventListener("keydown", onKey);
    return () => {
      document.removeEventListener("pointerdown", onPointer);
      document.removeEventListener("keydown", onKey);
    };
  }, [open, close]);
  return ref;
}

function Sidebar({ onNavigate, alerts }: { onNavigate: () => void; alerts: number }) {
  const session = useSession();
  const work = WORK.filter((item) => visible(item, session));
  const admin = ADMIN.filter((item) => visible(item, session));
  const link = (item: NavItem) => (
    <NavLink key={item.to} to={item.to} end={item.end} className="nav-link" onClick={onNavigate}>
      <item.icon size={18} />
      <span>{item.label}</span>
      {item.to === "/" && alerts > 0 && (
        <span className="nav-link__badge" title="Проблемы, требующие внимания">
          {alerts}
        </span>
      )}
    </NavLink>
  );
  return (
    <aside className="sidebar" aria-label="Главное меню">
      <Link to="/" className="sidebar__brand" onClick={onNavigate} aria-label="Ростелеком ИТ Школа - на главную">
        <RtLogo height={40} />
        <span className="sidebar__product">Взаимодействие с вузами</span>
      </Link>
      <nav className="sidebar__nav">
        {work.map(link)}
        {admin.length > 0 && (
          <>
            <div className="nav-group__title">Администрирование</div>
            {admin.map(link)}
          </>
        )}
        <div className="nav-group__title">Помощь</div>
        {link({ to: "/help", label: "Руководства", icon: BookOpen })}
      </nav>
    </aside>
  );
}

/** Быстрый поиск взаимодействий (в том числе по номеру договора) и вузов. */
function QuickSearch({ open, onClose }: { open: boolean; onClose: () => void }) {
  const { business } = useSession();
  const [query, setQuery] = useState("");
  const [focused, setFocused] = useState(false);
  const [debounced, setDebounced] = useState("");
  const navigate = useNavigate();
  const ref = useOutsideClose(focused, () => setFocused(false));

  useEffect(() => {
    const timer = window.setTimeout(() => setDebounced(query.trim()), 250);
    return () => window.clearTimeout(timer);
  }, [query]);

  const enabled = debounced.length >= 2;
  const interactions = useQuery({
    queryKey: ["search", "interactions", debounced],
    queryFn: () => listInteractions({ search: debounced, limit: 6 }),
    enabled: enabled && business,
  });
  const universities = useQuery({
    queryKey: ["search", "universities", debounced],
    queryFn: () => listUniversities({ search: debounced, limit: 6 }),
    enabled,
  });

  const go = (path: string) => {
    setQuery("");
    setFocused(false);
    onClose();
    navigate(path);
  };

  const showResults = focused && enabled;
  return (
    <div className={`topbar__search ${open ? "topbar__search--open" : ""}`} ref={ref}>
      <div className="search-input" style={{ width: "100%" }}>
        <Search size={16} />
        <input
          className="control"
          type="search"
          placeholder={business ? "Найти вуз, взаимодействие или договор" : "Найти вуз"}
          aria-label="Поиск по вузам и взаимодействиям"
          value={query}
          autoFocus={open}
          onFocus={() => setFocused(true)}
          onChange={(event) => {
            setQuery(event.target.value);
            setFocused(true);
          }}
          onKeyDown={(event) => {
            if (event.key === "Enter" && query.trim())
              go(
                business
                  ? `/interactions?search=${encodeURIComponent(query.trim())}`
                  : `/universities?search=${encodeURIComponent(query.trim())}`,
              );
          }}
        />
      </div>
      {open && <IconButton icon={X} label="Закрыть поиск" onClick={onClose} />}
      {showResults && (
        <div className="menu search-results">
          <div className="search-results__group">Вузы</div>
          {(universities.data?.items || []).map((item) => (
            <button key={item.id} type="button" className="menu__item" onClick={() => go(`/universities/${item.id}`)}>
              <Building2 size={16} />
              <span>
                {item.short_name || item.name}
                <small className="muted" style={{ display: "block", fontWeight: 400 }}>
                  {item.city || "—"} ·{" "}
                  {countLabel(item.interactions_count || 0, ["взаимодействие", "взаимодействия", "взаимодействий"])}
                </small>
              </span>
            </button>
          ))}
          {universities.data && universities.data.items.length === 0 && <div className="menu__item muted">Не найдено</div>}
          {business && (
            <>
              <div className="search-results__group">Взаимодействия</div>
              {(interactions.data?.items || []).map((item) => (
                <button key={item.id} type="button" className="menu__item" onClick={() => go(`/interactions/${item.id}`)}>
                  <Handshake size={16} />
                  <span>
                    {item.title || item.university.short_name || item.university.name}
                    <small className="muted" style={{ display: "block", fontWeight: 400 }}>
                      {item.university.short_name || item.university.name}
                      {item.contract ? ` · договор ${item.contract.number}` : ""} ·{" "}
                      {item.stage?.stage_name || "процесс не запущен"}
                    </small>
                  </span>
                </button>
              ))}
              {interactions.data && interactions.data.items.length === 0 && <div className="menu__item muted">Не найдено</div>}
              <button
                type="button"
                className="menu__item"
                onClick={() => go(`/interactions?search=${encodeURIComponent(query.trim())}`)}
              >
                <Search size={16} /> Все взаимодействия по запросу «{query.trim()}»
              </button>
            </>
          )}
        </div>
      )}
    </div>
  );
}

/**
 * Колокольчик: уведомления о проблемах по своим взаимодействиям.
 *
 * Уведомление можно отметить прочитанным (или все сразу) - оно уходит со
 * счётчика и опускается вниз списка. Переход по уведомлению тоже его читает.
 * Проблема при этом не исчезает: она остаётся в «Требует внимания» на главной,
 * пока её не решат, а если станет серьёзнее - уведомление снова будет новым.
 */
function AlertsMenu() {
  const [open, setOpen] = useState(false);
  const ref = useOutsideClose(open, () => setOpen(false));
  const toast = useToast();
  const alerts = useQuery({ queryKey: keys.alerts, queryFn: () => getAlerts({ limit: 100 }), refetchInterval: 5 * 60_000 });
  const items = alerts.data || [];
  const unread = items.filter((item) => !item.is_read);
  const ordered = [...unread, ...items.filter((item) => item.is_read)];

  const markRead = useMutation({
    mutationFn: markAlertsRead,
    // Отметка видна сразу, не дожидаясь ответа сервера.
    onMutate: (selected: string[] | null) =>
      queryClient.setQueryData<Alert[]>(keys.alerts, (current) =>
        current?.map((item) => (!selected || selected.includes(item.key) ? { ...item, is_read: true } : item)),
      ),
    onError: (error) => toast.error(error, "Не удалось отметить уведомления"),
    onSettled: () => {
      void queryClient.invalidateQueries({ queryKey: keys.alerts });
      void queryClient.invalidateQueries({ queryKey: keys.dashboard });
    },
  });

  return (
    <div style={{ position: "relative" }} ref={ref}>
      <IconButton
        icon={Bell}
        label={`Требует внимания: ${countLabel(unread.length, ["новое", "новых", "новых"])}`}
        badge={unread.length}
        expanded={open}
        onClick={() => setOpen((value) => !value)}
      />
      {open && (
        <div className="menu alerts-panel">
          <div className="alerts-panel__head">
            <div className="alerts-panel__title">
              <strong>Требует внимания</strong>
              <span className="muted">
                {unread.length ? countLabel(unread.length, ["новое", "новых", "новых"]) : "новых нет"}
              </span>
            </div>
            {unread.length > 0 && (
              <button type="button" className="link-btn" onClick={() => markRead.mutate(null)}>
                Прочитать все
              </button>
            )}
          </div>
          {items.length === 0 && <div className="state">Проблем нет - всё идёт по плану.</div>}
          {ordered.slice(0, 30).map((item) => {
            const body = (
              <>
                <Bell size={16} className={`alert-item__icon alert-item__icon--${item.severity}`} />
                <span className="alert-item__text">
                  <strong>{item.kind_label}</strong>
                  <span>{item.message}</span>
                  <small title={item.university_full_name || undefined}>
                    {[item.university_name, item.contract_number, item.manager_name].filter(Boolean).join(" · ")}
                  </small>
                </span>
              </>
            );
            const target = item.interaction_id ? `/interactions/${item.interaction_id}` : item.link;
            return (
              <div key={item.key} className={`alert-item ${item.is_read ? "alert-item--read" : ""}`}>
                {target ? (
                  <Link
                    className="alert-item__link"
                    to={target}
                    onClick={() => {
                      if (!item.is_read) markRead.mutate([item.key]);
                      setOpen(false);
                    }}
                  >
                    {body}
                  </Link>
                ) : (
                  <div className="alert-item__link">{body}</div>
                )}
                {!item.is_read && (
                  <button
                    type="button"
                    className="icon-btn alert-item__read"
                    aria-label={`Отметить прочитанным: ${item.kind_label}`}
                    title="Отметить прочитанным"
                    onClick={() => markRead.mutate([item.key])}
                  >
                    <Check size={16} />
                  </button>
                )}
              </div>
            );
          })}
          {unread.length < items.length && (
            <p className="alerts-panel__note">Прочитанные остаются на главной в «Требует внимания», пока проблема не решена.</p>
          )}
        </div>
      )}
    </div>
  );
}

function UserMenu() {
  const { me, roles, mode } = useSession();
  const [open, setOpen] = useState(false);
  const ref = useOutsideClose(open, () => setOpen(false));
  const roleText = roles.map((role) => ROLE_SHORT[role]).join(", ") || "Нет ролей";
  return (
    <div style={{ position: "relative" }} ref={ref}>
      <button type="button" className="user-chip" aria-expanded={open} onClick={() => setOpen((value) => !value)}>
        <Avatar name={me.full_name} />
        <span className="user-chip__text">
          <strong>{me.full_name}</strong>
          <small>{roleText}</small>
        </span>
      </button>
      {open && (
        <div className="menu">
          <div className="menu__head">
            <Avatar name={me.full_name} large />
            <div className="stack-s" style={{ gap: 2, minWidth: 0 }}>
              <strong>{me.full_name}</strong>
              <small className="muted">{me.email || me.username}</small>
              <small className="muted">{roleText}</small>
            </div>
          </div>
          <Link className="menu__item" to="/account" onClick={() => setOpen(false)}>
            <UserCog size={16} /> Учётная запись
          </Link>
          {mode === "dev" && (
            <div className="menu__item muted" style={{ fontWeight: 400, fontSize: 12 }}>
              <ClipboardList size={16} /> Режим разработки: вход без Keycloak
            </div>
          )}
          <button type="button" className="menu__item" onClick={() => void logout()}>
            <LogOut size={16} /> Выйти
          </button>
        </div>
      )}
    </div>
  );
}

export function AppShell() {
  const [navOpen, setNavOpen] = useState(false);
  const [searchOpen, setSearchOpen] = useState(false);
  const location = useLocation();
  const navigationType = useNavigationType();
  const alerts = useQuery({ queryKey: keys.alerts, queryFn: () => getAlerts({ limit: 100 }), refetchInterval: 5 * 60_000 });

  // Новая страница открывается сверху; «назад» возвращает браузер сам.
  useEffect(() => {
    if (navigationType !== "POP") window.scrollTo({ top: 0 });
    setNavOpen(false);
  }, [location.pathname, navigationType]);

  return (
    <div className={`shell ${navOpen ? "shell--nav-open" : ""}`}>
      <Sidebar
        onNavigate={() => setNavOpen(false)}
        alerts={(alerts.data || []).filter((item) => item.severity === "critical" && !item.is_read).length}
      />
      {navOpen && <div className="scrim" onClick={() => setNavOpen(false)} />}
      <div className="main">
        <header className="topbar">
          <IconButton className="topbar__burger" icon={Menu} label="Открыть меню" onClick={() => setNavOpen(true)} />
          <QuickSearch open={searchOpen} onClose={() => setSearchOpen(false)} />
          <div className="topbar__actions">
            <IconButton className="topbar__burger" icon={Search} label="Поиск" onClick={() => setSearchOpen(true)} />
            <AlertsMenu />
            <UserMenu />
          </div>
        </header>
        <main id="content">
          <Outlet />
        </main>
      </div>
    </div>
  );
}
