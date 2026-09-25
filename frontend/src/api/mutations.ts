/**
 * Изменение данных с уведомлением о результате.
 *
 * Каждое действие пользователя заканчивается видимым ответом: «Сохранено»
 * или понятной ошибкой с кодом. Страница при этом не перезагружается -
 * обновляются только затронутые данные.
 */
import { useMutation } from "@tanstack/react-query";
import { useCallback, useState } from "react";
import { useToast } from "../components/Toasts";
import { saveFile, type DownloadedFile } from "./client";

interface Options<TVars, TData> {
  success?: string | ((data: TData, vars: TVars) => string);
  onSuccess?: (data: TData, vars: TVars) => void;
  errorTitle?: string;
}

export function useApiMutation<TVars, TData>(fn: (vars: TVars) => Promise<TData>, options: Options<TVars, TData> = {}) {
  const toast = useToast();
  return useMutation({
    mutationFn: fn,
    onSuccess: (data, vars) => {
      if (options.success) toast.success(typeof options.success === "function" ? options.success(data, vars) : options.success);
      options.onSuccess?.(data, vars);
    },
    onError: (error) => toast.error(error, options.errorTitle),
  });
}

/** Скачивание файла из API: отчёта, диаграммы, образца, вложения. */
export function useDownload(): [(load: () => Promise<DownloadedFile>) => Promise<void>, boolean] {
  const toast = useToast();
  const [busy, setBusy] = useState(false);
  const run = useCallback(
    async (load: () => Promise<DownloadedFile>) => {
      setBusy(true);
      try {
        saveFile(await load());
      } catch (error) {
        toast.error(error, "Не удалось скачать файл");
      } finally {
        setBusy(false);
      }
    },
    [toast],
  );
  return [run, busy];
}
