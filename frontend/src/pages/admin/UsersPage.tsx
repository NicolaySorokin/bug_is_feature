/**
 * Пользователи и права (раздел 12 «Решений по бизнес-модели»).
 *
 * Роль, функциональные права и область данных разделены:
 *
 * * роли живут в Keycloak и не наследуются - совмещение задаётся
 *   несколькими ролями явно;
 * * дополнительные права (запуск обмена, журнал обмена, персональные
 *   данные студентов, представление схемы процесса) выдаются отдельно;
 * * область данных (свои, команда, все, никаких) по умолчанию следует из
 *   ролей; расширить её можно с основанием и, если нужно, со сроком;
 * * точечный доступ к вузу - со сроком, основанием и отметкой, кто выдал;
 *   отзыв не удаляет запись.
 */
import { keepPreviousData, useQuery } from "@tanstack/react-query";
import { KeyRound, RefreshCw, ShieldCheck, UserPlus, X } from "lucide-react";
import { useEffect, useMemo, useState } from "react";
import {
  createUser,
  getUser,
  grantUniversity,
  listUsers,
  resetPassword,
  revokeUniversity,
  syncRoles,
  updateUser,
} from "../../api/endpoints";
import { useApiMutation } from "../../api/mutations";
import { keys, queryClient, useLabel, useUniversities, useUsers } from "../../api/queries";
import type { DataScope, Role, User, UserPermission } from "../../api/types";
import { useSession } from "../../auth/session";
import { DataTable, type Column } from "../../components/DataTable";
import { Drawer, Modal } from "../../components/Modal";
import {
  Avatar,
  Button,
  Card,
  Checkbox,
  DescriptionList,
  EmptyState,
  ErrorState,
  Field,
  Hint,
  Loading,
  PageHeader,
  SearchInput,
  SelectField,
  StatusBadge,
  Switch,
  Tag,
  TextField,
} from "../../components/ui";
import { formatDate, formatDateTime } from "../../lib/format";
import { usePageTitle } from "../../lib/usePageTitle";

const ROLES: Role[] = ["manager", "head", "admin"];
const SCOPES: DataScope[] = ["default", "own", "team", "all", "none"];
const PERMISSIONS: UserPermission[] = [
  "view_personal_data",
  "sync_integrations",
  "view_integration_log",
  "edit_workflow_presentation",
];

// Политика паролей реалма Keycloak: короче Keycloak пароль не примет.
const PASSWORD_MIN_LENGTH = 12;
const PASSWORD_HINT = "Не короче 12 знаков: строчные и заглавные буквы, цифры, не совпадает с логином";
const ROLE_HINTS: Record<Role, string> = {
  manager: "ведёт свои взаимодействия с вузами",
  head: "команда, назначение ответственных, исключения, проверка вузов",
  admin: "пользователи, справочники, шаблоны, интеграции; без бизнес-данных",
};
const SCOPE_HINTS: Record<DataScope, string> = {
  default: "по ролям: менеджер - свои, руководитель - команда, администратор - никаких",
  own: "свои взаимодействия, свои вузы и открытые ему вузы",
  team: "плюс взаимодействия команды и те, что ждут ответственного",
  all: "все бизнес-данные организации",
  none: "только административные функции",
};

/** Конец выбранного дня в UTC - срок временного доступа. */
function endOfDay(value: string): string | null {
  return value ? new Date(`${value}T23:59:59`).toISOString() : null;
}

function refreshUsers() {
  void queryClient.invalidateQueries({ queryKey: keys.users });
  void queryClient.invalidateQueries({ queryKey: keys.directory });
  void queryClient.invalidateQueries({ queryKey: ["user"] });
  void queryClient.invalidateQueries({ queryKey: ["users-page"] });
}

function RolesPicker({ value, onChange }: { value: Role[]; onChange: (value: Role[]) => void }) {
  const label = useLabel();
  return (
    <Field
      label="Роли"
      hint="Роли не наследуются: руководителю, который сам ведёт вузы, нужна и роль менеджера. Хранятся в Keycloak, действуют со следующего входа"
    >
      <div className="stack-s">
        {ROLES.map((role) => (
          <Checkbox
            key={role}
            label={
              <span>
                {label("role", role)} <small className="muted">— {ROLE_HINTS[role]}</small>
              </span>
            }
            checked={value.includes(role)}
            onChange={(checked) => onChange(ROLES.filter((item) => (item === role ? checked : value.includes(item))))}
          />
        ))}
        {/* Раздел 12 решений: администратор по умолчанию бизнес-данных не видит,
            служебный доступ - временный. Совмещение возможно, но осознанно. */}
        {value.includes("admin") && (value.includes("manager") || value.includes("head")) && (
          <span className="field__error">
            Администратор с бизнес-ролью постоянно работает с взаимодействиями и вузами. Если доступ нужен на время, вместо роли
            выдайте временную область данных.
          </span>
        )}
      </div>
    </Field>
  );
}

/** Точечный доступ к вузам: выдача со сроком и основанием, отзыв с отметкой. */
function Grants({ userId, grants }: { userId: string; grants: NonNullable<import("../../api/types").UserDetail["grants"]> }) {
  const universities = useUniversities();
  const [universityId, setUniversityId] = useState("");
  const [reason, setReason] = useState("");
  const [expires, setExpires] = useState("");
  const grant = useApiMutation(
    () => grantUniversity(userId, { university_id: universityId, reason: reason.trim(), expires_at: endOfDay(expires) }),
    {
      success: "Доступ к вузу открыт",
      onSuccess: (saved) => {
        queryClient.setQueryData(["user", userId], saved);
        setUniversityId("");
        setReason("");
        setExpires("");
        refreshUsers();
      },
    },
  );
  const revoke = useApiMutation((id: string) => revokeUniversity(userId, id), {
    success: "Доступ отозван",
    onSuccess: (saved) => {
      queryClient.setQueryData(["user", userId], saved);
      refreshUsers();
    },
  });
  const active = grants.filter((item) => item.is_active);
  const past = grants.filter((item) => !item.is_active);
  return (
    <Card title="Доступ к отдельным вузам" description="Сверх области данных - например, на время отпуска коллеги.">
      <div className="stack">
        {active.length === 0 && <p className="muted">Открытых вузов нет.</p>}
        {active.map((item) => (
          <div key={item.university_id} className="row-between" style={{ alignItems: "flex-start" }}>
            <div className="cell-title">
              <strong>{item.university_name}</strong>
              <small>
                {item.reason || "без основания"} · {item.expires_at ? `до ${formatDate(item.expires_at)}` : "бессрочно"}
                {item.granted_by ? ` · выдал ${item.granted_by.full_name}` : ""}
              </small>
            </div>
            <Button
              variant="ghost"
              size="s"
              icon={X}
              loading={revoke.isPending}
              onClick={() => revoke.mutate(item.university_id)}
            >
              Отозвать
            </Button>
          </div>
        ))}
        {past.length > 0 && (
          <details>
            <summary className="muted">Отозванные и истёкшие: {past.length}</summary>
            <div className="stack-s" style={{ marginTop: 8 }}>
              {past.map((item) => (
                <small key={item.university_id} className="muted">
                  {item.university_name} ·{" "}
                  {item.revoked_at
                    ? `отозван ${formatDate(item.revoked_at)}${item.revoked_by ? ` (${item.revoked_by.full_name})` : ""}`
                    : `истёк ${formatDate(item.expires_at)}`}
                </small>
              ))}
            </div>
          </details>
        )}
        <div className="form-grid" style={{ borderTop: "1px solid var(--line)", paddingTop: 12 }}>
          <SelectField
            className="span-2"
            label="Вуз"
            value={universityId}
            onChange={setUniversityId}
            placeholder="Выберите вуз"
            options={(universities.data || []).map((item) => ({ value: item.id, label: item.short_name || item.name }))}
          />
          <TextField
            label="Основание"
            required
            value={reason}
            onChange={setReason}
            maxLength={1000}
            placeholder="Замещает коллегу"
          />
          <TextField label="До (включительно)" type="date" value={expires} onChange={setExpires} hint="Пусто - бессрочно" />
          <div className="span-2">
            <Button
              variant="secondary"
              disabled={!universityId || !reason.trim()}
              loading={grant.isPending}
              onClick={() => grant.mutate(undefined)}
            >
              Открыть доступ
            </Button>
          </div>
        </div>
      </div>
    </Card>
  );
}

function UserDrawer({ userId, onClose }: { userId: string | null; onClose: () => void }) {
  const { me, mode } = useSession();
  const label = useLabel();
  const everyone = useUsers();
  const user = useQuery({ queryKey: ["user", userId], queryFn: () => getUser(userId!), enabled: Boolean(userId) });
  const [roles, setRoles] = useState<Role[]>([]);
  const [fullName, setFullName] = useState("");
  const [email, setEmail] = useState("");
  const [headId, setHeadId] = useState("");
  const [scope, setScope] = useState<DataScope>("default");
  const [scopeReason, setScopeReason] = useState("");
  const [scopeExpires, setScopeExpires] = useState("");
  const [permissions, setPermissions] = useState<UserPermission[]>([]);
  const [active, setActive] = useState(true);
  const [password, setPassword] = useState<string | null>(null);

  useEffect(() => {
    if (!user.data) return;
    setRoles((user.data.roles || []).filter((role): role is Role => ROLES.includes(role as Role)));
    setFullName(user.data.full_name);
    setEmail(user.data.email || "");
    setHeadId(user.data.head_id || "");
    setScope(user.data.data_scope || "default");
    setScopeReason(user.data.data_scope_reason || "");
    setScopeExpires(user.data.data_scope_expires_at ? user.data.data_scope_expires_at.slice(0, 10) : "");
    setPermissions((user.data.permissions || []) as UserPermission[]);
    setActive(user.data.is_active);
  }, [user.data]);

  const heads = useMemo(
    () =>
      (everyone.data || [])
        .filter((item) => item.is_active && (item.roles || []).includes("head") && item.id !== userId)
        .map((item) => ({ value: item.id, label: item.full_name })),
    [everyone.data, userId],
  );

  const save = useApiMutation(
    () =>
      updateUser(userId!, {
        roles,
        full_name: fullName.trim(),
        email: email.trim() || null,
        head_id: headId || null,
        data_scope: scope,
        data_scope_reason: scope === "default" ? null : scopeReason.trim() || null,
        data_scope_expires_at: scope === "default" ? null : endOfDay(scopeExpires),
        permissions,
        is_active: active,
      }),
    {
      success: "Права сохранены",
      onSuccess: (saved) => {
        queryClient.setQueryData(["user", userId], saved);
        refreshUsers();
      },
    },
  );
  // Администратор выдаёт только временный пароль: постоянный сотрудник
  // придумывает сам при первом входе, и его не знает никто, кроме него.
  const reset = useApiMutation((value: string) => resetPassword(userId!, value), {
    success: "Временный пароль задан: при входе сотрудник придумает свой",
    onSuccess: () => setPassword(null),
  });

  const self = userId === me.id;
  const managed = new Set(user.data?.managed_university_ids || []);
  const needsReason = scope !== "default" && !scopeReason.trim();

  return (
    <Drawer
      open={userId !== null}
      onClose={onClose}
      title={user.data?.full_name || "Пользователь"}
      description={user.data ? `${user.data.username}${user.data.email ? ` · ${user.data.email}` : ""}` : undefined}
      footer={
        <>
          <Button variant="outline" onClick={onClose}>
            Закрыть
          </Button>
          <Button
            loading={save.isPending}
            // Снять с себя роль администратора сервер не даст - кнопку не предлагаем.
            disabled={!user.data || roles.length === 0 || !fullName.trim() || needsReason || (self && !roles.includes("admin"))}
            onClick={() => save.mutate(undefined)}
          >
            Сохранить
          </Button>
        </>
      }
    >
      {user.isPending ? (
        <Loading />
      ) : user.isError ? (
        <ErrorState error={user.error} />
      ) : (
        <div className="stack">
          <DescriptionList
            items={[
              ["Последняя активность", formatDateTime(user.data.last_seen_at, "не заходил")],
              ["В системе с", formatDateTime(user.data.created_at)],
              ["Действующая область", label("data_scope", user.data.effective_scope || "none")],
              ["Ведёт взаимодействий", user.data.interactions_count ?? 0],
              ["Менеджер по умолчанию у вузов", managed.size ? `${managed.size}` : "нет"],
              ["Команда", (user.data.team || []).length ? (user.data.team || []).map((item) => item.full_name).join(", ") : null],
            ]}
          />
          <TextField label="ФИО" value={fullName} onChange={setFullName} maxLength={255} required />
          <TextField label="Почта" type="email" value={email} onChange={setEmail} maxLength={255} />
          <RolesPicker value={roles} onChange={setRoles} />
          {self && !roles.includes("admin") && <span className="field__error">Нельзя снять с себя роль администратора</span>}
          <SelectField
            label="Руководитель"
            value={headId}
            onChange={setHeadId}
            placeholder="Не указан"
            options={heads}
            hint="Команда руководителя - его область данных «Команда» и кого он может назначать"
          />
          <Card title="Область данных" description={SCOPE_HINTS[scope]}>
            <div className="stack">
              <SelectField
                label="Какие взаимодействия и вузы видит"
                value={scope}
                onChange={(value) => setScope(value as DataScope)}
                options={SCOPES.map((value) => ({ value, label: label("data_scope", value) }))}
              />
              {scope !== "default" && (
                <div className="form-grid">
                  <TextField
                    className="span-2"
                    label="Основание"
                    required
                    value={scopeReason}
                    onChange={setScopeReason}
                    maxLength={1000}
                    placeholder="Например: подготовка годового отчёта"
                    error={needsReason ? "Укажите основание" : undefined}
                  />
                  <TextField
                    label="Действует до"
                    type="date"
                    value={scopeExpires}
                    onChange={setScopeExpires}
                    hint="Пусто - бессрочно; по истечении - область по ролям"
                  />
                </div>
              )}
            </div>
          </Card>
          <Field label="Дополнительные права" hint="Из роли не следуют - выдаются отдельно">
            <div className="stack-s">
              {PERMISSIONS.map((permission) => (
                <Checkbox
                  key={permission}
                  label={label("permission", permission)}
                  checked={permissions.includes(permission)}
                  onChange={(checked) =>
                    setPermissions((current) =>
                      checked ? [...current, permission] : current.filter((item) => item !== permission),
                    )
                  }
                />
              ))}
            </div>
          </Field>
          <Grants userId={userId!} grants={user.data.grants || []} />
          <Switch label="Учётная запись активна" checked={active} disabled={self} onChange={setActive} />
          {mode === "keycloak" && (
            <Card title="Пароль">
              {password === null ? (
                <Button variant="outline" icon={KeyRound} onClick={() => setPassword("")}>
                  Выдать временный пароль
                </Button>
              ) : (
                <div className="stack-s">
                  <TextField
                    label="Временный пароль"
                    type="password"
                    value={password}
                    onChange={setPassword}
                    hint={PASSWORD_HINT + "; при входе Keycloak попросит придумать свой"}
                    autoComplete="new-password"
                  />
                  <div className="row">
                    <Button variant="outline" onClick={() => setPassword(null)}>
                      Отмена
                    </Button>
                    <Button
                      loading={reset.isPending}
                      disabled={password.length < PASSWORD_MIN_LENGTH}
                      onClick={() => reset.mutate(password)}
                    >
                      Задать
                    </Button>
                  </div>
                </div>
              )}
            </Card>
          )}
        </div>
      )}
    </Drawer>
  );
}

function CreateUserModal({ open, onClose }: { open: boolean; onClose: () => void }) {
  const { mode } = useSession();
  const [username, setUsername] = useState("");
  const [fullName, setFullName] = useState("");
  const [email, setEmail] = useState("");
  const [roles, setRoles] = useState<Role[]>(["manager"]);
  const [password, setPassword] = useState("");
  useEffect(() => {
    if (open) {
      setUsername("");
      setFullName("");
      setEmail("");
      setRoles(["manager"]);
      setPassword("");
    }
  }, [open]);
  const create = useApiMutation(
    () =>
      createUser({
        username: username.trim(),
        full_name: fullName.trim(),
        email: email.trim() || null,
        roles,
        password: mode === "keycloak" ? password : null,
        data_scope: "default",
      }),
    {
      success: (user) => `Пользователь ${user.username} создан`,
      onSuccess: () => {
        refreshUsers();
        onClose();
      },
    },
  );
  const valid =
    /^[a-zA-Z0-9._-]{3,}$/.test(username.trim()) &&
    fullName.trim() &&
    roles.length > 0 &&
    (mode !== "keycloak" || password.length >= PASSWORD_MIN_LENGTH);
  return (
    <Modal
      open={open}
      onClose={onClose}
      title="Новый пользователь"
      description={
        mode === "keycloak"
          ? "Учётная запись создаётся в Keycloak с временным паролем - при первом входе пользователь задаст свой."
          : "Режим разработки: учётная запись создаётся без Keycloak."
      }
      footer={
        <>
          <Button variant="outline" onClick={onClose}>
            Отмена
          </Button>
          <Button loading={create.isPending} disabled={!valid} onClick={() => create.mutate(undefined)}>
            Создать
          </Button>
        </>
      }
    >
      <div className="stack">
        <TextField
          label="Логин"
          required
          value={username}
          onChange={setUsername}
          hint="Латиница, цифры, точка, дефис"
          maxLength={100}
          autoComplete="off"
        />
        <TextField label="ФИО" required value={fullName} onChange={setFullName} maxLength={255} />
        <TextField label="Почта" type="email" value={email} onChange={setEmail} maxLength={255} />
        <RolesPicker value={roles} onChange={setRoles} />
        {mode === "keycloak" && (
          <TextField
            label="Временный пароль"
            type="password"
            required
            value={password}
            onChange={setPassword}
            hint={PASSWORD_HINT}
            autoComplete="new-password"
          />
        )}
      </div>
    </Modal>
  );
}

export default function UsersPage() {
  const label = useLabel();
  const { mode } = useSession();
  const [search, setSearch] = useState("");
  const [role, setRole] = useState("");
  const [status, setStatus] = useState("");
  const [selected, setSelected] = useState<string | null>(null);
  const [creating, setCreating] = useState(false);
  const [debounced, setDebounced] = useState("");
  usePageTitle("Пользователи и права");

  useEffect(() => {
    const timer = window.setTimeout(() => setDebounced(search.trim()), 300);
    return () => window.clearTimeout(timer);
  }, [search]);

  const query = {
    search: debounced || undefined,
    role: role || undefined,
    is_active: status === "" ? undefined : status === "true",
    limit: 500,
  };
  const users = useQuery({ queryKey: ["users-page", query], queryFn: () => listUsers(query), placeholderData: keepPreviousData });
  const names = useMemo(
    () => Object.fromEntries((users.data?.items || []).map((item) => [item.id, item.full_name])),
    [users.data],
  );

  const sync = useApiMutation(() => syncRoles(), {
    success: (result) =>
      `Роли сверены с Keycloak: ${result.users_total} пользователей, добавлено ${result.users_created}, обновлено ${result.users_updated}`,
    onSuccess: refreshUsers,
  });

  const columns: Column<User>[] = [
    {
      key: "name",
      title: "Пользователь",
      primary: true,
      render: (row) => (
        <div className="row" style={{ flexWrap: "nowrap" }}>
          <Avatar name={row.full_name} />
          <div className="cell-title">
            <button type="button" className="link-btn" onClick={() => setSelected(row.id)}>
              {row.full_name}
            </button>
            <small>
              {row.username}
              {row.email ? ` · ${row.email}` : ""}
            </small>
          </div>
        </div>
      ),
    },
    {
      key: "roles",
      title: "Роли",
      render: (row) => (
        <div className="tags">
          {(row.roles || []).length === 0 && <span className="muted">Нет ролей</span>}
          {(row.roles || []).map((item) => (
            <span key={item} className={`tag ${item === "admin" ? "tag--accent" : ""}`}>
              {label("role", item)}
            </span>
          ))}
        </div>
      ),
    },
    {
      key: "scope",
      title: "Область данных",
      render: (row) =>
        row.data_scope && row.data_scope !== "default" ? (
          <Tag tone="accent">{label("data_scope", row.data_scope)}</Tag>
        ) : (
          <span className="muted">по ролям</span>
        ),
    },
    {
      key: "extra",
      title: "Доп. права",
      render: (row) => {
        const names = (row.permissions || []).map((item) => label("permission", item));
        if (names.length === 0) return <span className="muted">—</span>;
        return (
          <Hint
            title="Дополнительные права"
            content={
              <ul className="hint-list">
                {names.map((name) => (
                  <li key={name}>{name}</li>
                ))}
              </ul>
            }
            label={`Дополнительные права: ${names.join(", ")}`}
          >
            <span className="perm-count">
              <ShieldCheck size={14} aria-hidden="true" />
              {names.length}
            </span>
          </Hint>
        );
      },
    },
    {
      key: "head",
      title: "Руководитель",
      render: (row) => (row.head_id ? names[row.head_id] || "—" : <span className="muted">—</span>),
    },
    {
      key: "status",
      title: "Состояние",
      render: (row) =>
        row.is_active ? <StatusBadge tone="success">Активен</StatusBadge> : <StatusBadge tone="error">Отключён</StatusBadge>,
    },
  ];

  return (
    <div className="page">
      <PageHeader
        title="Пользователи и права"
        description="Роль задаёт действия, область данных - какие взаимодействия видны, отдельные права выдаются сверх роли."
        actions={
          <>
            {mode === "keycloak" && (
              <Button variant="outline" icon={RefreshCw} loading={sync.isPending} onClick={() => sync.mutate(undefined)}>
                Сверить с Keycloak
              </Button>
            )}
            <Button icon={UserPlus} onClick={() => setCreating(true)}>
              Добавить
            </Button>
          </>
        }
      />
      <div className="toolbar">
        <Field label="Поиск" className="field--grow">
          <SearchInput value={search} onChange={setSearch} placeholder="ФИО, логин или почта" />
        </Field>
        <SelectField
          label="Роль"
          value={role}
          onChange={setRole}
          placeholder="Все"
          options={ROLES.map((value) => ({ value, label: label("role", value) }))}
        />
        <SelectField
          label="Состояние"
          value={status}
          onChange={setStatus}
          placeholder="Все"
          options={[
            { value: "true", label: "Активные" },
            { value: "false", label: "Отключённые" },
          ]}
        />
      </div>
      <Card flush>
        {users.isPending ? (
          <Loading />
        ) : users.isError ? (
          <ErrorState error={users.error} onRetry={() => void users.refetch()} />
        ) : (
          <DataTable
            caption="Пользователи"
            columns={columns}
            rows={users.data.items}
            rowKey={(row) => row.id}
            onRowClick={(row) => setSelected(row.id)}
            refreshing={users.isFetching && users.isPlaceholderData}
            empty={<EmptyState title="Никого не нашли" />}
          />
        )}
      </Card>
      <UserDrawer userId={selected} onClose={() => setSelected(null)} />
      <CreateUserModal open={creating} onClose={() => setCreating(false)} />
    </div>
  );
}
