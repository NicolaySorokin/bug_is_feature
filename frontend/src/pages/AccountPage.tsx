/**
 * Учётная запись текущего сотрудника: профиль, роли, доступ к данным
 * и смена пароля.
 *
 * Раньше пункт меню вёл в консоль учётной записи Keycloak - отдельное
 * приложение на английском, которое отвечало 401 без ролей клиента account.
 * Теперь всё показывается здесь, а пароль меняется на странице Keycloak
 * «Новый пароль» в оформлении системы: сама система пароль не видит.
 */
import { KeyRound, LogOut, ShieldCheck } from "lucide-react";
import { useEffect } from "react";
import { changePassword, logout, takeAccountAction } from "../auth/auth";
import { useSession } from "../auth/session";
import { useToast } from "../components/Toasts";
import { Avatar, Button, Card, DescriptionList, PageHeader, StatusBadge } from "../components/ui";
import { ROLE_SHORT } from "../lib/labels";
import { formatDate } from "../lib/format";
import { usePageTitle } from "../lib/usePageTitle";

const ROLE_DUTIES: Record<string, string> = {
  manager: "ведёт свои взаимодействия с вузами: процесс, программы и продукты, договор, файлы",
  head: "контролирует работу команды: назначает ответственных, решает исключения, подтверждает вузы",
  admin: "управляет пользователями и правами, справочниками, шаблонами процессов, интеграциями и настройками",
};

const SCOPE_TEXT: Record<string, string> = {
  own: "Вы видите свои взаимодействия, вузы, где вы менеджер по умолчанию, и вузы, открытые вам отдельно.",
  team: "Вы видите взаимодействия своей команды и те, что ждут назначения ответственного.",
  all: "Вы видите все взаимодействия организации.",
  none: "Бизнес-данные (взаимодействия, договоры, отчёты) вам недоступны - только административные функции.",
  default: "",
};

export default function AccountPage() {
  const { me, roles, mode } = useSession();
  const toast = useToast();
  usePageTitle("Учётная запись");

  // Вернулись со страницы смены пароля Keycloak - сообщаем итог.
  useEffect(() => {
    const result = takeAccountAction();
    if (!result) return;
    if (result.status === "success") toast.success("Пароль изменён");
    else if (result.status === "error")
      toast.error(new Error("Keycloak сообщил об ошибке. Попробуйте ещё раз."), "Пароль не изменён");
  }, [toast]);

  const keycloak = mode === "keycloak";

  return (
    <div className="page page--narrow">
      <PageHeader title="Учётная запись" description="Ваш профиль в системе, роли и безопасность входа." />
      <div className="stack">
        <Card>
          <div className="account-profile">
            <Avatar name={me.full_name} large />
            <div className="stack-s" style={{ gap: 4, minWidth: 0 }}>
              <strong className="account-profile__name">{me.full_name}</strong>
              <span className="muted">{me.email || "Почта не указана"}</span>
            </div>
            <StatusBadge tone={me.is_active ? "success" : "error"}>{me.is_active ? "Активна" : "Отключена"}</StatusBadge>
          </div>
          <DescriptionList
            items={[
              ["Логин", <span className="mono">{me.username}</span>],
              ["Почта", me.email],
              ["Вход", keycloak ? "Единый вход Keycloak" : "Режим разработки, без пароля"],
            ]}
          />
          <p className="muted account-note">ФИО и почту меняет администратор системы в разделе «Пользователи и права».</p>
        </Card>

        <Card title="Роли и доступ">
          <ul className="role-list">
            {roles.length === 0 && <li className="muted">Роли не назначены - обратитесь к администратору.</li>}
            {roles.map((role) => (
              <li key={role}>
                <StatusBadge tone="accent">{ROLE_SHORT[role] || role}</StatusBadge>
                <span className="soft">{ROLE_DUTIES[role]}</span>
              </li>
            ))}
          </ul>
          <p className="muted account-note">
            {SCOPE_TEXT[me.effective_scope || "none"]}
            {me.data_scope_expires_at ? ` Расширенный доступ действует до ${formatDate(me.data_scope_expires_at)}.` : ""}
          </p>
        </Card>

        <Card title="Безопасность">
          <div className="account-action">
            <span className="account-action__icon">
              <KeyRound size={18} />
            </span>
            <div className="stack-s" style={{ gap: 2, minWidth: 0, flex: 1 }}>
              <strong>Пароль</strong>
              <span className="muted">
                {keycloak
                  ? "Новый пароль вводится на странице единого входа: не короче 12 символов, с заглавной и строчной буквой и цифрой."
                  : "В режиме разработки вход выполняется без пароля - менять нечего."}
              </span>
            </div>
            <Button variant="secondary" icon={KeyRound} disabled={!keycloak} onClick={() => void changePassword()}>
              Сменить пароль
            </Button>
          </div>
          <div className="account-action">
            <span className="account-action__icon">
              <ShieldCheck size={18} />
            </span>
            <div className="stack-s" style={{ gap: 2, minWidth: 0, flex: 1 }}>
              <strong>Сеанс</strong>
              <span className="muted">Закончили работу на чужом компьютере - выйдите из системы.</span>
            </div>
            <Button variant="outline" icon={LogOut} onClick={() => void logout()}>
              Выйти
            </Button>
          </div>
        </Card>
      </div>
    </div>
  );
}
