/**
 * Пользователи и права (раздел «Роли» ТЗ: администратор управляет правами
 * и доступом к данным).
 *
 * Роли живут в Keycloak: изменение здесь сразу записывается туда, так что
 * источник прав один. Доступ к данным: «свои вузы» (где сотрудник
 * ответственный, плюс открытые ему вузы) или «все договоры».
 */
import { keepPreviousData, useQuery } from "@tanstack/react-query";
import { KeyRound, RefreshCw, UserPlus } from "lucide-react";
import { useEffect, useState } from "react";
import { createUser, getUser, listUsers, resetPassword, syncRoles, updateUser } from "../../api/endpoints";
import { useApiMutation } from "../../api/mutations";
import { keys, queryClient, useLabel, useUniversities } from "../../api/queries";
import type { DataScope, Role, User } from "../../api/types";
import { useSession } from "../../auth/session";
import { DataTable, type Column } from "../../components/DataTable";
import { Drawer, Modal } from "../../components/Modal";
import { MultiSelect } from "../../components/MultiSelect";
import {
  Avatar,
  Button,
  Checkbox,
  DescriptionList,
  EmptyState,
  ErrorState,
  Loading,
  PageHeader,
  SearchInput,
  SelectField,
  StatusBadge,
  Switch,
  Card,
  TextField,
  Field,
} from "../../components/ui";
import { formatDateTime } from "../../lib/format";
import { usePageTitle } from "../../lib/usePageTitle";

const ROLES: Role[] = ["manager", "head", "admin"];
const ROLE_HINTS: Record<Role, string> = {
  manager: "Ведёт свои вузы и договоры",
  head: "Видит все вузы, назначает ответственных",
  admin: "Права, справочники, настройки",
};

function refreshUsers() {
  void queryClient.invalidateQueries({ queryKey: keys.users });
  void queryClient.invalidateQueries({ queryKey: ["user"] });
  void queryClient.invalidateQueries({ queryKey: ["users-page"] });
}

function RolesPicker({ value, onChange }: { value: Role[]; onChange: (value: Role[]) => void }) {
  const label = useLabel();
  return (
    <Field label="Роли" hint="Роли хранятся в Keycloak и действуют со следующего входа пользователя">
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
      </div>
    </Field>
  );
}

function UserDrawer({ userId, onClose }: { userId: string | null; onClose: () => void }) {
  const { me, mode } = useSession();
  const universities = useUniversities();
  const user = useQuery({ queryKey: ["user", userId], queryFn: () => getUser(userId!), enabled: Boolean(userId) });
  const [roles, setRoles] = useState<Role[]>([]);
  const [fullName, setFullName] = useState("");
  const [email, setEmail] = useState("");
  const [scope, setScope] = useState<DataScope>("default");
  const [grants, setGrants] = useState<string[]>([]);
  const [active, setActive] = useState(true);
  const [password, setPassword] = useState<string | null>(null);

  useEffect(() => {
    if (!user.data) return;
    setRoles((user.data.roles || []).filter((role): role is Role => ROLES.includes(role as Role)));
    setFullName(user.data.full_name);
    setEmail(user.data.email || "");
    setScope(user.data.data_scope);
    setGrants(user.data.university_ids || []);
    setActive(user.data.is_active);
  }, [user.data]);

  const save = useApiMutation(
    () =>
      updateUser(userId!, {
        roles,
        full_name: fullName.trim(),
        email: email.trim() || null,
        data_scope: scope,
        university_ids: grants,
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
  const reset = useApiMutation((value: string) => resetPassword(userId!, value), {
    success: "Временный пароль задан: пользователь сменит его при входе",
    onSuccess: () => setPassword(null),
  });

  const self = userId === me.id;
  const managed = new Set(user.data?.managed_university_ids || []);

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
            disabled={!user.data || roles.length === 0 || !fullName.trim()}
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
              ["Договоров", user.data.contracts_count ?? 0],
              ["Ответственный за вузы", managed.size ? `${managed.size}` : "нет"],
            ]}
          />
          <TextField label="ФИО" value={fullName} onChange={setFullName} maxLength={255} required />
          <TextField label="Почта" type="email" value={email} onChange={setEmail} maxLength={255} />
          <RolesPicker value={roles} onChange={setRoles} />
          {self && !roles.includes("admin") && <span className="field__error">Нельзя снять с себя роль администратора</span>}
          <SelectField
            label="Доступ к данным"
            value={scope}
            onChange={(value) => setScope(value as DataScope)}
            options={[
              { value: "default", label: "По роли: свои вузы (руководитель и администратор видят всё)" },
              { value: "all", label: "Все договоры и вузы" },
            ]}
          />
          <MultiSelect
            label="Дополнительно открытые вузы"
            placeholder="Нет"
            value={grants}
            onChange={setGrants}
            options={(universities.data || []).map((item) => ({
              value: item.id,
              label: item.short_name || item.name,
              hint: managed.has(item.id) ? "ответственный" : undefined,
            }))}
            hint="Вузы коллег, договоры которых сотрудник видит и ведёт (например, на время отпуска)"
          />
          <Switch label="Учётная запись активна" checked={active} disabled={self} onChange={setActive} />
          {mode === "keycloak" && (
            <Card title="Пароль">
              {password === null ? (
                <Button variant="outline" icon={KeyRound} onClick={() => setPassword("")}>
                  Задать временный пароль
                </Button>
              ) : (
                <div className="stack-s">
                  <TextField
                    label="Временный пароль"
                    type="password"
                    value={password}
                    onChange={setPassword}
                    hint="Не короче 8 символов; при входе Keycloak попросит сменить"
                  />
                  <div className="row">
                    <Button variant="outline" onClick={() => setPassword(null)}>
                      Отмена
                    </Button>
                    <Button loading={reset.isPending} disabled={password.length < 8} onClick={() => reset.mutate(password)}>
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
    (mode !== "keycloak" || password.length >= 8);
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
            hint="Не короче 8 символов"
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
        description="Роли, доступ к данным вузов и учётные записи. Изменения ролей записываются в Keycloak и попадают в журнал."
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
