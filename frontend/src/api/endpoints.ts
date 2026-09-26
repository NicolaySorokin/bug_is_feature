/** Вызовы API по разделам. Пути и тела - как в Swagger UI (/docs). */
import { api, download, type Query } from "./client";
import type {
  Alert,
  Application,
  Attachment,
  AuditEntry,
  ColumnInfo,
  Comment,
  ContractContact,
  ContractCreate,
  ContractDetail,
  ContractListItem,
  ContractProduct,
  ContractProgram,
  ContractUpdate,
  Dashboard,
  Direction,
  ExportFormat,
  GraphWrite,
  ImportPreview,
  ImportResult,
  ImportRun,
  ImportType,
  ImportTypeInfo,
  IntegrationRun,
  IntegrationSource,
  License,
  LicenseCreate,
  LicenseListItem,
  Me,
  MetaEnums,
  Page,
  Product,
  Program,
  ProgramProductLink,
  Report,
  ReportRequest,
  RoleSyncResult,
  Setting,
  Stage,
  Statistics,
  StatisticsFilters,
  Template,
  UniversityContact,
  UniversityContactCreate,
  UniversityCreate,
  UniversityDetail,
  UniversityListItem,
  UniversityUpdate,
  User,
  UserCreate,
  UserDetail,
  UserUpdate,
  Vendor,
  VendorContact,
  Version,
  VersionGraph,
  WorkflowView,
} from "./types";

// --- Сервис -----------------------------------------------------------------

export const getMe = () => api<Me>("/me");
export const getEnums = () => api<MetaEnums>("/meta/enums");

// --- Сотрудники -------------------------------------------------------------

export const listUsers = (query: Query = {}) => api<Page<User>>("/users", { query: { limit: 500, ...query } });
export const getUser = (id: string) => api<UserDetail>(`/users/${id}`);
export const createUser = (body: UserCreate) => api<UserDetail>("/users", { method: "POST", body });
export const updateUser = (id: string, body: UserUpdate) => api<UserDetail>(`/users/${id}`, { method: "PATCH", body });
export const resetPassword = (id: string, password: string, temporary: boolean) =>
  api<void>(`/users/${id}/reset-password`, { method: "POST", body: { password, temporary } });
export const syncRoles = () => api<RoleSyncResult>("/users/sync-roles", { method: "POST" });

// --- Главная ----------------------------------------------------------------

export const getDashboard = () => api<Dashboard>("/dashboard");
export const getAlerts = (query: Query = {}) => api<Alert[]>("/dashboard/alerts", { query });

// --- Вузы -------------------------------------------------------------------

export const listUniversities = (query: Query = {}) =>
  api<Page<UniversityListItem>>("/universities", { query: { limit: 500, ...query } });
export const getUniversity = (id: string) => api<UniversityDetail>(`/universities/${id}`);
export const createUniversity = (body: UniversityCreate) => api<UniversityDetail>("/universities", { method: "POST", body });
export const updateUniversity = (id: string, body: UniversityUpdate) =>
  api<UniversityDetail>(`/universities/${id}`, { method: "PATCH", body });
export const deleteUniversity = (id: string) => api<void>(`/universities/${id}`, { method: "DELETE" });
export const createContact = (universityId: string, body: UniversityContactCreate) =>
  api<UniversityContact>(`/universities/${universityId}/contacts`, { method: "POST", body });
export const updateContact = (universityId: string, contactId: string, body: Partial<UniversityContact>) =>
  api<UniversityContact>(`/universities/${universityId}/contacts/${contactId}`, { method: "PATCH", body });
export const deleteContact = (universityId: string, contactId: string) =>
  api<void>(`/universities/${universityId}/contacts/${contactId}`, { method: "DELETE" });

// --- Справочники ------------------------------------------------------------

export const listDirections = () => api<Direction[]>("/catalog/directions");
export const listPrograms = () => api<Program[]>("/catalog/programs");
export const listVendors = () => api<Vendor[]>("/catalog/vendors");
export const listProducts = () => api<Product[]>("/catalog/products");
export const listProgramProducts = () => api<ProgramProductLink[]>("/catalog/program-products");

type CatalogKind = "directions" | "programs" | "vendors" | "products";
export const createCatalogItem = <T>(kind: CatalogKind, body: Record<string, unknown>) =>
  api<T>(`/catalog/${kind}`, { method: "POST", body });
export const updateCatalogItem = <T>(kind: CatalogKind, id: string, body: Record<string, unknown>) =>
  api<T>(`/catalog/${kind}/${id}`, { method: "PATCH", body });
export const setProgramProducts = (programId: string, productIds: string[]) =>
  api<ProgramProductLink[]>(`/catalog/programs/${programId}/products`, {
    method: "PUT",
    body: { product_ids: productIds },
  });
export const createVendorContact = (vendorId: string, body: Partial<VendorContact>) =>
  api<VendorContact>(`/catalog/vendors/${vendorId}/contacts`, { method: "POST", body });
export const updateVendorContact = (id: string, body: Partial<VendorContact>) =>
  api<VendorContact>(`/catalog/vendor-contacts/${id}`, { method: "PATCH", body });
export const deleteVendorContact = (id: string) => api<void>(`/catalog/vendor-contacts/${id}`, { method: "DELETE" });

// --- Договоры ---------------------------------------------------------------

export const listContracts = (query: Query = {}) => api<Page<ContractListItem>>("/contracts", { query });
export const getContract = (id: string) => api<ContractDetail>(`/contracts/${id}`);
export const createContract = (body: ContractCreate) => api<ContractDetail>("/contracts", { method: "POST", body });
export const updateContract = (id: string, body: ContractUpdate) =>
  api<ContractDetail>(`/contracts/${id}`, { method: "PATCH", body });
export const deleteContract = (id: string) => api<void>(`/contracts/${id}`, { method: "DELETE" });
export const addContractProgram = (id: string, programId: string) =>
  api<ContractProgram>(`/contracts/${id}/programs`, { method: "POST", body: { program_id: programId } });
export const updateContractProgram = (id: string, linkId: string, status: string) =>
  api<ContractProgram>(`/contracts/${id}/programs/${linkId}`, {
    method: "PATCH",
    body: { implementation_status: status },
  });
export const removeContractProgram = (id: string, linkId: string) =>
  api<void>(`/contracts/${id}/programs/${linkId}`, { method: "DELETE" });
export const addContractProduct = (id: string, productId: string) =>
  api<ContractProduct>(`/contracts/${id}/products`, { method: "POST", body: { product_id: productId } });
export const updateContractProduct = (id: string, linkId: string, status: string) =>
  api<ContractProduct>(`/contracts/${id}/products/${linkId}`, { method: "PATCH", body: { transfer_status: status } });
export const removeContractProduct = (id: string, linkId: string) =>
  api<void>(`/contracts/${id}/products/${linkId}`, { method: "DELETE" });
export const putContractContact = (id: string, body: { contact_id: string; role?: string | null; is_primary?: boolean }) =>
  api<ContractContact>(`/contracts/${id}/contacts`, { method: "PUT", body });
export const removeContractContact = (id: string, contactId: string) =>
  api<void>(`/contracts/${id}/contacts/${contactId}`, { method: "DELETE" });

// --- Лицензии ---------------------------------------------------------------

export const createLicense = (contractId: string, linkId: string, body: LicenseCreate) =>
  api<License>(`/contracts/${contractId}/products/${linkId}/licenses`, { method: "POST", body });
export const updateLicense = (id: string, body: Partial<LicenseCreate>) =>
  api<License>(`/licenses/${id}`, { method: "PATCH", body });
export const deleteLicense = (id: string) => api<void>(`/licenses/${id}`, { method: "DELETE" });

// --- Рабочий процесс ----------------------------------------------------------

export const getWorkflow = (contractId: string) => api<WorkflowView>(`/contracts/${contractId}/workflow`);
export const startWorkflow = (contractId: string, templateId: string) =>
  api<WorkflowView>(`/contracts/${contractId}/workflow`, { method: "POST", body: { template_id: templateId } });
export const transition = (instanceId: string, toStageId: string, comment?: string) =>
  api<WorkflowView>(`/workflow/instances/${instanceId}/transition`, {
    method: "POST",
    body: { to_stage_id: toStageId, comment: comment || null },
  });
export const skipStage = (instanceId: string, toStageId: string, reason: string) =>
  api<WorkflowView>(`/workflow/instances/${instanceId}/skip`, {
    method: "POST",
    body: { to_stage_id: toStageId, reason },
  });
export const blockWorkflow = (instanceId: string, reason: string) =>
  api<WorkflowView>(`/workflow/instances/${instanceId}/block`, { method: "POST", body: { reason } });
export const unblockWorkflow = (instanceId: string, reason: string) =>
  api<WorkflowView>(`/workflow/instances/${instanceId}/unblock`, { method: "POST", body: { reason } });

export const listTemplates = () => api<Template[]>("/workflow/templates");
export const listVersions = (templateId: string) => api<Version[]>(`/workflow/templates/${templateId}/versions`);
export const getVersion = (versionId: string) => api<VersionGraph>(`/workflow/versions/${versionId}`);
export const createTemplate = (body: { name: string; description?: string | null; graph?: GraphWrite | null }) =>
  api<VersionGraph>("/workflow/templates", { method: "POST", body });
export const updateTemplate = (id: string, body: Partial<Template>) =>
  api<Template>(`/workflow/templates/${id}`, { method: "PATCH", body });
export const createVersion = (templateId: string, fromVersionId?: string) =>
  api<VersionGraph>(`/workflow/templates/${templateId}/versions`, {
    method: "POST",
    body: { copy_graph: true, from_version_id: fromVersionId || null },
  });
export const saveGraph = (versionId: string, body: GraphWrite) =>
  api<VersionGraph>(`/workflow/versions/${versionId}/graph`, { method: "PUT", body });
export const saveLayout = (versionId: string, stages: { stage_id: string; layout_x: number; layout_y: number }[]) =>
  api<VersionGraph>(`/workflow/versions/${versionId}/layout`, { method: "PUT", body: { stages } });
export const publishVersion = (versionId: string) => api<Version>(`/workflow/versions/${versionId}/publish`, { method: "POST" });
export const deleteVersion = (versionId: string) => api<void>(`/workflow/versions/${versionId}`, { method: "DELETE" });
export const renameStage = (stageId: string, body: { name?: string; description?: string | null }) =>
  api<Stage>(`/workflow/stages/${stageId}`, { method: "PATCH", body });

// --- Комментарии и файлы ----------------------------------------------------

export const listComments = (contractId: string) => api<Comment[]>(`/contracts/${contractId}/comments`);
export const createComment = (contractId: string, text: string, eventId?: string | null) =>
  api<Comment>(`/contracts/${contractId}/comments`, {
    method: "POST",
    body: { text, workflow_event_id: eventId || null },
  });
export const listAttachments = (contractId: string) => api<Attachment[]>(`/contracts/${contractId}/attachments`);
export function uploadAttachment(contractId: string, file: File, eventId?: string | null): Promise<Attachment> {
  const form = new FormData();
  form.append("file", file);
  if (eventId) form.append("workflow_event_id", eventId);
  return api<Attachment>(`/contracts/${contractId}/attachments`, { method: "POST", body: form });
}
export const downloadAttachment = (id: string) => download(`/attachments/${id}/download`);
export const deleteAttachment = (id: string) => api<void>(`/attachments/${id}`, { method: "DELETE" });

// --- Отчёты и статистика ----------------------------------------------------

export const listReportColumns = () => api<ColumnInfo[]>("/reports/columns");
export const previewReport = (body: ReportRequest) => api<Report>("/reports/preview", { method: "POST", body });
export const exportReport = (body: ReportRequest, format: ExportFormat) =>
  download("/reports/export", { method: "POST", body, query: { format } });
export const exportReportChart = (body: ReportRequest, key: string, format: "png" | "pdf") =>
  download("/reports/chart", { method: "POST", body, query: { key, format } });

export const getStatistics = (body: StatisticsFilters) => api<Statistics>("/statistics/programs", { method: "POST", body });
export const exportStatistics = (body: StatisticsFilters, format: ExportFormat) =>
  download("/statistics/export", { method: "POST", body, query: { format } });
export const exportStatisticsChart = (body: StatisticsFilters, key: string, format: "png" | "pdf") =>
  download("/statistics/chart", { method: "POST", body, query: { key, format } });
export const listApplications = (query: Query = {}) => api<Page<Application>>("/statistics/applications", { query });
export interface StreamStatistics {
  stream: number | null;
  applications: number | null;
  learners: number | null;
}
export const getProgramStreams = (programId: string) => api<StreamStatistics[]>(`/statistics/programs/${programId}/streams`);
export const listLicenses = (query: Query = {}) => api<Page<LicenseListItem>>("/licenses", { query });

// --- Интеграции -------------------------------------------------------------

export const listSources = () => api<IntegrationSource[]>("/integrations/sources");
export const updateSource = (code: string, isEnabled: boolean) =>
  api<IntegrationSource>(`/integrations/sources/${code}`, { method: "PATCH", body: { is_enabled: isEnabled } });
export const syncSource = (code: string) => api<IntegrationRun>(`/integrations/sources/${code}/sync`, { method: "POST" });
export const syncAll = () => api<IntegrationRun[]>("/integrations/sync", { method: "POST" });
export function uploadSourcePayload(code: string, file: File): Promise<IntegrationRun> {
  const form = new FormData();
  form.append("file", file);
  return api<IntegrationRun>(`/integrations/sources/${code}/upload`, { method: "POST", body: form });
}
export const listRuns = (query: Query = {}) => api<IntegrationRun[]>("/integrations/runs", { query: { limit: 50, ...query } });

// --- Импорт -----------------------------------------------------------------

export const listImportTypes = () => api<ImportTypeInfo[]>("/imports/types");
export const listImportRuns = () => api<ImportRun[]>("/imports", { query: { limit: 30 } });
export const downloadImportTemplate = (type: ImportType) => download("/imports/template", { query: { type } });
export function uploadImport(file: File, type: ImportType): Promise<ImportPreview> {
  const form = new FormData();
  form.append("file", file);
  form.append("type", type);
  return api<ImportPreview>("/imports", { method: "POST", body: form });
}
export const validateImport = (runId: string, mapping: Record<string, string | null>) =>
  api<ImportResult>(`/imports/${runId}/validate`, { method: "POST", body: { mapping } });
export const commitImport = (runId: string, mapping: Record<string, string | null>) =>
  api<ImportResult>(`/imports/${runId}/commit`, { method: "POST", body: { mapping } });
export const getImport = (runId: string) => api<ImportResult>(`/imports/${runId}`);

// --- Журнал и настройки -----------------------------------------------------

export const listAudit = (query: Query = {}) => api<Page<AuditEntry>>("/audit", { query });
export const getSettings = () => api<Setting[]>("/settings");
export const saveSettings = (values: Record<string, number>) => api<Setting[]>("/settings", { method: "PUT", body: { values } });
