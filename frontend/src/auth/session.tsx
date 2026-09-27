/**
 * Текущий пользователь и его права в интерфейсе.
 *
 * Роли, действия и область данных решает сервер (раздел 12 «Решений по
 * бизнес-модели»): /me отдаёт готовый список действий, а клиент по нему
 * только прячет кнопки, которые сотрудник всё равно не сможет применить.
 * Роли не наследуются: руководитель не получает права менеджера,
 * администратор - права руководителя.
 */
import { createContext, useContext, useMemo, type ReactNode } from "react";
import type { DataScope, Me, Role } from "../api/types";
import type { AuthMode } from "./auth";

/** Действия - как в app.services.access.Action на сервере. */
export type Action =
  | "create_interaction"
  | "work_interaction"
  | "assign_responsible"
  | "skip_any_stage"
  | "cancel_interaction"
  | "product_exception"
  | "edit_program_products"
  | "view_reports"
  | "view_statistics"
  | "edit_university_contacts"
  | "propose_university"
  | "manage_universities"
  | "manage_users"
  | "edit_catalog"
  | "import"
  | "edit_templates"
  | "edit_workflow_presentation"
  | "view_audit"
  | "edit_settings"
  | "sync_integrations"
  | "view_integration_log"
  | "resolve_mappings"
  | "view_personal_data";

/** Прежнее имя типа: раньше права выводились из роли на клиенте. */
export type Permission = Action;

export interface Session {
  me: Me;
  mode: AuthMode;
  roles: Role[];
  /** Главная роль: от неё зависит вид главной страницы. */
  primaryRole: Role;
  /** Действующая область бизнес-данных: свои, команда, все или никаких. */
  scope: DataScope;
  /** Есть ли доступ к бизнес-данным (взаимодействиям, отчётам). */
  business: boolean;
  can: (action: Action) => boolean;
}

const SessionContext = createContext<Session | null>(null);

export function SessionProvider({ me, mode, children }: { me: Me; mode: AuthMode; children: ReactNode }) {
  const session = useMemo<Session>(() => {
    const roles = (me.roles || []).filter((role): role is Role => ["manager", "head", "admin"].includes(role));
    const actions = new Set(me.actions || []);
    const primaryRole: Role = roles.includes("head") ? "head" : roles.includes("manager") ? "manager" : "admin";
    const scope = (me.effective_scope || "none") as DataScope;
    return {
      me,
      mode,
      roles,
      primaryRole,
      scope,
      business: scope !== "none",
      can: (action) => actions.has(action),
    };
  }, [me, mode]);
  return <SessionContext.Provider value={session}>{children}</SessionContext.Provider>;
}

export function useSession(): Session {
  const session = useContext(SessionContext);
  if (!session) throw new Error("useSession вне SessionProvider");
  return session;
}
