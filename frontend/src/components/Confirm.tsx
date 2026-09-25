/**
 * Подтверждение действия, при необходимости - с причиной.
 *
 * const confirm = useConfirm();
 * const reason = await confirm({ title: "Заблокировать процесс?", reason: { required: true } });
 * if (reason === null) return; // пользователь передумал
 */
import { createContext, useCallback, useContext, useRef, useState, type ReactNode } from "react";
import { Modal } from "./Modal";
import { Button, TextAreaField } from "./ui";

export interface ConfirmOptions {
  title: string;
  message?: ReactNode;
  confirmLabel?: string;
  danger?: boolean;
  /** Поле для причины или комментария: его текст вернёт confirm. */
  reason?: { label?: string; required?: boolean; placeholder?: string };
}

type ConfirmFn = (options: ConfirmOptions) => Promise<string | null>;

const ConfirmContext = createContext<ConfirmFn | null>(null);

export function ConfirmProvider({ children }: { children: ReactNode }) {
  const [options, setOptions] = useState<ConfirmOptions | null>(null);
  const [text, setText] = useState("");
  const resolver = useRef<((value: string | null) => void) | null>(null);

  const confirm = useCallback<ConfirmFn>((next) => {
    setText("");
    setOptions(next);
    return new Promise((resolve) => {
      resolver.current = resolve;
    });
  }, []);

  const close = (value: string | null) => {
    resolver.current?.(value);
    resolver.current = null;
    setOptions(null);
  };

  const missingReason = Boolean(options?.reason?.required && !text.trim());

  return (
    <ConfirmContext.Provider value={confirm}>
      {children}
      <Modal
        open={options !== null}
        title={options?.title}
        onClose={() => close(null)}
        footer={
          <>
            <Button variant="outline" onClick={() => close(null)}>
              Отмена
            </Button>
            <Button variant={options?.danger ? "danger" : "primary"} disabled={missingReason} onClick={() => close(text.trim())}>
              {options?.confirmLabel || "Подтвердить"}
            </Button>
          </>
        }
      >
        <div className="stack">
          {options?.message && <div className="soft">{options.message}</div>}
          {options?.reason && (
            <TextAreaField
              label={options.reason.label || "Комментарий"}
              required={options.reason.required}
              placeholder={options.reason.placeholder}
              value={text}
              onChange={setText}
              rows={3}
              maxLength={4000}
            />
          )}
        </div>
      </Modal>
    </ConfirmContext.Provider>
  );
}

export function useConfirm(): ConfirmFn {
  const confirm = useContext(ConfirmContext);
  if (!confirm) throw new Error("useConfirm вне ConfirmProvider");
  return confirm;
}
