/**
 * Вход в систему.
 *
 * На стенде с Keycloak - одна кнопка: логин и пароль вводятся на странице
 * Keycloak, система паролей не видит. В режиме разработки - список учётных
 * записей заглушки, сгруппированный по ролям.
 */
import { KeyRound, LogIn, ShieldCheck } from "lucide-react";
import { useMemo, useState } from "react";
import type { DemoAccount } from "../api/types";
import type { AuthSession } from "../auth/auth";
import { Avatar, Button, SearchInput } from "../components/ui";
import { ROLE_SHORT } from "../lib/labels";

const ROLE_ORDER = ["admin", "head", "manager"];

function mainRole(account: DemoAccount): string {
  return ROLE_ORDER.find((role) => account.roles.includes(role)) || "manager";
}

export function LoginPage({ auth, onLogin }: { auth: AuthSession; onLogin: (account?: DemoAccount) => Promise<void> }) {
  const [query, setQuery] = useState("");
  const [busy, setBusy] = useState(false);

  const accounts = useMemo(() => {
    const needle = query.trim().toLowerCase();
    return [...auth.demoAccounts]
      .filter((account) => !needle || `${account.full_name} ${account.username}`.toLowerCase().includes(needle))
      .sort((left, right) => ROLE_ORDER.indexOf(mainRole(left)) - ROLE_ORDER.indexOf(mainRole(right)));
  }, [auth.demoAccounts, query]);

  const enter = async (account?: DemoAccount) => {
    setBusy(true);
    try {
      await onLogin(account);
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="login">
      <section className="login__hero">
        <a className="sidebar__brand" style={{ padding: 0, height: "auto" }} href="/">
          <span className="brand-mark">РТ</span>
          <span className="brand-text">
            <strong>ИТ Школа Ростелекома</strong>
            <small>Взаимодействие с вузами</small>
          </span>
        </a>
        <div className="stack" style={{ gap: 20 }}>
          <h1>Система контроля взаимодействия ИТ Школы с вузами и школами</h1>
          <p>
            Договоры и ИТ-программы, рабочие процессы с вузами, лицензии на ИТ-продукты, статистика обучения студентов и отчёты
            для руководства - в одном месте.
          </p>
        </div>
        <div className="login__facts">
          <div>
            <strong>14 этапов</strong>
            <span>процесса работы с вузом</span>
          </div>
          <div>
            <strong>XLSX · XLS · PDF</strong>
            <span>отчёты и выгрузки</span>
          </div>
          <div>
            <strong>LMS и сайт</strong>
            <span>заявки и обучающиеся</span>
          </div>
        </div>
      </section>

      <section className="login__panel">
        {auth.mode === "keycloak" ? (
          <>
            <div className="stack-s">
              <h2>Вход в систему</h2>
              <p className="muted">
                Логин и пароль вводятся на странице единого входа Keycloak. После входа вы вернётесь на ту страницу, которую
                открывали.
              </p>
            </div>
            <Button size="l" icon={LogIn} loading={busy} onClick={() => void enter()}>
              Войти через Keycloak
            </Button>
            <p className="muted row" style={{ fontSize: 13 }}>
              <ShieldCheck size={16} /> Доступ выдаёт администратор системы. Забыли пароль - обратитесь к нему.
            </p>
          </>
        ) : (
          <>
            <div className="stack-s">
              <h2>Выберите учётную запись</h2>
              <p className="muted">
                Стенд работает без Keycloak (режим разработки): вход выполняется от имени выбранного сотрудника, права
                соответствуют его ролям.
              </p>
            </div>
            <SearchInput value={query} onChange={setQuery} placeholder="Фамилия или логин" label="Поиск учётной записи" />
            <ul className="account-list">
              {accounts.map((account) => (
                <li key={account.username}>
                  <button type="button" className="account" disabled={busy} onClick={() => void enter(account)}>
                    <Avatar name={account.full_name} />
                    <span className="account__text">
                      <strong>{account.full_name}</strong>
                      <small>
                        {account.username} · {account.roles.map((role) => ROLE_SHORT[role] || role).join(", ")}
                      </small>
                    </span>
                    <KeyRound size={16} className="muted" />
                  </button>
                </li>
              ))}
              {accounts.length === 0 && <li className="muted">Учётные записи не найдены</li>}
            </ul>
          </>
        )}
      </section>
    </div>
  );
}
