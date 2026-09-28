/**
 * Модальное окно и боковая панель. В Atomaro их нет, поэтому сделаны здесь: фокус внутри окна,
 * Esc закрывает, после закрытия фокус возвращается.
 */
import { X } from "lucide-react";
import { useEffect, useId, useRef, type ReactNode } from "react";
import { createPortal } from "react-dom";

const FOCUSABLE =
  'a[href], button:not([disabled]), input:not([disabled]), select:not([disabled]), textarea:not([disabled]), [tabindex]:not([tabindex="-1"])';

let openCount = 0;

function useDialogBehaviour(open: boolean, onClose: () => void, dismissable: boolean) {
  const panelRef = useRef<HTMLDivElement>(null);
  const onCloseRef = useRef(onClose);
  onCloseRef.current = onClose;

  useEffect(() => {
    if (!open) return;
    const previous = document.activeElement as HTMLElement | null;
    openCount += 1;
    document.body.style.overflow = "hidden";

    const panel = panelRef.current;
    const first = panel?.querySelector<HTMLElement>("[data-autofocus]") || panel?.querySelector<HTMLElement>(FOCUSABLE);
    window.setTimeout(() => (first || panel)?.focus(), 0);

    const onKeyDown = (event: KeyboardEvent) => {
      if (event.key === "Escape" && dismissable) {
        event.stopPropagation();
        onCloseRef.current();
        return;
      }
      if (event.key !== "Tab" || !panel) return;
      const items = Array.from(panel.querySelectorAll<HTMLElement>(FOCUSABLE)).filter((item) => item.offsetParent !== null);
      if (items.length === 0) return;
      const firstItem = items[0];
      const lastItem = items[items.length - 1];
      if (event.shiftKey && document.activeElement === firstItem) {
        event.preventDefault();
        lastItem.focus();
      } else if (!event.shiftKey && document.activeElement === lastItem) {
        event.preventDefault();
        firstItem.focus();
      }
    };
    panel?.addEventListener("keydown", onKeyDown);
    return () => {
      panel?.removeEventListener("keydown", onKeyDown);
      openCount -= 1;
      if (openCount === 0) document.body.style.overflow = "";
      previous?.focus?.();
    };
  }, [open, dismissable]);

  return panelRef;
}

export interface ModalProps {
  open: boolean;
  title: ReactNode;
  description?: ReactNode;
  onClose: () => void;
  children: ReactNode;
  footer?: ReactNode;
  size?: "m" | "wide" | "xl";
  /** false: окно не закрывается кликом мимо и Esc, например пока идёт сохранение. */
  dismissable?: boolean;
}

export function Modal({ open, title, description, onClose, children, footer, size = "m", dismissable = true }: ModalProps) {
  const titleId = useId();
  const panelRef = useDialogBehaviour(open, onClose, dismissable);
  if (!open) return null;
  return createPortal(
    <div
      className="modal-backdrop"
      onMouseDown={(event) => {
        if (event.target === event.currentTarget && dismissable) onClose();
      }}
    >
      <div
        ref={panelRef}
        className={`modal ${size === "wide" ? "modal--wide" : size === "xl" ? "modal--xl" : ""}`}
        role="dialog"
        aria-modal="true"
        aria-labelledby={titleId}
        tabIndex={-1}
      >
        <div className="modal__header">
          <div>
            <h2 id={titleId}>{title}</h2>
            {description && <p>{description}</p>}
          </div>
          <button type="button" className="icon-btn" aria-label="Закрыть" onClick={onClose} disabled={!dismissable}>
            <X size={18} />
          </button>
        </div>
        <div className="modal__body">{children}</div>
        {footer && <div className="modal__footer">{footer}</div>}
      </div>
    </div>,
    document.body,
  );
}

export function Drawer({
  open,
  title,
  description,
  onClose,
  children,
  footer,
}: {
  open: boolean;
  title: ReactNode;
  description?: ReactNode;
  onClose: () => void;
  children: ReactNode;
  footer?: ReactNode;
}) {
  const titleId = useId();
  const panelRef = useDialogBehaviour(open, onClose, true);
  if (!open) return null;
  return createPortal(
    <>
      <div className="drawer-backdrop" onMouseDown={onClose} />
      <div ref={panelRef} className="drawer" role="dialog" aria-modal="true" aria-labelledby={titleId} tabIndex={-1}>
        <div className="modal__header">
          <div>
            <h2 id={titleId}>{title}</h2>
            {description && <p>{description}</p>}
          </div>
          <button type="button" className="icon-btn" aria-label="Закрыть" onClick={onClose}>
            <X size={18} />
          </button>
        </div>
        <div className="modal__body" style={{ flex: 1 }}>
          {children}
        </div>
        {footer && <div className="modal__footer">{footer}</div>}
      </div>
    </>,
    document.body,
  );
}
