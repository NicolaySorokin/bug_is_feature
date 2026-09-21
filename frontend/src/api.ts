import { mockContracts, mockDashboard, mockReport, mockUniversities, mockUsers, mockWorkflow } from "./mock";
import type { Contract, Dashboard, DataSource, Loaded, Page, Report, User, WorkflowView } from "./types";

const API_BASE_URL = (import.meta.env.VITE_API_BASE_URL || "http://localhost:8000/api/v1").replace(/\/$/, "");
const USE_DEMO_FALLBACK = import.meta.env.VITE_USE_DEMO_FALLBACK !== "false";

export interface DemoIdentity {
  username: string;
  roles: string[];
}

let demoIdentity: DemoIdentity = {
  username: localStorage.getItem("edu-crm-demo-user") || "petrov",
  roles: (localStorage.getItem("edu-crm-demo-roles") || "manager").split(","),
};

export function getDemoIdentity(): DemoIdentity {
  return demoIdentity;
}

export function setDemoIdentity(identity: DemoIdentity): void {
  demoIdentity = identity;
  localStorage.setItem("edu-crm-demo-user", identity.username);
  localStorage.setItem("edu-crm-demo-roles", identity.roles.join(","));
}

export class ApiError extends Error {
  status: number;
  code?: string;

  constructor(message: string, status: number, code?: string) {
    super(message);
    this.name = "ApiError";
    this.status = status;
    this.code = code;
  }
}

async function request<T>(path: string, init: RequestInit = {}): Promise<T> {
  const headers = new Headers(init.headers);
  if (init.body && !(init.body instanceof FormData)) headers.set("Content-Type", "application/json");
  const token = localStorage.getItem("edu-crm-access-token");
  if (token) headers.set("Authorization", `Bearer ${token}`);
  else {
    headers.set("X-Dev-User", demoIdentity.username);
    headers.set("X-Dev-Roles", demoIdentity.roles.join(","));
  }

  const response = await fetch(`${API_BASE_URL}${path}`, { ...init, headers });
  if (!response.ok) {
    let body: { message?: string; code?: string } | null = null;
    try { body = await response.json() as { message?: string; code?: string }; } catch { /* response may be empty */ }
    throw new ApiError(body?.message || `API вернул ошибку ${response.status}`, response.status, body?.code);
  }
  if (response.status === 204) return undefined as T;
  const contentType = response.headers.get("content-type") || "";
  if (contentType.includes("application/octet-stream") || contentType.includes("application/pdf") || contentType.includes("spreadsheet")) return response.blob() as Promise<T>;
  return response.json() as Promise<T>;
}

async function load<T>(path: string, fallback: T, init?: RequestInit): Promise<Loaded<T>> {
  try {
    return { data: await request<T>(path, init), source: "api" };
  } catch (error) {
    if (!USE_DEMO_FALLBACK) throw error;
    return { data: fallback, source: "demo", error: error instanceof Error ? error.message : "API недоступен" };
  }
}

export function loadMe(): Promise<Loaded<User>> {
  const fallback = mockUsers.find((item) => item.username === demoIdentity.username) || mockUsers[0];
  return load("/me", fallback);
}

export function loadDashboard(): Promise<Loaded<Dashboard>> {
  return load("/dashboard", { ...mockDashboard, role: (demoIdentity.roles[0] || "manager") as Dashboard["role"] });
}

export function loadContracts(params: { search?: string; status?: string; manager_id?: string; limit?: number; offset?: number } = {}): Promise<Loaded<Page<Contract>>> {
  const query = new URLSearchParams();
  Object.entries(params).forEach(([key, value]) => value !== undefined && value !== "" && query.set(key, String(value)));
  const fallback = mockContracts.filter((item) => (!params.search || item.number.toLowerCase().includes(params.search.toLowerCase()) || item.title?.toLowerCase().includes(params.search.toLowerCase())) && (!params.status || item.status === params.status));
  return load(`/contracts${query.size ? `?${query.toString()}` : ""}`, { items: fallback, total: fallback.length, limit: params.limit || 50, offset: params.offset || 0 });
}

export function loadContract(id: string): Promise<Loaded<Contract>> {
  return load(`/contracts/${id}`, mockContracts.find((item) => item.id === id) || mockContracts[0]);
}

export function loadWorkflow(id: string): Promise<Loaded<WorkflowView>> {
  return load(`/contracts/${id}/workflow`, mockWorkflow(id));
}

export function loadReport(body: Record<string, unknown> = {}): Promise<Loaded<Report>> {
  return load("/reports/preview", mockReport, { method: "POST", body: JSON.stringify(body) });
}

export function loadUniversities(): Promise<Loaded<Page<unknown>>> {
  return load("/universities?limit=100", { items: mockUniversities, total: mockUniversities.length, limit: 100, offset: 0 });
}

export async function transitionWorkflow(instanceId: string, toStageId: string, comment?: string): Promise<WorkflowView> {
  return request<WorkflowView>(`/workflow/instances/${instanceId}/transition`, { method: "POST", body: JSON.stringify({ to_stage_id: toStageId, comment }) });
}

export async function blockWorkflow(instanceId: string, reason: string): Promise<WorkflowView> {
  return request<WorkflowView>(`/workflow/instances/${instanceId}/block`, { method: "POST", body: JSON.stringify({ reason }) });
}

export async function unblockWorkflow(instanceId: string, reason: string): Promise<WorkflowView> {
  return request<WorkflowView>(`/workflow/instances/${instanceId}/unblock`, { method: "POST", body: JSON.stringify({ reason }) });
}

export async function updateContract(id: string, payload: Record<string, unknown>): Promise<Contract> {
  return request<Contract>(`/contracts/${id}`, { method: "PATCH", body: JSON.stringify(payload) });
}

export async function exportReport(body: Record<string, unknown>, format: "xlsx" | "pdf"): Promise<Blob> {
  return request<Blob>(`/reports/export?format=${format}`, { method: "POST", body: JSON.stringify(body) });
}

export function apiBaseUrl(): string { return API_BASE_URL; }
