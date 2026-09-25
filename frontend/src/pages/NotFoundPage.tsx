import { Compass } from "lucide-react";
import { useNavigate } from "react-router-dom";
import { Button, EmptyState } from "../components/ui";
import { usePageTitle } from "../lib/usePageTitle";

export default function NotFoundPage() {
  const navigate = useNavigate();
  usePageTitle("Страница не найдена");
  return (
    <div className="page">
      <EmptyState
        icon={Compass}
        title="Страница не найдена"
        action={
          <Button variant="secondary" onClick={() => navigate("/")}>
            На главную
          </Button>
        }
      >
        Возможно, ссылка устарела или запись удалили. Воспользуйтесь меню или поиском вверху страницы.
      </EmptyState>
    </div>
  );
}
