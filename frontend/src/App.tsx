/**
 * Маршруты приложения.
 *
 * Страницы загружаются по мере надобности (lazy): первый экран открывается
 * быстро, а код администрирования и справки скачивается, только когда
 * пользователь туда переходит.
 */
import { lazy, Suspense, type ReactNode } from "react";
import { createBrowserRouter, Navigate, RouterProvider } from "react-router-dom";
import { useSession, type Permission } from "./auth/session";
import { EmptyState, Loading } from "./components/ui";
import { AppShell } from "./layout/AppShell";
import { ShieldOff } from "lucide-react";

const DashboardPage = lazy(() => import("./pages/DashboardPage"));
const ContractsPage = lazy(() => import("./pages/ContractsPage"));
const ContractPage = lazy(() => import("./pages/contract/ContractPage"));
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

/** Раздел только для ролей с правом: остальные видят объяснение, а не пустую страницу. */
function Guard({ permission, children }: { permission: Permission; children: ReactNode }) {
  const { can } = useSession();
  if (!can(permission)) {
    return (
      <div className="page">
        <EmptyState icon={ShieldOff} title="Раздел недоступен">
          Для этого раздела нужна другая роль. Если доступ нужен для работы, обратитесь к администратору системы.
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
          path: "contracts",
          element: (
            <Page>
              <ContractsPage />
            </Page>
          ),
        },
        {
          path: "contracts/:contractId",
          element: (
            <Page>
              <ContractPage />
            </Page>
          ),
        },
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
            <Page>
              <ReportsPage />
            </Page>
          ),
        },
        {
          path: "integrations",
          element: (
            <Page>
              <IntegrationsPage />
            </Page>
          ),
        },
        { path: "admin", element: <Navigate to="/admin/users" replace /> },
        {
          path: "admin/users",
          element: (
            <Guard permission="manage_users">
              <Page>
                <UsersPage />
              </Page>
            </Guard>
          ),
        },
        {
          path: "admin/catalog",
          element: (
            <Guard permission="edit_catalog">
              <Page>
                <CatalogPage />
              </Page>
            </Guard>
          ),
        },
        {
          path: "admin/imports",
          element: (
            <Guard permission="import">
              <Page>
                <ImportsPage />
              </Page>
            </Guard>
          ),
        },
        {
          path: "admin/workflows",
          element: (
            <Guard permission="edit_templates">
              <Page>
                <WorkflowsPage />
              </Page>
            </Guard>
          ),
        },
        {
          path: "admin/audit",
          element: (
            <Guard permission="view_audit">
              <Page>
                <AuditPage />
              </Page>
            </Guard>
          ),
        },
        {
          path: "admin/settings",
          element: (
            <Guard permission="edit_settings">
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
