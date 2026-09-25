/**
 * Отчёты и статистика.
 *
 * «Взаимодействие с вузами» - конструктор отчёта: период, вузы,
 * направления, продукты, ответственные, выбор колонок, выгрузка в XLSX,
 * XLS, PDF и JSON. «Статистика обучения» - рейтинг ИТ-программ по заявкам
 * и обучающимся из LMS и с сайта. «Заявки» - список заявок с сайта
 * (с персональными данными - только руководителю и администратору).
 */
import { useSearchParams } from "react-router-dom";
import { useSession } from "../../auth/session";
import { PageHeader, Tabs } from "../../components/ui";
import { usePageTitle } from "../../lib/usePageTitle";
import { ApplicationsList } from "./ApplicationsList";
import { InteractionReport } from "./InteractionReport";
import { LearningStatistics } from "./LearningStatistics";

export default function ReportsPage() {
  const [params, setParams] = useSearchParams();
  const { can } = useSession();
  const tab = params.get("tab") || "interaction";
  usePageTitle("Отчёты и статистика");
  return (
    <div className="page">
      <PageHeader
        title="Отчёты и статистика"
        description="Отчёты строятся по данным, которые вам доступны. Фильтры и выбранные колонки запоминаются."
      />
      <Tabs
        value={tab}
        onChange={(key) => setParams({ tab: key }, { replace: true })}
        items={[
          { key: "interaction", label: "Взаимодействие с вузами" },
          { key: "learning", label: "Статистика обучения" },
          { key: "applications", label: "Заявки с сайта", hidden: !can("view_personal_data") },
        ]}
      />
      {tab === "interaction" && <InteractionReport />}
      {tab === "learning" && <LearningStatistics />}
      {tab === "applications" && can("view_personal_data") && <ApplicationsList />}
    </div>
  );
}
