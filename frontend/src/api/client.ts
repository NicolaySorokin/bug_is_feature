/**
 * HTTP-клиент API.
 *
 * Любой отказ сервера приходит в едином формате {code, message, details}
 * (нефункциональное требование 3 ТЗ «коды ошибок»): клиент превращает его
 * в ApiError, а интерфейс показывает человеку message, а в подробностях -
 * машиночитаемый code.
 */
import { authHeaders, onUnauthorized } from "../auth/auth";

export const API_BASE_URL = (import.meta.env.VITE_API_BASE_URL || "/api/v1").replace(/\/$/, "");

/**
 * Текст, если сервер ответил без нашего формата ошибки - обычно это Nginx,
 * пока API перезапускается или недоступен. Номер ответа (502, 504...) людям
 * ничего не говорит, поэтому в тексте его нет: он виден разработчику
 * в инструментах браузера.
 */
function fallbackMessage(status: number): string {
  if (status === 413) return "Файл слишком большой. Загрузите файл меньшего размера.";
  const what = status >= 500 ? "Сервер сейчас недоступен." : "Сервер не смог выполнить действие.";
  return `${what} Повторите действие позже, а если ошибка повторится - обратитесь к администратору.`;
}

function fallbackCode(status: number): string {
  if (status === 413) return "file_too_large";
  return status >= 500 ? "internal_error" : "request_failed";
}

export class ApiError extends Error {
  readonly status: number;
  readonly code: string;
  readonly details: Record<string, unknown> | null;

  constructor(message: string, status: number, code: string, details: Record<string, unknown> | null = null) {
    super(message);
    this.name = "ApiError";
    this.status = status;
    this.code = code;
    this.details = details;
  }
}

export type Query = Record<string, string | number | boolean | null | undefined | string[]>;

export interface RequestOptions {
  method?: "GET" | "POST" | "PUT" | "PATCH" | "DELETE";
  query?: Query;
  body?: unknown;
  signal?: AbortSignal;
}

export function buildUrl(path: string, query?: Query): string {
  const params = new URLSearchParams();
  Object.entries(query || {}).forEach(([key, value]) => {
    if (value === undefined || value === null || value === "") return;
    if (Array.isArray(value)) value.forEach((item) => params.append(key, item));
    else params.set(key, String(value));
  });
  const search = params.toString();
  return `${API_BASE_URL}${path}${search ? `?${search}` : ""}`;
}

async function send(path: string, options: RequestOptions): Promise<Response> {
  const headers = new Headers(await authHeaders());
  let body: BodyInit | undefined;
  if (options.body instanceof FormData) body = options.body;
  else if (options.body !== undefined) {
    headers.set("Content-Type", "application/json");
    body = JSON.stringify(options.body);
  }

  let response: Response;
  try {
    response = await fetch(buildUrl(path, options.query), {
      method: options.method || (body ? "POST" : "GET"),
      headers,
      body,
      signal: options.signal,
    });
  } catch (error) {
    if (error instanceof DOMException && error.name === "AbortError") throw error;
    throw new ApiError("Сервер недоступен. Проверьте подключение к сети и повторите действие.", 0, "network_error");
  }

  if (!response.ok) {
    let payload: { code?: string; message?: string; details?: Record<string, unknown> | null } = {};
    try {
      payload = await response.json();
    } catch {
      // Ответ без тела (например, от Nginx при перезапуске) - текст и код по статусу.
    }
    if (response.status === 401) onUnauthorized();
    throw new ApiError(
      payload.message || fallbackMessage(response.status),
      response.status,
      payload.code || fallbackCode(response.status),
      payload.details ?? null,
    );
  }
  return response;
}

export async function api<T>(path: string, options: RequestOptions = {}): Promise<T> {
  const response = await send(path, options);
  if (response.status === 204) return undefined as T;
  return (await response.json()) as T;
}

export interface DownloadedFile {
  blob: Blob;
  filename: string;
}

/** Файл из ответа API: отчёт, диаграмма, вложение, образец для импорта. */
export async function download(path: string, options: RequestOptions = {}): Promise<DownloadedFile> {
  const response = await send(path, options);
  const disposition = response.headers.get("Content-Disposition") || "";
  const encoded = /filename\*=UTF-8''([^;]+)/i.exec(disposition)?.[1];
  const plain = /filename="?([^";]+)"?/i.exec(disposition)?.[1];
  const filename = encoded ? decodeURIComponent(encoded) : plain || "file";
  return { blob: await response.blob(), filename };
}

/** Сохраняет файл на диск пользователя через временную ссылку. */
export function saveFile({ blob, filename }: DownloadedFile): void {
  const url = URL.createObjectURL(blob);
  const link = document.createElement("a");
  link.href = url;
  link.download = filename;
  document.body.appendChild(link);
  link.click();
  link.remove();
  window.setTimeout(() => URL.revokeObjectURL(url), 1000);
}

export function errorMessage(error: unknown): string {
  if (error instanceof ApiError) return error.message;
  if (error instanceof Error) return error.message;
  return "Неизвестная ошибка";
}
