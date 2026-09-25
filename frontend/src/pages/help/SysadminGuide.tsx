/** Руководство системного администратора: состав, установка, обновление, резервные копии. */
import type { Section } from "./HelpPage";
import { Note, Shot } from "./HelpPage";

export function SysadminGuide(): Section[] {
  return [
    {
      id: "architecture",
      title: "Состав системы",
      body: (
        <>
          <p>Система - четыре контейнера Docker. Наружу открыт только Nginx (порты 80 и 443).</p>
          <Shot src="architecture.svg" caption="Контейнеры и потоки данных" />
          <table>
            <thead>
              <tr>
                <th>Контейнер</th>
                <th>Что делает</th>
              </tr>
            </thead>
            <tbody>
              <tr>
                <td>
                  <code>nginx</code> (образ <code>edu-crm-web</code>)
                </td>
                <td>
                  Отдаёт клиентскую часть (React, собрана в образ), проксирует <code>/api</code>, <code>/docs</code> к API и{" "}
                  <code>/realms</code> к Keycloak; TLS, заголовки безопасности, сжатие.
                </td>
              </tr>
              <tr>
                <td>
                  <code>api</code> (образ <code>edu-crm-api</code>)
                </td>
                <td>
                  REST API на FastAPI (Python 3.12), несколько рабочих процессов (<code>WEB_CONCURRENCY</code>). При запуске
                  применяет миграции Alembic. Файлы вложений - том <code>api_storage</code>.
                </td>
              </tr>
              <tr>
                <td>
                  <code>db</code>
                </td>
                <td>
                  PostgreSQL 16, данные - том <code>pgdata</code>.
                </td>
              </tr>
              <tr>
                <td>
                  <code>keycloak</code>
                </td>
                <td>
                  Keycloak 26: вход по OpenID Connect (Authorization Code + PKCE), роли. Реалм <code>edu-crm</code> импортируется
                  из <code>deploy/keycloak/realm-export.json</code>.
                </td>
              </tr>
            </tbody>
          </table>
          <p>
            Описание API - Swagger UI (<code>/docs</code>) и ReDoc (<code>/redoc</code>), схема -{" "}
            <code>/api/v1/openapi.json</code>. Модель архитектуры в нотации ArchiMate (Archi) -{" "}
            <code>docs/architecture/edu-crm.archimate</code> в репозитории.
          </p>
        </>
      ),
    },
    {
      id: "install",
      title: "Установка",
      body: (
        <>
          <p>
            Сервер: Linux x86-64, 2 vCPU, 4 ГБ памяти (под нагрузкой из ТЗ занято около 1,5 ГБ), 20 ГБ диска; Docker 24+ с Compose
            v2, make.
          </p>
          <pre>
            <code>{`git clone <репозиторий> edu-crm && cd edu-crm
cp cicd/prod/.env.example cicd/prod/.env   # задайте пароли и адреса
make build ENV=prod
make up ENV=prod                            # контейнеры, миграции, демоданные`}</code>
          </pre>
          <p>
            Среды: <code>dev</code> - разработка (http://localhost:3000, вход без Keycloak), <code>preprod</code> - как бой, но по
            HTTP, <code>prod</code> - HTTPS с сертификатом Let&apos;s Encrypt. Отличия сред - в <code>cicd/&lt;среда&gt;/</code>.
          </p>
          <h3>Основные переменные (cicd/&lt;среда&gt;/.env)</h3>
          <table>
            <thead>
              <tr>
                <th>Переменная</th>
                <th>Назначение</th>
              </tr>
            </thead>
            <tbody>
              <tr>
                <td>
                  <code>POSTGRES_USER</code>, <code>POSTGRES_PASSWORD</code>, <code>POSTGRES_DB</code>
                </td>
                <td>Доступ к базе. Пароль - длинный случайный</td>
              </tr>
              <tr>
                <td>
                  <code>AUTH_BACKEND</code>
                </td>
                <td>
                  <code>keycloak</code> в preprod и prod; <code>dev</code> - вход без пароля, только для разработки
                </td>
              </tr>
              <tr>
                <td>
                  <code>KEYCLOAK_BASE_URL</code>
                </td>
                <td>Адрес Keycloak для браузера, он же издатель токенов (https://домен-стенда)</td>
              </tr>
              <tr>
                <td>
                  <code>KEYCLOAK_ADMIN</code>, <code>KEYCLOAK_ADMIN_PASSWORD</code>
                </td>
                <td>Администратор консоли Keycloak</td>
              </tr>
              <tr>
                <td>
                  <code>WEB_CONCURRENCY</code>
                </td>
                <td>Рабочие процессы API (4 - на 50 пользователей и 10 отчётов одновременно)</td>
              </tr>
              <tr>
                <td>
                  <code>LMS_BASE_URL</code>, <code>LMS_TOKEN</code>, <code>SITE_BASE_URL</code>, <code>SITE_TOKEN</code>
                </td>
                <td>API LMS и сайта. Пусто - тестовые ответы (файл JSON можно загрузить в разделе «LMS и сайт»)</td>
              </tr>
              <tr>
                <td>
                  <code>CORS_ORIGINS</code>
                </td>
                <td>Адреса, с которых разрешены запросы к API из браузера</td>
              </tr>
            </tbody>
          </table>
        </>
      ),
    },
    {
      id: "keycloak",
      title: "Keycloak и учётные записи",
      body: (
        <>
          <ul>
            <li>
              Реалм <code>edu-crm</code>; клиенты <code>edu-crm-web</code> (публичный, PKCE S256 - вход из браузера) и{" "}
              <code>edu-crm-api</code> (аудитория токенов API).
            </li>
            <li>
              Роли реалма <code>manager</code>, <code>head</code>, <code>admin</code>. Роль <code>admin</code> включает права{" "}
              <code>realm-management</code> на пользователей: администратор CRM управляет ролями из интерфейса системы.
            </li>
            <li>Защита от подбора пароля: 10 неудачных попыток - временная блокировка; журнал событий входа хранится 90 дней.</li>
            <li>Консоль Keycloak: https://домен-стенда/admin/ (логин и пароль из KEYCLOAK_ADMIN*).</li>
          </ul>
          <Note warn>
            В демонстрационном реалме у пользователей пароль совпадает с логином. Перед эксплуатацией смените пароли или удалите
            демо-пользователей, задайте политику паролей реалма. Реалм импортируется при создании контейнера Keycloak: при
            изменении файла выгрузки контейнер пересоздаётся, и пользователи, заведённые вручную, пропадают - для постоянной
            эксплуатации подключите Keycloak к PostgreSQL (KC_DB=postgres).
          </Note>
        </>
      ),
    },
    {
      id: "deploy",
      title: "Обновление (CI/CD) и откат",
      body: (
        <>
          <ol>
            <li>
              Пуш в <code>main</code> запускает CI (GitHub Actions): тесты и стиль API, миграции и демоданные,
              типы/стиль/тесты/сборка клиентской части, сборка образов.
            </li>
            <li>
              После зелёного CI workflow «Деплой» собирает образы <code>edu-crm-api:&lt;коммит&gt;</code> и{" "}
              <code>edu-crm-web:&lt;коммит&gt;</code>, привозит их на сервер по SSH и активирует релиз: миграции, проверка
              здоровья API, перечитывание Nginx.
            </li>
            <li>
              Не поднялся - прежний релиз возвращается автоматически. После выкладки проверяются HTTPS, клиентская часть, API,
              Keycloak.
            </li>
          </ol>
          <p>Вручную на сервере (каталог /opt/edu-crm):</p>
          <pre>
            <code>{`bash current/cicd/prod/server/release.sh list            # релизы, * - текущий
bash current/cicd/prod/server/release.sh rollback        # откат на предыдущий
bash current/cicd/prod/server/release.sh compose ps      # состояние контейнеров
bash current/cicd/prod/server/release.sh compose logs -f api nginx`}</code>
          </pre>
          <p>
            Выложить определённый коммит: Actions → «Деплой» → Run workflow, поле «Коммит, тег или ветка». Подробно -{" "}
            <code>cicd/README.md</code>.
          </p>
        </>
      ),
    },
    {
      id: "backup",
      title: "Резервное копирование",
      body: (
        <>
          <p>Копировать нужно базу и том с файлами вложений. Ежедневно, с хранением копий вне сервера:</p>
          <pre>
            <code>{`cd /opt/edu-crm
# база
bash current/cicd/prod/server/release.sh compose exec -T db \\
  pg_dump -U edu_crm -Fc edu_crm > backup/edu_crm-$(date +%F).dump
# файлы вложений
docker run --rm -v edu-crm_api_storage:/data -v $PWD/backup:/backup alpine \\
  tar czf /backup/storage-$(date +%F).tgz -C /data .`}</code>
          </pre>
          <p>Восстановление:</p>
          <pre>
            <code>{`bash current/cicd/prod/server/release.sh compose exec -T db \\
  pg_restore -U edu_crm -d edu_crm --clean --if-exists < backup/edu_crm-ДАТА.dump
docker run --rm -v edu-crm_api_storage:/data -v $PWD/backup:/backup alpine \\
  tar xzf /backup/storage-ДАТА.tgz -C /data`}</code>
          </pre>
        </>
      ),
    },
    {
      id: "monitoring",
      title: "Контроль работы",
      body: (
        <>
          <ul>
            <li>
              Здоровье: <code>GET /api/v1/health</code> - <code>{`{"status":"ok"}`}</code>; тот же запрос - healthcheck контейнера
              API.
            </li>
            <li>
              Журналы: <code>release.sh compose logs api</code>, <code>nginx</code>, <code>keycloak</code>. Ошибки API - в едином
              формате с кодом (<code>code</code>), по коду пользователь сообщает о проблеме.
            </li>
            <li>Действия пользователей - «Журнал изменений» в интерфейсе (роль администратора).</li>
            <li>
              Нагрузка: <code>make loadtest</code> - 50 одновременных пользователей и 10 параллельных отчётов (требования ТЗ);
              <code> make seed-load N=3000</code> добавляет договоры для проверки на объёме.
            </li>
          </ul>
        </>
      ),
    },
    {
      id: "security",
      title: "Защита информации",
      body: (
        <>
          <p>Меры, заложенные в систему (152-ФЗ, приказ ФСТЭК России № 117):</p>
          <ul>
            <li>
              Единая точка входа; база, API и Keycloak наружу не публикуются. HTTPS с HSTS, CSP, запрет встраивания во фрейм.
            </li>
            <li>Аутентификация - Keycloak (PKCE), токены живут 30 минут; блокировка при подборе пароля, журнал событий входа.</li>
            <li>Разграничение доступа на сервере: роль и область данных проверяются в каждом запросе.</li>
            <li>Журнал изменений данных и прав с маскированием персональных данных.</li>
            <li>Минимизация: из анкет LMS не сохраняются паспорт, СНИЛС, адрес, сведения о дипломе.</li>
            <li>
              Проверка типа и размера загружаемых файлов; заявки с персональными данными видны только руководителю и
              администратору.
            </li>
          </ul>
          <Note>
            Организационные меры (модель угроз, уровень защищённости ИСПДн, назначение ответственного, сертифицированные средства
            защиты при необходимости) определяются оператором персональных данных при вводе в эксплуатацию.
          </Note>
        </>
      ),
    },
    {
      id: "troubleshooting",
      title: "Частые проблемы",
      body: (
        <table>
          <thead>
            <tr>
              <th>Признак</th>
              <th>Причина и решение</th>
            </tr>
          </thead>
          <tbody>
            <tr>
              <td>После входа сразу снова страница входа</td>
              <td>
                <code>KEYCLOAK_BASE_URL</code> не совпадает с адресом стенда - токен не проходит проверку издателя. Исправьте и
                перезапустите API.
              </td>
            </tr>
            <tr>
              <td>«Сервер недоступен» на странице</td>
              <td>
                API не запущен или не прошёл миграции: <code>release.sh compose logs api</code>.
              </td>
            </tr>
            <tr>
              <td>Отчёт PDF без русских букв</td>
              <td>В образе API нет шрифта DejaVu - соберите образ из Dockerfile репозитория.</td>
            </tr>
            <tr>
              <td>Синхронизация с LMS или сайтом с ошибкой</td>
              <td>Текст ошибки - в «LMS и сайт» → журнал обмена; проверьте адрес и токен источника.</td>
            </tr>
            <tr>
              <td>Не хватает памяти</td>
              <td>
                Уменьшите <code>WEB_CONCURRENCY</code> до 2 в секрете <code>PROD_ENV</code> и выложите стенд заново.
              </td>
            </tr>
          </tbody>
        </table>
      ),
    },
  ];
}
