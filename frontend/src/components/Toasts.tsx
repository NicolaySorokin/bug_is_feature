/**
 * Всплывающие уведомления: короткое «готово» или сообщение сервера с кодом ошибки.
 */
import { CheckCircle2, CircleAlert, Info, X } from "lucide-react";
import { createContext, useCallback, useContext, useMemo, useRef, useState, type ReactNode } from "react";
import { ApiError, errorMessage } from "../api/client";

type ToastTone = "success" | "error" | "info" | "warning";

interface ToastItem {
  id: number;
  tone: ToastTone;
  title: string;
  detail?: string;
}

interface ToastApi {
  success: (title: string, detail?: string) => void;
  info: (title: string, detail?: string) => void;
  warning: (title: string, detail?: string) => void;
  error: (error: unknown, title?: string) => void;
}

const ToastContext = createContext<ToastApi | null>(null);

const ICONS = { success: CheckCircle2, error: CircleAlert, info: Info, warning: CircleAlert };

export function ToastProvider({ children }: { children: ReactNode }) {
  const [items, setItems] = useState<ToastItem[]>([]);
  const nextId = useRef(1);

  const dismiss = useCallback((id: number) => setItems((current) => current.filter((item) => item.id !== id)), []);

  const push = useCallback(
    (tone: ToastTone, title: string, detail?: string) => {
      const id = nextId.current++;
      setItems((current) => [...current.slice(-3), { id, tone, title, detail }]);
      window.setTimeout(() => dismiss(id), tone === "error" ? 9000 : 5000);
    },
    [dismiss],
  );

  const api = useMemo<ToastApi>(
    () => ({
      success: (title, detail) => push("success", title, detail),
      info: (title, detail) => push("info", title, detail),
      warning: (title, detail) => push("warning", title, detail),
      error: (error, title) => {
        const code = error instanceof ApiError ? error.code : undefined;
        const message = errorMessage(error);
        push(
          "error",
          title || message,
          [title ? message : null, code ? `Код ошибки: ${code}` : null].filter(Boolean).join(" · "),
        );
      },
    }),
    [push],
  );

  return (
    <ToastContext.Provider value={api}>
      {children}
      <div className="toasts" aria-live="polite" aria-atomic="false">
        {items.map((item) => {
          const Icon = ICONS[item.tone];
          return (
            <div key={item.id} className={`toast toast--${item.tone}`} role={item.tone === "error" ? "alert" : "status"}>
              <Icon size={18} />
              <div className="toast__text">
                <strong>{item.title}</strong>
                {item.detail && <small>{item.detail}</small>}
              </div>
              <button
                type="button"
                className="icon-btn"
                style={{ width: 28, height: 28 }}
                aria-label="Скрыть"
                onClick={() => dismiss(item.id)}
              >
                <X size={14} />
              </button>
            </div>
          );
        })}
      </div>
    </ToastContext.Provider>
  );
}

export function useToast(): ToastApi {
  const api = useContext(ToastContext);
  if (!api) throw new Error("useToast вне ToastProvider");
  return api;
}
