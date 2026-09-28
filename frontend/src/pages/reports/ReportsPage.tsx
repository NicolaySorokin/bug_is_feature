/**
 * Отчёты и статистика: отчёт по взаимодействиям, статистика обучения и заявки с сайта.
 * Каждая вкладка видна по своему праву.
 */
import { GraduationCap, Handshake, Inbox } from "lucide-react";
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
  usePageTitle("Отчёты и статистика");
  const items = [
    { key: "interaction", label: "Взаимодействие с вузами", icon: Handshake, hidden: !can("view_reports") },
    { key: "learning", label: "Статистика обучения", icon: GraduationCap, hidden: !can("view_statistics") },
    // Заявки относятся к статистике обучения, но с персональными данными, поэтому нужны оба права.
    {
      key: "applications",
      label: "Заявки с сайта",
      icon: Inbox,
      hidden: !(can("view_statistics") && can("view_personal_data")),
    },
  ];
  const visible = items.filter((item) => !item.hidden).map((item) => item.key);
  const requested = params.get("tab") || "";
  const tab = visible.includes(requested) ? requested : visible[0];
  return (
    <div className="page">
      <PageHeader title="Отчёты и статистика" />
      {visible.length > 1 && (
        <Tabs value={tab} onChange={(key) => setParams({ tab: key }, { replace: true })} label="Разделы отчётов" items={items} />
      )}
      {tab === "interaction" && <InteractionReport />}
      {tab === "learning" && <LearningStatistics />}
      {tab === "applications" && <ApplicationsList />}
    </div>
  );
}
