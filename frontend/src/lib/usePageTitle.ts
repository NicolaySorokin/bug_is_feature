import { useEffect } from "react";

const APP = "ИТ Школа · вузы";

/** Заголовок вкладки браузера: по нему страницы различают в истории и закладках. */
export function usePageTitle(title?: string | null): void {
  useEffect(() => {
    document.title = title ? `${title} — ${APP}` : APP;
  }, [title]);
}
