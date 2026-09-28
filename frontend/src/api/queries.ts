/**
 * Общие запросы с кэшем React Query. Справочники живут в кэше несколько минут, после изменений
 * данные перезапрашиваются в фоне без перезагрузки страницы.
 */
import { QueryClient, useQuery } from "@tanstack/react-query";
import { ApiError } from "./client";
import * as endpoints from "./endpoints";
import { FALLBACK_LABELS } from "../lib/labels";

export const queryClient = new QueryClient({
  defaultOptions: {
    queries: {
      staleTime: 30_000,
      gcTime: 10 * 60_000,
      refetchOnWindowFocus: false,
      retry: (count, error) => {
        // 4xx повторять бессмысленно: права или данные от повтора не изменятся.
        if (error instanceof ApiError && error.status >= 400 && error.status < 500) return false;
        return count < 2;
      },
    },
  },
});

const LONG = 5 * 60_000;

export const keys = {
  me: ["me"] as const,
  enums: ["enums"] as const,
  dashboard: ["dashboard"] as const,
  alerts: ["alerts"] as const,
  users: ["users"] as const,
  universities: ["universities"] as const,
  university: (id: string) => ["university", id] as const,
  directions: ["catalog", "directions"] as const,
  programs: ["catalog", "programs"] as const,
  products: ["catalog", "products"] as const,
  vendors: ["catalog", "vendors"] as const,
  programProducts: ["catalog", "program-products"] as const,
  directory: ["directory"] as const,
  interactions: ["interactions"] as const,
  interaction: (id: string) => ["interaction", id] as const,
  workflow: (id: string) => ["workflow", id] as const,
  comments: (id: string) => ["comments", id] as const,
  attachments: (id: string) => ["attachments", id] as const,
  licenses: (id: string) => ["licenses", id] as const,
  templates: ["templates"] as const,
  contractTemplates: ["contract-templates"] as const,
  templateFields: ["contract-templates", "fields"] as const,
  versions: (templateId: string) => ["versions", templateId] as const,
  version: (versionId: string) => ["version", versionId] as const,
  sources: ["sources"] as const,
  runs: ["runs"] as const,
  mappings: ["mappings"] as const,
  imports: ["imports"] as const,
  settings: ["settings"] as const,
};

export function useEnums() {
  return useQuery({
    queryKey: keys.enums,
    queryFn: endpoints.getEnums,
    staleTime: Infinity,
    placeholderData: {
      labels: FALLBACK_LABELS,
      error_codes: [],
      uploads: { allowed_extensions: [], max_size_mb: 25 },
      alerts: { default_sla_days: 14, expiring_days: 60 },
    },
  });
}

/** Подпись значения перечисления: label("interaction_status", "blocked") даёт «Заблокировано». */
export function useLabel(): (group: string, value?: string | null) => string {
  const { data } = useEnums();
  const labels = data?.labels || FALLBACK_LABELS;
  return (group, value) => {
    if (!value) return "—";
    return labels[group]?.[value] || FALLBACK_LABELS[group]?.[value] || value;
  };
}

/** Все сотрудники, только администратору. */
export const useUsers = (enabled = true) =>
  useQuery({
    queryKey: keys.users,
    queryFn: () => endpoints.listUsers().then((page) => page.items),
    staleTime: LONG,
    enabled,
  });

/** Менеджеры, которых сотрудник может назначить или выбрать в фильтре. */
export const useDirectory = () =>
  useQuery({ queryKey: keys.directory, queryFn: () => endpoints.listDirectory("manager"), staleTime: LONG });

export const useUniversities = () =>
  useQuery({
    queryKey: keys.universities,
    queryFn: () => endpoints.listUniversities().then((page) => page.items),
    staleTime: LONG,
  });

/**
 * Этапы опубликованных версий шаблонов: название и все его id.
 *
 * У каждой версии свои записи этапов, поэтому фильтр по названию отправляет id во всех версиях.
 */
export interface StageIndex {
  names: string[];
  ids: Record<string, string[]>;
}

export const useStageIndex = () =>
  useQuery({
    queryKey: ["stage-names"],
    staleTime: LONG,
    queryFn: async (): Promise<StageIndex> => {
      const index: StageIndex = { names: [], ids: {} };
      const templates = await endpoints.listTemplates();
      for (const template of templates) {
        const versions = (await endpoints.listVersions(template.id))
          .filter((version) => version.status !== "draft")
          .sort((left, right) => right.version_number - left.version_number);
        for (const version of versions) {
          const graph = await endpoints.getVersion(version.id);
          [...(graph.stages || [])]
            .sort((left, right) => left.sort_order - right.sort_order)
            .forEach((stage) => {
              // Порядок названий как в самой новой версии действующего шаблона.
              if (!index.ids[stage.name]) {
                index.ids[stage.name] = [];
                if (template.is_active) index.names.push(stage.name);
              }
              index.ids[stage.name].push(stage.id);
            });
        }
      }
      return index;
    },
  });

/** Названия этапов действующих шаблонов для фильтра «Этап». */
export function useStageNames() {
  const index = useStageIndex();
  return { ...index, data: index.data?.names };
}

export const useDirections = () => useQuery({ queryKey: keys.directions, queryFn: endpoints.listDirections, staleTime: LONG });
export const usePrograms = () => useQuery({ queryKey: keys.programs, queryFn: endpoints.listPrograms, staleTime: LONG });
export const useProducts = () => useQuery({ queryKey: keys.products, queryFn: endpoints.listProducts, staleTime: LONG });
export const useVendors = () => useQuery({ queryKey: keys.vendors, queryFn: endpoints.listVendors, staleTime: LONG });
export const useTemplates = () => useQuery({ queryKey: keys.templates, queryFn: endpoints.listTemplates, staleTime: LONG });

/** Данные изменились: всё, что зависит от взаимодействий, перезапросится в фоне. */
export function invalidateInteractionData(interactionId?: string): void {
  void queryClient.invalidateQueries({ queryKey: keys.dashboard });
  void queryClient.invalidateQueries({ queryKey: keys.alerts });
  void queryClient.invalidateQueries({ queryKey: keys.interactions });
  void queryClient.invalidateQueries({ queryKey: keys.universities });
  void queryClient.invalidateQueries({ queryKey: ["university"] });
  void queryClient.invalidateQueries({ queryKey: ["report"] });
  void queryClient.invalidateQueries({ queryKey: ["statistics"] });
  void queryClient.invalidateQueries({ queryKey: ["search"] });
  void queryClient.invalidateQueries({ queryKey: ["license-registry"] });
  if (interactionId) {
    void queryClient.invalidateQueries({ queryKey: keys.interaction(interactionId) });
    void queryClient.invalidateQueries({ queryKey: keys.workflow(interactionId) });
    void queryClient.invalidateQueries({ queryKey: keys.comments(interactionId) });
    void queryClient.invalidateQueries({ queryKey: keys.attachments(interactionId) });
    void queryClient.invalidateQueries({ queryKey: keys.licenses(interactionId) });
  }
}
