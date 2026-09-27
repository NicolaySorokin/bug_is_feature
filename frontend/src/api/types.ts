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

export type Role = S["Role"];
export type DataScope = S["DataScope"];
export type UserPermission = S["Permission"];
export type UniversityStatus = S["UniversityStatus"];
export type InteractionStatus = S["InteractionStatus"];
export type InteractionOutcome = S["InteractionOutcome"];
export type InteractionSource = S["InteractionSource"];
export type ClosureReason = S["ClosureReason"];
export type ContractStatus = S["ContractStatus"];
export type ContractClosureReason = S["ContractClosureReason"];
export type ProgramStatus = S["ProgramImplementationStatus"];
export type ProductStatus = S["ProductTransferStatus"];
export type LicenseStatus = S["LicenseStatus"];
export type StageState = S["StageState"];
export type SlaState = S["SlaState"];
export type DocumentType = S["DocumentType"];
export type WorkflowEventType = S["WorkflowEventType"];
export type WorkflowVersionStatus = S["WorkflowVersionStatus"];
export type AlertKind = S["AlertKind"];
export type AlertSeverity = S["AlertSeverity"];
export type ImportType = S["ImportType"];
export type ImportRunStatus = S["ImportRunStatus"];
export type IntegrationRunStatus = S["IntegrationRunStatus"];
export type MappingStatus = S["MappingStatus"];
export type ReportColumn = S["ReportColumn"];
export type ChartKey = S["ChartKey"];
export type PeriodBasis = S["PeriodBasis"];
export type ExportFormat = S["ExportFormat"];
export type InteractionOrder = S["InteractionOrder"];

export type Page<T> = { items: T[]; total: number; limit: number; offset: number };

export type AuthConfig = S["AuthConfig"];
export type DemoAccount = S["DemoAccount"];
export type Me = S["MeRead"];
export type User = S["UserRead"];
export type UserBrief = S["UserBrief"];
export type UserDetail = S["UserDetail"];
export type UserCreate = S["UserCreate"];
export type UserUpdate = S["UserUpdate"];
export type AccessGrant = S["AccessGrantRead"];
export type AccessGrantWrite = S["AccessGrantWrite"];
export type RoleSyncResult = S["RoleSyncResult"];

export type UniversityBrief = S["UniversityBrief"];
export type UniversityListItem = S["UniversityListItem"];
export type UniversityDetail = S["UniversityDetail"];
export type UniversityContact = S["UniversityContactRead"];
export type UniversityCreate = S["UniversityCreate"];
export type UniversityUpdate = S["UniversityUpdate"];
export type UniversityContactCreate = S["UniversityContactCreate"];
export type DuplicateCandidate = S["DuplicateCandidate"];

export type Direction = S["ItDirectionRead"];
export type Program = S["ItProgramRead"];
export type Product = S["ItProductRead"];
export type Vendor = S["VendorRead"];
export type VendorContact = S["VendorContactRead"];
export type ProgramProductLink = S["ProgramProductLink"];

export type InteractionListItem = S["InteractionListItem"];
export type InteractionDetail = S["InteractionDetail"];
export type InteractionCreate = S["InteractionCreate"];
export type InteractionUpdate = S["InteractionUpdate"];
export type InteractionProgram = S["InteractionProgramRead"];
export type InteractionProduct = S["InteractionProductRead"];
export type InteractionContact = S["InteractionContactRead"];
export type ProgramProductLinkRead = S["ProgramProductLinkRead"];
export type StageSummary = S["StageSummary"];
export type StageSla = S["StageSla"];

export type Contract = S["ContractRead"];
export type ContractBrief = S["ContractBrief"];
export type ContractWrite = S["ContractWrite"];
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
export type DashboardCounters = S["DashboardCounters"];
export type NextStep = S["NextStep"];
export type ControlItem = S["ControlItem"];
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
export type IntegrationMapping = S["MappingRead"];

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
