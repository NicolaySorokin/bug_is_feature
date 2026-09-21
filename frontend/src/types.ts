export type Role = "manager" | "head" | "admin";

export type ContractStatus = "draft" | "active" | "suspended" | "closed";
export type StageState = "not_started" | "active" | "completed" | "skipped" | "blocked";

export interface User {
  id: string;
  username: string;
  full_name: string;
  email: string;
  is_active: boolean;
  roles: Role[];
}

export interface Alert {
  kind: string;
  kind_label: string;
  severity: "info" | "warning" | "critical";
  severity_label: string;
  message: string;
  contract_id?: string | null;
  contract_number?: string | null;
  university_name?: string | null;
  manager_name?: string | null;
  days?: number | null;
}

export interface Dashboard {
  role: Role;
  generated_at: string;
  counters: {
    contracts: number;
    contracts_active: number;
    contracts_draft: number;
    universities: number;
    my_contracts: number;
    processes_in_progress: number;
    processes_blocked: number;
    processes_completed: number;
    alerts: number;
  };
  alerts: Alert[];
  alerts_summary: { kind: string; label: string; count: number }[];
  charts: { key: string; title: string; items: { label: string; value: number }[] }[];
  manager_load: { manager_id: string; manager_name: string; contracts: number; active: number; blocked: number }[];
  recent: { entity_type: string; entity_id: string; action: string; user_name?: string | null; created_at: string; summary: string }[];
}

export interface University {
  id: string;
  name: string;
  short_name?: string | null;
  city?: string | null;
  website?: string | null;
  description?: string | null;
  manager_id?: string | null;
  is_active: boolean;
  contacts?: { id: string; full_name: string; position?: string | null; email?: string | null; phone?: string | null }[];
}

export interface Program {
  id: string;
  name: string;
  direction_id?: string | null;
  direction?: { id: string; name: string } | null;
}

export interface Product {
  id: string;
  name: string;
  vendor_id?: string | null;
  vendor?: { id: string; name: string } | null;
}

export interface Contract {
  id: string;
  university_id: string;
  university?: University | null;
  manager_id?: string | null;
  number: string;
  title?: string | null;
  signed_at?: string | null;
  valid_from?: string | null;
  valid_to?: string | null;
  status: ContractStatus;
  comment?: string | null;
  programs?: { id: string; program_id: string; implementation_status: string; program?: Program | null }[];
  products?: { id: string; product_id: string; transfer_status: string; product?: Product | null }[];
}

export interface WorkflowStage {
  id: string;
  code: string;
  name: string;
  description?: string | null;
  sort_order: number;
  is_optional: boolean;
  is_final: boolean;
  sla_days?: number | null;
  layout_x?: number | null;
  layout_y?: number | null;
}

export interface WorkflowTransition {
  id: string;
  from_stage_id: string;
  to_stage_id: string;
  name?: string | null;
  is_backward: boolean;
  requires_comment: boolean;
}

export interface WorkflowEvent {
  id: string;
  from_stage_id?: string | null;
  to_stage_id?: string | null;
  user_id?: string | null;
  event_type: string;
  comment?: string | null;
  created_at: string;
}

export interface WorkflowView {
  id: string;
  contract_id: string;
  workflow_version_id: string;
  current_stage_id?: string | null;
  status: "in_progress" | "blocked" | "completed" | "cancelled";
  current_stage_started_at?: string | null;
  started_at?: string | null;
  completed_at?: string | null;
  version: {
    id: string;
    template_id: string;
    version_number: number;
    published_at?: string | null;
    stages: WorkflowStage[];
    transitions: WorkflowTransition[];
  };
  stage_states: { stage_id: string; state: StageState }[];
  available_transitions: WorkflowTransition[];
  events: WorkflowEvent[];
}

export interface Report {
  title: string;
  generated_at: string;
  filters: Record<string, unknown>;
  columns: string[];
  column_titles: Record<string, string>;
  totals: { rows: number; contracts: number; universities: number; programs: number; products: number };
  rows: {
    contract_id: string;
    university: string;
    direction: string;
    program: string;
    product: string;
    contract_number: string;
    contract_status: ContractStatus;
    stage: string;
    days_on_stage?: number | null;
    manager: string;
    valid_to?: string | null;
  }[];
  charts: { key: string; title: string; measure: string; items: { label: string; value: number }[] }[];
}

export interface Page<T> {
  items: T[];
  total: number;
  limit: number;
  offset: number;
}

export type DataSource = "api" | "demo";
export interface Loaded<T> {
  data: T;
  source: DataSource;
  error?: string;
}
