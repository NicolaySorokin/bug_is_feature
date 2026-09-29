/**
 * Встроенные руководства по ролям со снимками экранов. Снимки лежат в public/help, их пересобирает
 * scripts/help-screenshots.cjs.
 */
import { BookOpen, Info, ShieldCheck, TriangleAlert, Users, Wrench } from "lucide-react";
import { useEffect, useState, type ReactNode } from "react";
import { useNavigate, useParams } from "react-router-dom";
import { useSession } from "../../auth/session";
import { PageHeader, Tabs } from "../../components/ui";
import { usePageTitle } from "../../lib/usePageTitle";
import { AdminGuide } from "./AdminGuide";
import { HeadGuide } from "./HeadGuide";
import { ManagerGuide } from "./ManagerGuide";
import { OperationsGuide } from "./OperationsGuide";

export interface Section {
  id: string;
  title: string;
  body: ReactNode;
}

export function Shot({ src, caption, className }: { src: string; caption: string; className?: string }) {
  return (
    <figure className={className}>
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
      {/* Оглавление само оформлено карточкой, чтобы не было двойного отступа. */}
      <nav aria-label="Оглавление" className="card help__toc">
        {sections.map((section) => (
          <a key={section.id} href={`#${section.id}`} className={active === section.id ? "active" : undefined}>
            {section.title}
          </a>
        ))}
      </nav>
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

const GUIDES = {
  manager: ManagerGuide,
  head: HeadGuide,
  admin: AdminGuide,
  operations: OperationsGuide,
};

export default function HelpPage() {
  const { guide } = useParams();
  const navigate = useNavigate();
  const { can, roles } = useSession();
  usePageTitle("Руководства");

  const admin = can("manage_users");
  const guides = [
    { key: "manager", label: "Менеджеру", icon: BookOpen, hidden: false },
    { key: "head", label: "Руководителю", icon: Users, hidden: !(roles.includes("head") || admin) },
    { key: "admin", label: "Администратору", icon: ShieldCheck, hidden: !admin },
    { key: "operations", label: "Системному администратору", icon: Wrench, hidden: !admin },
  ] as const;
  // Без выбора открывается руководство своей роли. Старая ссылка /help/user ведёт к руководству менеджера.
  const own = roles.includes("head") ? "head" : roles.includes("manager") || !admin ? "manager" : "admin";
  const requested = guide === "user" ? "manager" : guide === "sysadmin" ? "operations" : guide;
  const current = guides.find((item) => item.key === requested && !item.hidden)?.key || own;
  const sections = GUIDES[current]();

  return (
    <div className="page">
      {/* Без подзаголовка: про доступ сказано в разделе «Роли и права», а ссылка на Swagger UI есть
в руководстве системного администратора по установке и эксплуатации. */}
      <PageHeader title="Руководства" />
      <Tabs
        value={current}
        onChange={(key) => navigate(`/help/${key}`)}
        label="Руководства"
        items={guides.map((item) => ({ key: item.key, label: item.label, icon: item.icon, hidden: item.hidden }))}
      />
      <Guide key={current} sections={sections} />
    </div>
  );
}
