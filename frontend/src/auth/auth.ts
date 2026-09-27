/**
 * Вход в систему.
 *
 * Схему входа выбирает сервер (GET /meta/auth), поэтому одна и та же сборка
 * клиента работает и на стенде с Keycloak, и в разработке с заглушкой.
 *
 * Keycloak: Authorization Code + PKCE через официальный адаптер keycloak-js
 * и публичный клиент edu-crm-web. Токены живут в памяти и в sessionStorage
 * вкладки (после перезагрузки страницы не нужно заново входить; закрыли
 * вкладку - сессия браузера кончилась). Перед каждым запросом токен
 * продлевается, если до конца его жизни меньше 30 секунд.
 *
 * Заглушка (AUTH_BACKEND=dev): пользователь выбирается из списка учётных
 * записей, API получает его в заголовках X-Dev-User и X-Dev-Roles.
 */
import Keycloak from "keycloak-js";
import type { AuthConfig, DemoAccount } from "../api/types";

const TOKENS_KEY = "edu-crm.tokens";
const DEV_ACCOUNT_KEY = "edu-crm.dev-account";

export type AuthMode = "dev" | "keycloak";

export interface AuthSession {
  mode: AuthMode;
  authenticated: boolean;
  demoAccounts: DemoAccount[];
  keycloakAccount?: { username: string; name: string };
}

let keycloak: Keycloak | null = null;
let devAccount: DemoAccount | null = null;
/** Итог действия на странице Keycloak (смена пароля), с которым вернулись в систему. */
let accountAction: { action: string; status: "success" | "cancelled" | "error" } | null = null;

function apiBase(): string {
  return (import.meta.env.VITE_API_BASE_URL || "/api/v1").replace(/\/$/, "");
}

function readJson<T>(storage: Storage, key: string): T | null {
  try {
    const raw = storage.getItem(key);
    return raw ? (JSON.parse(raw) as T) : null;
  } catch {
    return null;
  }
}

function saveTokens(): void {
  if (!keycloak?.token) return;
  try {
    sessionStorage.setItem(
      TOKENS_KEY,
      JSON.stringify({ token: keycloak.token, refreshToken: keycloak.refreshToken, idToken: keycloak.idToken }),
    );
  } catch {
    // Хранилище недоступно (приватный режим) - просто войдём заново после перезагрузки.
  }
}

async function loadConfig(): Promise<AuthConfig> {
  const response = await fetch(`${apiBase()}/meta/auth`);
  // Текст - для консоли разработчика: человеку Root показывает общее сообщение.
  if (!response.ok) throw new Error(`Настройки входа не получены: ответ ${response.status}`);
  return (await response.json()) as AuthConfig;
}

let initPromise: Promise<AuthSession> | null = null;

/**
 * Готовит вход: читает настройки сервера и восстанавливает сессию, если она есть.
 * Keycloak инициализируется один раз на страницу, поэтому результат запоминается.
 */
export function initAuth(): Promise<AuthSession> {
  initPromise ??= startAuth().catch((error) => {
    initPromise = null; // сервер был недоступен - следующая попытка начнётся заново
    throw error;
  });
  return initPromise;
}

async function startAuth(): Promise<AuthSession> {
  const config = await loadConfig();

  if (config.mode === "keycloak" && config.keycloak) {
    keycloak = new Keycloak({
      url: config.keycloak.url,
      realm: config.keycloak.realm,
      clientId: config.keycloak.client_id,
    });
    const stored = readJson<{ token: string; refreshToken: string; idToken: string }>(sessionStorage, TOKENS_KEY);
    keycloak.onAuthRefreshSuccess = saveTokens;
    keycloak.onAuthSuccess = saveTokens;
    keycloak.onTokenExpired = () => {
      keycloak?.updateToken(30).catch(() => undefined);
    };
    // Возврат со страницы смены пароля: keycloak-js разбирает kc_action_status
    // из адреса и сообщает итог сюда.
    keycloak.onActionUpdate = (status, action) => {
      accountAction = { action: action || "", status };
    };
    let authenticated = false;
    try {
      authenticated = await keycloak.init({
        pkceMethod: "S256",
        checkLoginIframe: false,
        // Сохранённые токены вкладки: без лишнего перехода на страницу Keycloak.
        token: stored?.token,
        refreshToken: stored?.refreshToken,
        idToken: stored?.idToken,
      });
    } catch {
      sessionStorage.removeItem(TOKENS_KEY);
    }
    if (authenticated) saveTokens();
    const parsed = keycloak.tokenParsed as { preferred_username?: string; name?: string } | undefined;
    return {
      mode: "keycloak",
      authenticated,
      demoAccounts: [],
      keycloakAccount: parsed
        ? { username: parsed.preferred_username || "", name: parsed.name || parsed.preferred_username || "" }
        : undefined,
    };
  }

  devAccount = readJson<DemoAccount>(sessionStorage, DEV_ACCOUNT_KEY);
  return { mode: "dev", authenticated: devAccount !== null, demoAccounts: config.demo_accounts || [] };
}

/** Переход на страницу входа Keycloak (или выбор учётной записи заглушки). */
export async function login(account?: DemoAccount): Promise<void> {
  if (keycloak) {
    await keycloak.login({ redirectUri: window.location.href, locale: "ru" });
    return;
  }
  if (account) {
    devAccount = account;
    sessionStorage.setItem(DEV_ACCOUNT_KEY, JSON.stringify(account));
  }
}

export async function logout(): Promise<void> {
  sessionStorage.removeItem(TOKENS_KEY);
  sessionStorage.removeItem(DEV_ACCOUNT_KEY);
  if (keycloak) {
    await keycloak.logout({ redirectUri: window.location.origin });
    return;
  }
  devAccount = null;
  window.location.assign("/");
}

/** Заголовки авторизации для запроса к API. */
export async function authHeaders(): Promise<Record<string, string>> {
  if (keycloak) {
    try {
      await keycloak.updateToken(30);
    } catch {
      // Сессия Keycloak кончилась - запрос уйдёт без продления и вернёт 401.
    }
    return keycloak.token ? { Authorization: `Bearer ${keycloak.token}` } : {};
  }
  if (devAccount) {
    return { "X-Dev-User": devAccount.username, "X-Dev-Roles": devAccount.roles.join(",") };
  }
  return {};
}

let redirecting = false;

/** API ответил 401: сессия истекла - отправляем на вход, не теряя адрес страницы. */
export function onUnauthorized(): void {
  if (redirecting) return;
  redirecting = true;
  sessionStorage.removeItem(TOKENS_KEY);
  if (keycloak) {
    void keycloak.login({ redirectUri: window.location.href, locale: "ru" });
  } else {
    sessionStorage.removeItem(DEV_ACCOUNT_KEY);
    window.location.assign("/");
  }
}

/**
 * Смена пароля: страница Keycloak «Новый пароль» (действие UPDATE_PASSWORD,
 * Application Initiated Action). Пароль вводится только в Keycloak - система
 * его не видит; после сохранения Keycloak возвращает на returnTo.
 *
 * Отдельная консоль учётной записи Keycloak (/realms/.../account) не нужна:
 * она на английском, не в стиле системы и требует ролей клиента account.
 */
export async function changePassword(returnTo = window.location.href): Promise<void> {
  if (!keycloak) return;
  await keycloak.login({ action: "UPDATE_PASSWORD", redirectUri: returnTo, locale: "ru" });
}

/** Итог смены пароля, если только что вернулись со страницы Keycloak. Читается один раз. */
export function takeAccountAction(): { action: string; status: "success" | "cancelled" | "error" } | null {
  const result = accountAction;
  accountAction = null;
  return result;
}
