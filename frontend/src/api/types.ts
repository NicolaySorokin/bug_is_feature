/**
 * Типы данных API.
 *
 * Источник - схема OpenAPI сервера (docs/openapi.json): `npm run api:types`
 * генерирует из неё schema.d.ts, а здесь даны короткие имена. Поэтому
 * клиент и сервер не расходятся: изменилась схема - перестанет собираться
 * код, который её использует.
 */
import type { components } from "./schema";

type S = components["schemas"];

export type Role = "manager" | "head" | "admin";
export type ContractStatus = S["ContractStatus"];
export type ImplementationStatus = S["ImplementationStatus"];
export type LicenseStatus = S["LicenseStatus"];
export type StageState = S["StageState"];
export type WorkflowStatus = S["WorkflowInstanceStatus"];
export type WorkflowEventType = S["WorkflowEventType"];
export type AlertKind = S["AlertKind"];
export type AlertSeverity = S["AlertSeverity"];
export type ImportType = S["ImportType"];
export type ImportRunStatus = S["ImportRunStatus"];
export type IntegrationRunStatus = S["IntegrationRunStatus"];
export type DataScope = S["DataScope"];
export type ReportColumn = S["ReportColumn"];
export type ChartKey = S["ChartKey"];
export type PeriodBasis = S["PeriodBasis"];
export type ExportFormat = S["ExportFormat"];

export type Page<T> = { items: T[]; total: number; limit: number; offset: number };

export type AuthConfig = S["AuthConfig"];
export type DemoAccount = S["DemoAccount"];
export type Me = S["MeRead"];
export type User = S["UserRead"];
export type UserDetail = S["UserDetail"];
export type UserCreate = S["UserCreate"];
export type UserUpdate = S["UserUpdate"];
export type RoleSyncResult = S["RoleSyncResult"];

export type University = S["UniversityRead"];
export type UniversityListItem = S["UniversityListItem"];
export type UniversityDetail = S["UniversityDetail"];
export type UniversityContact = S["UniversityContactRead"];
export type UniversityCreate = S["UniversityCreate"];
export type UniversityUpdate = S["UniversityUpdate"];
export type UniversityContactCreate = S["UniversityContactCreate"];

export type Direction = S["ItDirectionRead"];
export type Program = S["ItProgramRead"];
export type Product = S["ItProductRead"];
export type Vendor = S["VendorRead"];
export type VendorContact = S["VendorContactRead"];
export type ProgramProductLink = S["ProgramProductLink"];

export type ContractListItem = S["ContractListItem"];
export type ContractDetail = S["ContractDetail"];
export type ContractCreate = S["ContractCreate"];
export type ContractUpdate = S["ContractUpdate"];
export type ContractProgram = S["ContractProgramRead"];
export type ContractProduct = S["ContractProductRead"];
export type ContractContact = S["ContractContactRead"];
export type ProcessSummary = S["ProcessSummary"];
export type License = S["LicenseRead"];
export type LicenseCreate = S["LicenseCreate"];
export type LicenseListItem = S["LicenseListItem"];

export type Stage = S["StageRead"];
export type Transition = S["TransitionRead"];
export type WorkflowEvent = S["EventRead"];
export type WorkflowView = S["InstanceView"];
export type Template = S["TemplateRead"];
export type Version = S["VersionRead"];
export type VersionGraph = S["VersionGraph"];
export type GraphWrite = S["GraphWrite"];
export type StageWrite = S["StageWrite"];
export type TransitionWrite = S["TransitionWrite"];

export type Comment = S["CommentRead"];
export type Attachment = S["AttachmentRead"];

export type Alert = S["AlertRead"];
export type Dashboard = S["DashboardResponse"];
export type NextAction = S["NextAction"];
export type ManagerLoad = S["ManagerLoad"];
export type RecentChange = S["RecentChange"];
export type AdminSummary = S["AdminSummary"];

export type ReportFilters = S["ReportFilters"];
export type ReportRequest = S["ReportRequest"];
export type Report = S["ReportResponse"];
export type ReportRow = S["ReportRow"];
export type ColumnInfo = S["ColumnInfo"];
export type ChartData = S["ChartData"];

export type StatisticsFilters = S["StatisticsFilters"];
export type Statistics = S["StatisticsResponse"];
export type ProgramStatistics = S["ProgramStatistics"];
export type Application = S["ApplicationRead"];

export type IntegrationSource = S["IntegrationSourceRead"];
export type IntegrationRun = S["IntegrationRunRead"];

export type ImportTypeInfo = S["ImportTypeInfo"];
export type ImportPreview = S["ImportPreview"];
export type ImportResult = S["ImportResult"];
export type ImportRun = S["ImportRunRead"];

export type AuditEntry = S["AuditEntryRead"];
export type Setting = S["SettingRead"];

export interface MetaEnums {
  labels: Record<string, Record<string, string>>;
  error_codes: string[];
  uploads: { allowed_extensions: string[]; max_size_mb: number };
  alerts: { default_sla_days: number; expiring_days: number };
}
