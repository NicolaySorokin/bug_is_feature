/**
 * Текущий пользователь и его права в интерфейсе.
 *
 * Права повторяют ролевую модель сервера (раздел 8 концепции): кнопки,
 * которые роль всё равно не сможет применить, в интерфейсе не показываются.
 * Решает всё равно сервер - здесь только удобство.
 */
import { createContext, useContext, useMemo, type ReactNode } from "react";
import type { Me, Role } from "../api/types";
import type { AuthMode } from "./auth";

export type Permission =
  | "assign_responsible" // назначать ответственных за вузы и договоры
  | "edit_university" // править справочник вузов
  | "skip_any_stage" // пропускать и обязательные этапы
  | "rename_stage" // корректировать названия статусов процесса
  | "save_layout" // сохранять расположение схемы процесса
  | "sync_integrations" // запускать обмен с LMS и сайтом
  | "view_personal_data" // видеть заявки с ФИО и контактами
  | "manage_users" // пользователи и права
  | "edit_catalog" // справочники программ и продуктов
  | "import" // загрузка каталогов из XLS/XLSX
  | "edit_templates" // шаблоны процессов
  | "view_audit" // журнал изменений
  | "edit_settings" // системные настройки
  | "delete_contract";

const HEAD_PERMISSIONS: Permission[] = [
  "assign_responsible",
  "edit_university",
  "skip_any_stage",
  "rename_stage",
  "save_layout",
  "sync_integrations",
  "view_personal_data",
];
const ADMIN_PERMISSIONS: Permission[] = [
  ...HEAD_PERMISSIONS,
  "manage_users",
  "edit_catalog",
  "import",
  "edit_templates",
  "view_audit",
  "edit_settings",
  "delete_contract",
];

export interface Session {
  me: Me;
  mode: AuthMode;
  roles: Role[];
  /** Главная роль: от неё зависит вид главной страницы. */
  primaryRole: Role;
  can: (permission: Permission) => boolean;
}

const SessionContext = createContext<Session | null>(null);

export function SessionProvider({ me, mode, children }: { me: Me; mode: AuthMode; children: ReactNode }) {
  const session = useMemo<Session>(() => {
    const roles = (me.roles || []).filter((role): role is Role => ["manager", "head", "admin"].includes(role));
    const permissions = new Set<Permission>(
      roles.includes("admin") ? ADMIN_PERMISSIONS : roles.includes("head") ? HEAD_PERMISSIONS : [],
    );
    const primaryRole: Role = roles.includes("admin") ? "admin" : roles.includes("head") ? "head" : "manager";
    return { me, mode, roles, primaryRole, can: (permission) => permissions.has(permission) };
  }, [me, mode]);
  return <SessionContext.Provider value={session}>{children}</SessionContext.Provider>;
}

export function useSession(): Session {
  const session = useContext(SessionContext);
  if (!session) throw new Error("useSession вне SessionProvider");
  return session;
}
