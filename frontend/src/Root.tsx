/**
 * Запуск приложения: вход, загрузка профиля, затем интерфейс.
 *
 * 1. Сервер сообщает схему входа (Keycloak или учебная заглушка).
 * 2. Без сессии - страница входа.
 * 3. С сессией - профиль /me: роли и область данных. Отключённая учётная
 *    запись получает понятное сообщение, а не пустой экран.
 */
import { QueryClientProvider, useQuery } from "@tanstack/react-query";
import { useEffect, useState } from "react";
import { ApiError, errorMessage } from "./api/client";
import { getMe } from "./api/endpoints";
import { keys, queryClient } from "./api/queries";
import { initAuth, login, logout, type AuthSession } from "./auth/auth";
import { SessionProvider } from "./auth/session";
import { ConfirmProvider } from "./components/Confirm";
import { ToastProvider } from "./components/Toasts";
import { Button, ErrorState } from "./components/ui";
import { App } from "./App";
import { LoginPage } from "./pages/LoginPage";
import { Loader } from "@atomaro/ui-kit";

type BootState = { status: "loading" } | { status: "failed"; error: string } | { status: "ready"; auth: AuthSession };

function Boot({ text }: { text: string }) {
  return (
    <div className="boot" role="status">
      <span className="brand-mark" aria-hidden="true">
        РТ
      </span>
      <Loader size="s" variant="primary" />
      <span>{text}…</span>
    </div>
  );
}

export function Root() {
  const [state, setState] = useState<BootState>({ status: "loading" });
  const [attempt, setAttempt] = useState(0);

  useEffect(() => {
    let cancelled = false;
    initAuth()
      .then((auth) => !cancelled && setState({ status: "ready", auth }))
      .catch((error) => !cancelled && setState({ status: "failed", error: errorMessage(error) }));
    return () => {
      cancelled = true;
    };
  }, [attempt]);

  if (state.status === "loading") return <Boot text="Подключаемся к серверу" />;
  if (state.status === "failed") {
    return (
      <div className="boot">
        <ErrorState
          title="Сервер недоступен"
          error={new ApiError(state.error, 0, "network_error")}
          onRetry={() => {
            setState({ status: "loading" });
            setAttempt((value) => value + 1);
          }}
        />
      </div>
    );
  }

  const { auth } = state;
  if (!auth.authenticated) {
    return (
      <LoginPage
        auth={auth}
        onLogin={async (account) => {
          await login(account);
          if (auth.mode === "dev") setState({ status: "ready", auth: { ...auth, authenticated: true } });
        }}
      />
    );
  }

  return (
    <QueryClientProvider client={queryClient}>
      <ToastProvider>
        <ConfirmProvider>
          <Authorized auth={auth} />
        </ConfirmProvider>
      </ToastProvider>
    </QueryClientProvider>
  );
}

function Authorized({ auth }: { auth: AuthSession }) {
  const me = useQuery({ queryKey: keys.me, queryFn: getMe, staleTime: 5 * 60_000 });

  if (me.isPending) return <Boot text="Загружаем профиль" />;
  if (me.isError) {
    const disabled = me.error instanceof ApiError && me.error.code === "account_disabled";
    return (
      <div className="boot">
        <ErrorState
          title={disabled ? "Учётная запись отключена" : "Не удалось загрузить профиль"}
          error={me.error}
          onRetry={disabled ? undefined : () => void me.refetch()}
        />
        <Button variant="outline" onClick={() => void logout()}>
          Выйти
        </Button>
      </div>
    );
  }

  return (
    <SessionProvider me={me.data} mode={auth.mode}>
      <App />
    </SessionProvider>
  );
}
