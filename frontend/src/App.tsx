/**
 * Маршруты приложения. Страницы грузятся лениво, поэтому первый экран открывается быстро.
 */
import { lazy, Suspense, type ReactNode } from "react";
import { createBrowserRouter, Navigate, RouterProvider } from "react-router-dom";
import { useSession, type Action } from "./auth/session";
import { EmptyState, Loading } from "./components/ui";
import { AppShell } from "./layout/AppShell";
import { ShieldOff } from "lucide-react";

const DashboardPage = lazy(() => import("./pages/DashboardPage"));
const InteractionsPage = lazy(() => import("./pages/InteractionsPage"));
const InteractionPage = lazy(() => import("./pages/interaction/InteractionPage"));
const UniversitiesPage = lazy(() => import("./pages/UniversitiesPage"));
const UniversityPage = lazy(() => import("./pages/UniversityPage"));
const ReportsPage = lazy(() => import("./pages/reports/ReportsPage"));
const IntegrationsPage = lazy(() => import("./pages/IntegrationsPage"));
const UsersPage = lazy(() => import("./pages/admin/UsersPage"));
const CatalogPage = lazy(() => import("./pages/admin/CatalogPage"));
const ImportsPage = lazy(() => import("./pages/admin/ImportsPage"));
const WorkflowsPage = lazy(() => import("./pages/admin/WorkflowsPage"));
const AuditPage = lazy(() => import("./pages/admin/AuditPage"));
const SettingsPage = lazy(() => import("./pages/admin/SettingsPage"));
const HelpPage = lazy(() => import("./pages/help/HelpPage"));
const AccountPage = lazy(() => import("./pages/AccountPage"));
const NotFoundPage = lazy(() => import("./pages/NotFoundPage"));

function Page({ children }: { children: ReactNode }) {
  return <Suspense fallback={<Loading text="Открываем раздел" />}>{children}</Suspense>;
}

/**
 * Раздел для тех, у кого есть одно из действий. Остальные видят объяснение, а не пустую страницу.
 */
function Guard({ any, business, children }: { any?: Action[]; business?: boolean; children: ReactNode }) {
  const session = useSession();
  const allowed = (!any || any.some((action) => session.can(action))) && (!business || session.business);
  if (!allowed) {
    // Администратору не советуем «обратиться к администратору»: бизнес-доступ ему выдают отдельно.
    const admin = session.can("manage_users");
    const noBusiness = business && !session.business;
    return (
      <div className="page">
        <EmptyState icon={ShieldOff} title="Раздел недоступен">
          {noBusiness && admin
            ? "Роль администратора не даёт доступа к бизнес-данным: взаимодействиям, договорам и отчётам. Если он нужен для работы, область данных выдаётся отдельно - временно, с основанием и отметкой в журнале изменений."
            : noBusiness
              ? "У вашей учётной записи нет доступа к бизнес-данным: взаимодействиям, договорам и отчётам. Если он нужен для работы, администратор может выдать область данных - в том числе временно."
              : admin
                ? "Для этого раздела нужна другая роль или отдельное право. Роли и права сотрудников назначаются в разделе «Пользователи и права»."
                : "Для этого раздела нужна другая роль или отдельное право. Если доступ нужен для работы, обратитесь к администратору системы."}
        </EmptyState>
      </div>
    );
  }
  return <>{children}</>;
}

const router = createBrowserRouter(
  [
    {
      path: "/",
      element: <AppShell />,
      children: [
        {
          index: true,
          element: (
            <Page>
              <DashboardPage />
            </Page>
          ),
        },
        {
          path: "interactions",
          element: (
            <Guard business>
              <Page>
                <InteractionsPage />
              </Page>
            </Guard>
          ),
        },
        {
          path: "interactions/:interactionId",
          element: (
            <Guard business>
              <Page>
                <InteractionPage />
              </Page>
            </Guard>
          ),
        },
        // Старые ссылки на реестр договоров ведут в реестр взаимодействий.
        { path: "contracts", element: <Navigate to="/interactions?has_contract=true" replace /> },
        { path: "contracts/*", element: <Navigate to="/interactions" replace /> },
        {
          path: "universities",
          element: (
            <Page>
              <UniversitiesPage />
            </Page>
          ),
        },
        {
          path: "universities/:universityId",
          element: (
            <Page>
              <UniversityPage />
            </Page>
          ),
        },
        {
          path: "reports",
          element: (
            <Guard any={["view_reports", "view_statistics"]}>
              <Page>
                <ReportsPage />
              </Page>
            </Guard>
          ),
        },
        {
          path: "integrations",
          element: (
            <Guard any={["view_integration_log", "sync_integrations", "resolve_mappings"]}>
              <Page>
                <IntegrationsPage />
              </Page>
            </Guard>
          ),
        },
        { path: "admin", element: <Navigate to="/admin/users" replace /> },
        {
          path: "admin/users",
          element: (
            <Guard any={["manage_users"]}>
              <Page>
                <UsersPage />
              </Page>
            </Guard>
          ),
        },
        {
          path: "admin/catalog",
          element: (
            <Guard any={["edit_catalog", "edit_program_products", "edit_contract_templates"]}>
              <Page>
                <CatalogPage />
              </Page>
            </Guard>
          ),
        },
        {
          path: "admin/imports",
          element: (
            <Guard any={["import"]}>
              <Page>
                <ImportsPage />
              </Page>
            </Guard>
          ),
        },
        {
          path: "admin/workflows",
          element: (
            <Guard any={["edit_templates"]}>
              <Page>
                <WorkflowsPage />
              </Page>
            </Guard>
          ),
        },
        {
          path: "admin/audit",
          element: (
            <Guard any={["view_audit"]}>
              <Page>
                <AuditPage />
              </Page>
            </Guard>
          ),
        },
        {
          path: "admin/settings",
          element: (
            <Guard any={["edit_settings"]}>
              <Page>
                <SettingsPage />
              </Page>
            </Guard>
          ),
        },
        {
          path: "account",
          element: (
            <Page>
              <AccountPage />
            </Page>
          ),
        },
        {
          path: "help",
          element: (
            <Page>
              <HelpPage />
            </Page>
          ),
        },
        {
          path: "help/:guide",
          element: (
            <Page>
              <HelpPage />
            </Page>
          ),
        },
        {
          path: "*",
          element: (
            <Page>
              <NotFoundPage />
            </Page>
          ),
        },
      ],
    },
  ],
  {
    future: {
      v7_relativeSplatPath: true,
      v7_fetcherPersist: true,
      v7_normalizeFormMethod: true,
      v7_partialHydration: true,
      v7_skipActionErrorRevalidation: true,
    },
  },
);

export function App() {
  return <RouterProvider router={router} future={{ v7_startTransition: true }} />;
}
