/**
 * Учётная запись сотрудника: профиль, роли, доступ к данным и смена пароля. Пароль меняется
 * на странице Keycloak, система его не видит.
 */
import { Eye, EyeOff, Handshake, KeyRound, LogOut, Settings, ShieldCheck, Users, type LucideIcon } from "lucide-react";
import { useEffect, type ReactNode } from "react";
import { changePassword, logout, takeAccountAction } from "../auth/auth";
import { useSession } from "../auth/session";
import { useToast } from "../components/Toasts";
import { Avatar, Button, Card, DescriptionList, PageHeader, StatusBadge } from "../components/ui";
import { ROLE_SHORT } from "../lib/labels";
import { formatDate } from "../lib/format";
import { usePageTitle } from "../lib/usePageTitle";

const ROLE_ICONS: Record<string, LucideIcon> = { manager: Handshake, head: Users, admin: Settings };

const ROLE_DUTIES: Record<string, string> = {
  manager: "Ведёт свои взаимодействия с вузами: процесс, программы и продукты, договор, файлы.",
  head: "Контролирует работу команды: назначает ответственных, решает исключения, подтверждает вузы.",
  admin: "Управляет пользователями и правами, справочниками, шаблонами процессов, интеграциями и настройками.",
};

const SCOPE_TEXT: Record<string, string> = {
  own: "Вы видите свои взаимодействия, вузы, где вы менеджер по умолчанию, и вузы, открытые вам отдельно.",
  team: "Вы видите взаимодействия своей команды и те, что ждут назначения ответственного.",
  all: "Вы видите все взаимодействия организации.",
  none: "Бизнес-данные (взаимодействия, договоры, отчёты) вам недоступны - только административные функции.",
  default: "",
};

/** Строка карточки: значок, заголовок, пояснение и, если нужно, действие справа. */
function AccountRow({
  icon: Icon,
  title,
  children,
  action,
}: {
  icon: LucideIcon;
  title: ReactNode;
  children: ReactNode;
  action?: ReactNode;
}) {
  return (
    <div className="account-action">
      <span className="account-action__icon" aria-hidden="true">
        <Icon size={18} />
      </span>
      <div className="account-action__text">
        <strong>{title}</strong>
        <span className="muted">{children}</span>
      </div>
      {action && <div className="account-action__button">{action}</div>}
    </div>
  );
}

export default function AccountPage() {
  const { me, roles, mode } = useSession();
  const toast = useToast();
  usePageTitle("Учётная запись");

  // Вернулись со страницы смены пароля Keycloak, сообщаем итог.
  useEffect(() => {
    const result = takeAccountAction();
    if (!result) return;
    if (result.status === "success") toast.success("Пароль изменён");
    else if (result.status === "error")
      toast.error(new Error("Keycloak сообщил об ошибке. Попробуйте ещё раз."), "Пароль не изменён");
  }, [toast]);

  const keycloak = mode === "keycloak";
  const scope = me.effective_scope || "none";

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
          {roles.length === 0 && (
            <AccountRow icon={ShieldCheck} title="Роли не назначены">
              Обратитесь к администратору системы.
            </AccountRow>
          )}
          {roles.map((role) => (
            <AccountRow key={role} icon={ROLE_ICONS[role] || ShieldCheck} title={ROLE_SHORT[role] || role}>
              {ROLE_DUTIES[role]}
            </AccountRow>
          ))}
          <AccountRow icon={scope === "none" ? EyeOff : Eye} title="Доступ к данным">
            {SCOPE_TEXT[scope]}
            {me.data_scope_expires_at ? ` Расширенный доступ действует до ${formatDate(me.data_scope_expires_at)}.` : ""}
          </AccountRow>
        </Card>

        <Card title="Безопасность">
          <AccountRow
            icon={KeyRound}
            title="Пароль"
            action={
              <Button variant="secondary" icon={KeyRound} disabled={!keycloak} onClick={() => void changePassword()}>
                Сменить пароль
              </Button>
            }
          >
            {keycloak
              ? "Новый пароль вводится на странице единого входа: не короче 12 символов, с заглавной и строчной буквой и цифрой."
              : "В режиме разработки вход выполняется без пароля - менять нечего."}
          </AccountRow>
          <AccountRow
            icon={ShieldCheck}
            title="Сеанс"
            action={
              <Button variant="outline" icon={LogOut} onClick={() => void logout()}>
                Выйти
              </Button>
            }
          >
            Закончили работу на чужом компьютере - выйдите из системы.
          </AccountRow>
        </Card>
      </div>
    </div>
  );
}
