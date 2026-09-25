/**
 * Сохранение того, что пользователь уже сделал на экране.
 *
 * Требование 13 ТЗ «кэш работы действий пользователя»: фильтры реестров
 * и отчётов, выбранные колонки, черновики комментариев переживают переход
 * между страницами и перезагрузку - пользователю не нужно повторять ввод.
 * Хранится в localStorage этого браузера; если хранилище недоступно
 * (приватный режим), всё работает, просто без запоминания.
 */
import { useCallback, useEffect, useRef, useState } from "react";

const PREFIX = "edu-crm.";

export function readStored<T>(key: string, fallback: T): T {
  try {
    const raw = window.localStorage.getItem(PREFIX + key);
    return raw === null ? fallback : (JSON.parse(raw) as T);
  } catch {
    return fallback;
  }
}

export function writeStored<T>(key: string, value: T | undefined): void {
  try {
    if (value === undefined) window.localStorage.removeItem(PREFIX + key);
    else window.localStorage.setItem(PREFIX + key, JSON.stringify(value));
  } catch {
    // Без хранилища просто не запоминаем.
  }
}

/** useState, значение которого сохраняется между сеансами. */
export function usePersistentState<T>(key: string, fallback: T): [T, (value: T | ((current: T) => T)) => void, () => void] {
  const [value, setValue] = useState<T>(() => readStored(key, fallback));
  const fallbackRef = useRef(fallback);

  useEffect(() => {
    writeStored(key, value);
  }, [key, value]);

  const reset = useCallback(() => setValue(fallbackRef.current), []);
  return [value, setValue, reset];
}
