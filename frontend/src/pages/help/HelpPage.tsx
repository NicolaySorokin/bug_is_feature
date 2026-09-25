/**
 * Встроенные руководства (нефункциональное требование 4 ТЗ): пользователя,
 * администратора и системного администратора, со снимками экранов.
 *
 * Снимки лежат в public/help и пересобираются скриптом
 * frontend/scripts/help-screenshots.cjs по живому стенду.
 */
import { BookOpen, Info, ShieldCheck, TriangleAlert, Wrench } from "lucide-react";
import { useEffect, useState, type ReactNode } from "react";
import { Link, useNavigate, useParams } from "react-router-dom";
import { useSession } from "../../auth/session";
import { Card, PageHeader, Tabs } from "../../components/ui";
import { usePageTitle } from "../../lib/usePageTitle";
import { AdminGuide } from "./AdminGuide";
import { SysadminGuide } from "./SysadminGuide";
import { UserGuide } from "./UserGuide";

export interface Section {
  id: string;
  title: string;
  body: ReactNode;
}

export function Shot({ src, caption }: { src: string; caption: string }) {
  return (
    <figure>
      <img src={`/help/${src}`} alt={caption} loading="lazy" />
      <figcaption>{caption}</figcaption>
    </figure>
  );
}

export function Note({ children, warn }: { children: ReactNode; warn?: boolean }) {
  const Icon = warn ? TriangleAlert : Info;
  return (
    <div className={`note ${warn ? "note--warn" : ""}`}>
      <Icon size={18} />
      <div>{children}</div>
    </div>
  );
}

function Guide({ sections }: { sections: Section[] }) {
  const [active, setActive] = useState(sections[0]?.id);

  // Подсветка раздела оглавления, который сейчас на экране.
  useEffect(() => {
    const observer = new IntersectionObserver(
      (entries) => {
        const visible = entries
          .filter((entry) => entry.isIntersecting)
          .sort((a, b) => a.boundingClientRect.top - b.boundingClientRect.top);
        if (visible[0]) setActive(visible[0].target.id);
      },
      { rootMargin: "-80px 0px -60% 0px" },
    );
    sections.forEach((section) => {
      const element = document.getElementById(section.id);
      if (element) observer.observe(element);
    });
    return () => observer.disconnect();
  }, [sections]);

  return (
    <div className="help">
      <Card className="help__toc">
        <nav aria-label="Оглавление" className="help__toc">
          {sections.map((section) => (
            <a key={section.id} href={`#${section.id}`} className={active === section.id ? "active" : undefined}>
              {section.title}
            </a>
          ))}
        </nav>
      </Card>
      <article className="card article">
        {sections.map((section) => (
          <section key={section.id}>
            <h2 id={section.id}>{section.title}</h2>
            {section.body}
          </section>
        ))}
      </article>
    </div>
  );
}

export default function HelpPage() {
  const { guide = "user" } = useParams();
  const navigate = useNavigate();
  const { can } = useSession();
  usePageTitle("Руководства");

  const guides = [
    { key: "user", label: "Пользователю", icon: BookOpen, hidden: false },
    { key: "admin", label: "Администратору", icon: ShieldCheck, hidden: !can("manage_users") },
    { key: "sysadmin", label: "Системному администратору", icon: Wrench, hidden: !can("manage_users") },
  ];
  const current = guides.find((item) => item.key === guide && !item.hidden)?.key || "user";

  return (
    <div className="page">
      <PageHeader
        title="Руководства"
        description={
          <>
            Как работать в системе: вход, договоры и рабочий процесс, вузы, отчёты. Вопросы по доступу - к администратору системы
            {can("manage_users") ? "" : " (раздел «Пользователи и права» у него в меню)"}. Описание API - в{" "}
            <Link to="/docs" target="_blank" reloadDocument>
              Swagger UI
            </Link>
            .
          </>
        }
      />
      <Tabs
        value={current}
        onChange={(key) => navigate(`/help/${key}`)}
        items={guides.map((item) => ({ key: item.key, label: item.label, hidden: item.hidden }))}
      />
      {current === "user" && <Guide sections={UserGuide()} />}
      {current === "admin" && <Guide sections={AdminGuide()} />}
      {current === "sysadmin" && <Guide sections={SysadminGuide()} />}
    </div>
  );
}
