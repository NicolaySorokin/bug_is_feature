/**
 * Фильтры реестра в адресе страницы.
 *
 * Адрес с фильтрами можно отправить коллеге или сохранить в закладки.
 * Последний набор фильтров запоминается (требование 13 ТЗ «кэш действий
 * пользователя»): если открыть раздел из меню, фильтры вернутся такими,
 * какими их оставили.
 */
import { useCallback, useEffect, useMemo } from "react";
import { useSearchParams } from "react-router-dom";
import { readStored, writeStored } from "./storage";

export type Filters = Record<string, string>;

export function useUrlFilters(storageKey: string, keys: string[]): [Filters, (patch: Filters) => void, () => void] {
  const [params, setParams] = useSearchParams();

  const filters = useMemo(() => {
    const result: Filters = {};
    keys.forEach((key) => {
      const value = params.get(key);
      if (value) result[key] = value;
    });
    return result;
    // keys - постоянный список, сравнение по содержимому не нужно
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [params]);

  // Раздел открыли без фильтров в адресе - вернём сохранённые.
  useEffect(() => {
    const hasAny = keys.some((key) => params.has(key));
    if (hasAny) return;
    const stored = readStored<Filters>(`filters.${storageKey}`, {});
    const restored = Object.entries(stored).filter(([key, value]) => keys.includes(key) && value);
    if (restored.length) {
      const next = new URLSearchParams(params);
      restored.forEach(([key, value]) => next.set(key, value));
      setParams(next, { replace: true });
    }
    // Только при первом открытии страницы.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  useEffect(() => {
    writeStored(`filters.${storageKey}`, filters);
  }, [filters, storageKey]);

  const update = useCallback(
    (patch: Filters) => {
      const next = new URLSearchParams(params);
      Object.entries(patch).forEach(([key, value]) => {
        if (value) next.set(key, value);
        else next.delete(key);
      });
      // Любое изменение фильтра возвращает к первой странице.
      if (!("offset" in patch)) next.delete("offset");
      setParams(next, { replace: true });
    },
    [params, setParams],
  );

  const reset = useCallback(() => {
    const next = new URLSearchParams(params);
    keys.forEach((key) => next.delete(key));
    setParams(next, { replace: true });
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [params, setParams]);

  return [filters, update, reset];
}
