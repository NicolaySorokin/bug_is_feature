/** Вызовы API по разделам. Пути и тела - как в Swagger UI (/docs). */
import { api, download, type Query } from "./client";
import type {
  AccessGrantWrite,
  Alert,
  Application,
  Attachment,
  AuditEntry,
  ClosureReason,
  ColumnInfo,
  Comment,
  Contract,
  ContractDocumentPreview,
  ContractTemplate,
  ContractTemplateWrite,
  ContractWrite,
  Dashboard,
  Direction,
  DocumentType,
  DuplicateCandidate,
  ExportFormat,
  GraphWrite,
  ImportPreview,
  ImportResult,
  ImportRun,
  ImportType,
  ImportTypeInfo,
  IntegrationMapping,
  IntegrationRun,
  IntegrationSource,
  InteractionContact,
  InteractionCreate,
  InteractionDetail,
  InteractionListItem,
  InteractionProduct,
  InteractionProgram,
  InteractionUpdate,
  License,
  LicenseCreate,
  LicenseListItem,
  Me,
  MetaEnums,
  Page,
  Product,
  ProductStatus,
  Program,
  ProgramProductLink,
  ProgramStatus,
  Report,
  ReportRequest,
  RoleSyncResult,
  Setting,
  Stage,
  Statistics,
  StatisticsFilters,
  Template,
  TemplateField,
  UniversityContact,
  UniversityContactCreate,
  UniversityCreate,
  UniversityDetail,
  UniversityListItem,
  UniversityUpdate,
  User,
  UserBrief,
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
/** Кого сотрудник может назначить ответственным или выбрать в фильтре. */
export const listDirectory = (role: "manager" | "head" = "manager") => api<UserBrief[]>("/users/directory", { query: { role } });
export const getUser = (id: string) => api<UserDetail>(`/users/${id}`);
export const createUser = (body: UserCreate) => api<UserDetail>("/users", { method: "POST", body });
export const updateUser = (id: string, body: UserUpdate) => api<UserDetail>(`/users/${id}`, { method: "PATCH", body });
export const grantUniversity = (id: string, body: AccessGrantWrite) =>
  api<UserDetail>(`/users/${id}/grants`, { method: "PUT", body });
export const revokeUniversity = (id: string, universityId: string) =>
  api<UserDetail>(`/users/${id}/grants/${universityId}`, { method: "DELETE" });
export const resetPassword = (id: string, password: string) =>
  api<void>(`/users/${id}/reset-password`, { method: "POST", body: { password } });
export const syncRoles = () => api<RoleSyncResult>("/users/sync-roles", { method: "POST" });

// --- Главная ----------------------------------------------------------------

export const getDashboard = () => api<Dashboard>("/dashboard");
export const getAlerts = (query: Query = {}) => api<Alert[]>("/dashboard/alerts", { query });
/** Отметить уведомления колокольчика прочитанными: по ключам или все сразу. */
export const markAlertsRead = (alertKeys: string[] | null) =>
  alertKeys
    ? api<void>("/dashboard/alerts/read", { method: "POST", body: { keys: alertKeys } })
    : api<void>("/dashboard/alerts/read-all", { method: "POST" });

// --- Вузы -------------------------------------------------------------------

export const listUniversities = (query: Query = {}) =>
  api<Page<UniversityListItem>>("/universities", { query: { limit: 500, ...query } });
export const listDuplicates = () => api<DuplicateCandidate[]>("/universities/duplicates");
export const getUniversity = (id: string) => api<UniversityDetail>(`/universities/${id}`);
export const createUniversity = (body: UniversityCreate) => api<UniversityDetail>("/universities", { method: "POST", body });
export const updateUniversity = (id: string, body: UniversityUpdate) =>
  api<UniversityDetail>(`/universities/${id}`, { method: "PATCH", body });
export const deleteUniversity = (id: string) => api<void>(`/universities/${id}`, { method: "DELETE" });
export const confirmUniversity = (id: string) => api<UniversityDetail>(`/universities/${id}/confirm`, { method: "POST" });
export const archiveUniversity = (id: string) => api<UniversityDetail>(`/universities/${id}/archive`, { method: "POST" });
export const mergeUniversity = (id: string, targetId: string) =>
  api<UniversityDetail>(`/universities/${id}/merge`, { method: "POST", body: { target_id: targetId } });
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

// --- Взаимодействия ---------------------------------------------------------

const I = (id: string) => `/interactions/${id}`;

export const listInteractions = (query: Query = {}) => api<Page<InteractionListItem>>("/interactions", { query });
export const getInteraction = (id: string) => api<InteractionDetail>(I(id));
export const createInteraction = (body: InteractionCreate) => api<InteractionDetail>("/interactions", { method: "POST", body });
export const updateInteraction = (id: string, body: InteractionUpdate) =>
  api<InteractionDetail>(I(id), { method: "PATCH", body });
export const deleteInteraction = (id: string) => api<void>(I(id), { method: "DELETE" });
export const startInteraction = (id: string) => api<WorkflowView>(`${I(id)}/start`, { method: "POST" });
export const cancelInteraction = (id: string, reason: ClosureReason, comment?: string | null) =>
  api<WorkflowView>(`${I(id)}/cancel`, { method: "POST", body: { reason, comment: comment || null } });

// Программы, продукты и их связи
export const addProgram = (id: string, programId: string) =>
  api<InteractionProgram>(`${I(id)}/programs`, { method: "POST", body: { program_id: programId } });
export const updateProgram = (id: string, linkId: string, status: ProgramStatus, comment?: string | null) =>
  api<InteractionProgram>(`${I(id)}/programs/${linkId}`, {
    method: "PATCH",
    body: { implementation_status: status, comment: comment || null },
  });
export const removeProgram = (id: string, linkId: string) => api<void>(`${I(id)}/programs/${linkId}`, { method: "DELETE" });
export const addProduct = (
  id: string,
  body: { product_id: string; program_link_ids: string[]; exception_comment?: string | null },
) => api<InteractionProduct>(`${I(id)}/products`, { method: "POST", body });
export const updateProduct = (id: string, linkId: string, status: ProductStatus, comment?: string | null) =>
  api<InteractionProduct>(`${I(id)}/products/${linkId}`, {
    method: "PATCH",
    body: { transfer_status: status, comment: comment || null },
  });
export const removeProduct = (id: string, linkId: string) => api<void>(`${I(id)}/products/${linkId}`, { method: "DELETE" });
export const linkProduct = (
  id: string,
  body: { program_link_id: string; product_link_id: string; exception_comment?: string | null },
) => api<void>(`${I(id)}/links`, { method: "PUT", body });
export const unlinkProduct = (id: string, programLinkId: string, productLinkId: string) =>
  api<void>(`${I(id)}/links`, {
    method: "DELETE",
    query: { program_link_id: programLinkId, product_link_id: productLinkId },
  });

// Контакты вуза во взаимодействии
export const putInteractionContact = (id: string, body: { contact_id: string; role?: string | null; is_primary?: boolean }) =>
  api<InteractionContact>(`${I(id)}/contacts`, { method: "PUT", body });
export const removeInteractionContact = (id: string, contactId: string) =>
  api<void>(`${I(id)}/contacts/${contactId}`, { method: "DELETE" });

// Договор (0..1) и лицензии
export const getContract = (id: string) => api<Contract | null>(`${I(id)}/contract`);
export const saveContract = (id: string, body: ContractWrite) => api<Contract>(`${I(id)}/contract`, { method: "PUT", body });
export const deleteContract = (id: string) => api<void>(`${I(id)}/contract`, { method: "DELETE" });

// Типовые шаблоны договоров и договор по шаблону.
export const listContractTemplates = () => api<ContractTemplate[]>("/contract-templates");
export const listTemplateFields = () => api<TemplateField[]>("/contract-templates/fields");
export const saveContractTemplate = (id: string | null, body: ContractTemplateWrite) =>
  id
    ? api<ContractTemplate>(`/contract-templates/${id}`, { method: "PUT", body })
    : api<ContractTemplate>("/contract-templates", { method: "POST", body });
export const previewContractDocument = (id: string, templateId: string) =>
  api<ContractDocumentPreview>(`${I(id)}/contract/document/preview`, { method: "POST", body: { template_id: templateId } });
export const downloadContractDocument = (id: string, templateId: string) =>
  download(`${I(id)}/contract/document`, { method: "POST", body: { template_id: templateId } });
export const attachContractDocument = (id: string, templateId: string, eventId?: string | null) =>
  api<Attachment>(`${I(id)}/contract/document/attach`, {
    method: "POST",
    body: { template_id: templateId, workflow_event_id: eventId || null },
  });
export const listInteractionLicenses = (id: string) => api<License[]>(`${I(id)}/licenses`);
export const createLicense = (id: string, productLinkId: string, body: LicenseCreate) =>
  api<License>(`${I(id)}/products/${productLinkId}/licenses`, { method: "POST", body });
export const updateLicense = (licenseId: string, body: Partial<LicenseCreate>) =>
  api<License>(`/licenses/${licenseId}`, { method: "PATCH", body });
export const deleteLicense = (licenseId: string) => api<void>(`/licenses/${licenseId}`, { method: "DELETE" });
export const listLicenses = (query: Query = {}) => api<Page<LicenseListItem>>("/licenses", { query });

// --- Рабочий процесс ----------------------------------------------------------

export const getWorkflow = (id: string) => api<WorkflowView>(`${I(id)}/workflow`);
export const transition = (id: string, toStageId: string, comment?: string, closureReason?: ClosureReason | null) =>
  api<WorkflowView>(`${I(id)}/transition`, {
    method: "POST",
    body: { to_stage_id: toStageId, comment: comment || null, closure_reason: closureReason || null },
  });
export const skipStage = (id: string, toStageId: string, reason: string) =>
  api<WorkflowView>(`${I(id)}/skip`, { method: "POST", body: { to_stage_id: toStageId, reason } });
export const blockInteraction = (id: string, reason: string) =>
  api<WorkflowView>(`${I(id)}/block`, { method: "POST", body: { reason } });
export const unblockInteraction = (id: string, reason: string) =>
  api<WorkflowView>(`${I(id)}/unblock`, { method: "POST", body: { reason } });

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

export const listComments = (id: string) => api<Comment[]>(`${I(id)}/comments`);
export const createComment = (id: string, text: string, eventId?: string | null) =>
  api<Comment>(`${I(id)}/comments`, {
    method: "POST",
    body: { text, workflow_event_id: eventId || null },
  });
export const listAttachments = (id: string) => api<Attachment[]>(`${I(id)}/attachments`);
export function uploadAttachment(
  id: string,
  file: File,
  eventId?: string | null,
  documentType?: DocumentType | null,
): Promise<Attachment> {
  const form = new FormData();
  form.append("file", file);
  if (eventId) form.append("workflow_event_id", eventId);
  if (documentType) form.append("document_type", documentType);
  return api<Attachment>(`${I(id)}/attachments`, { method: "POST", body: form });
}
export const downloadAttachment = (attachmentId: string) => download(`/attachments/${attachmentId}/download`);
export const deleteAttachment = (attachmentId: string) => api<void>(`/attachments/${attachmentId}`, { method: "DELETE" });

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
  period: string | null;
  applications: number | null;
  learners: number | null;
}
export const getProgramStreams = (programId: string) => api<StreamStatistics[]>(`/statistics/programs/${programId}/streams`);

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
export const getRun = (runId: string) => api<IntegrationRun>(`/integrations/runs/${runId}`);
export const listMappings = (status?: string) =>
  api<IntegrationMapping[]>("/integrations/mappings", { query: status ? { status } : {} });
export const resolveMapping = (id: string, entityId: string) =>
  api<IntegrationMapping>(`/integrations/mappings/${id}/resolve`, { method: "POST", body: { entity_id: entityId } });
export const createFromMapping = (id: string) =>
  api<IntegrationMapping>(`/integrations/mappings/${id}/create`, { method: "POST" });
export const ignoreMapping = (id: string) => api<IntegrationMapping>(`/integrations/mappings/${id}/ignore`, { method: "POST" });

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
