/** Руководство по установке и эксплуатации: состав, обновление, резервные копии. */
import type { Section } from "./HelpPage";
import { Note, Shot } from "./HelpPage";

export function OperationsGuide(): Section[] {
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
                  Отдаёт клиентскую часть (React, собрана в образ), проксирует <code>/api</code>, <code>/docs</code> к API и реалм{" "}
                  <code>/realms/edu-crm</code> к Keycloak; TLS, заголовки безопасности, сжатие.
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
                  PostgreSQL 16: база системы и база Keycloak (<code>keycloak</code>), данные - том <code>pgdata</code>.
                </td>
              </tr>
              <tr>
                <td>
                  <code>keycloak</code> (образ <code>edu-crm-keycloak</code>)
                </td>
                <td>
                  Keycloak 26 в боевом режиме: вход по OpenID Connect (Authorization Code + PKCE), роли, страница входа в стиле
                  Ростелекома. Реалм <code>edu-crm</code> описан в <code>deploy/keycloak/realm-export.json</code>.
                </td>
              </tr>
            </tbody>
          </table>
          <p>
            Описание API -{" "}
            <a href="/docs" target="_blank" rel="noreferrer">
              Swagger UI
            </a>{" "}
            (<code>/docs</code>) и ReDoc (<code>/redoc</code>), схема - <code>/api/v1/openapi.json</code>. Модель архитектуры в
            нотации ArchiMate (Archi) - <code>docs/architecture/edu-crm.archimate</code> в репозитории.
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
                <td>
                  Администратор консоли Keycloak (заводится при первом запуске). На новом реалме этим же паролем первый раз входит{" "}
                  <code>admin</code> системы, поэтому пароль должен проходить политику паролей реалма
                </td>
              </tr>
              <tr>
                <td>
                  <code>KEYCLOAK_USER_PASSWORDS</code>
                </td>
                <td>
                  Необязательно: начальные пароли пользователей, <code>логин:пароль</code> через запятую. Ставятся только тем, у
                  кого пароля ещё нет (сразу после создания реалма); дальше паролями управляют на сайте. В репозитории паролей нет
                </td>
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
                <td>
                  API LMS и сайта. Пусто - демонстрационный режим: пример ответа в формате источника (ответ настоящего API можно
                  загрузить файлом JSON в разделе «LMS и сайт»)
                </td>
              </tr>
              <tr>
                <td>
                  <code>INTEGRATION_SYNC_INTERVAL_HOURS</code>
                </td>
                <td>
                  Обмен по расписанию, раз в N часов; 0 - только вручную. Это значение по умолчанию: администратор меняет его в
                  «Настройках» без перезапуска
                </td>
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
              Роли реалма <code>manager</code>, <code>head</code>, <code>admin</code>. Роли не наследуются: руководителю, который
              сам ведёт вузы, назначают и <code>manager</code>; роль <code>admin</code> даёт только технические функции. Роль{" "}
              <code>admin</code> включает права <code>realm-management</code> на пользователей: администратор CRM управляет ролями
              из интерфейса системы.
            </li>
            <li>
              Политика паролей: не короче 12 знаков, строчные и заглавные буквы, цифры, не совпадает с логином. Защита от подбора:
              10 неудачных попыток - временная блокировка; журнал событий входа хранится 90 дней.
            </li>
            <li>
              Вход только через страницу Keycloak: выдача токена по паролю в обход неё выключена. Снаружи открыт только реалм{" "}
              <code>edu-crm</code>, консоль администратора Keycloak из интернета недоступна.
            </li>
            <li>
              Данные Keycloak хранятся в PostgreSQL и переживают пересоздание контейнера и сброс данных системы. Настройку из
              выгрузки реалма (параметры, роли, клиенты) переносит в работающий Keycloak задача <code>keycloak-setup</code> - при
              каждом деплое или вручную: <code>release.sh keycloak-setup</code>.
            </li>
          </ul>
          <Note>
            Переход на роли без наследования <code>keycloak-setup</code> выполняет сам и один раз (атрибут реалма{" "}
            <code>eduCrmRoleModel</code>): учётке из выгрузки, у которой остались роли старой иерархии (администратору добавляли{" "}
            <code>manager</code> и <code>head</code>, руководителю - <code>manager</code>), ставятся роли новой выгрузки. Роли,
            изменённые на сайте, и заведённые там учётки не трогаются. Команды руководителей задаются полем «Руководитель» у
            сотрудника.
          </Note>
          <Note>
            Учётными записями управляют на сайте: «Пользователи и права» - сотрудники, роли, отключение, пароли. Обновления стенда
            их не трогают. Из выгрузки учётные записи берутся только при создании реалма на пустой базе Keycloak; начальные пароли
            - из <code>KEYCLOAK_USER_PASSWORDS</code>, а без неё первый вход <code>admin</code> - паролем консоли Keycloak
            (временным), остальным пароли задаёт он.
          </Note>
        </>
      ),
    },
    {
      id: "integrations",
      title: "Обмен с LMS и сайтом",
      body: (
        <>
          <p>Промышленный режим обмена:</p>
          <ul>
            <li>
              <b>Транспорт</b> - API опрашивает источники по HTTPS (GET, токен в заголовке <code>Authorization</code>), адреса и
              токены - <code>LMS_BASE_URL</code>, <code>LMS_TOKEN</code>, <code>SITE_BASE_URL</code>, <code>SITE_TOKEN</code>.
              Тайм-аут запроса - <code>INTEGRATION_TIMEOUT_SECONDS</code>.
            </li>
            <li>
              <b>Расписание</b> - раз в N часов по настройке «Обмен с LMS и сайтом по расписанию» (0 - вручную). Проверку раз в
              пять минут делает один из рабочих процессов API - тот, что получил рекомендательную блокировку PostgreSQL, поэтому
              обмен не запускается дважды. Ручной обмен откладывает плановый.
            </li>
            <li>
              <b>Идемпотентность</b> - таблица <code>external_links</code> помнит, какой записи источника (в пределах источника и
              типа) соответствует запись системы: повторный обмен обновляет, а не дублирует.
            </li>
            <li>
              <b>Ошибки</b> - сбой сети, тайм-аут и ответ 5xx повторяются до трёх раз с паузой, 4xx - сразу ошибка запуска. Ошибка
              отдельной записи не останавливает обмен: запуск получает статус «Частично», запись - строку в журнале.
            </li>
            <li>
              <b>Мониторинг</b> - журнал запусков в «LMS и сайт» (статус, счётчики, число попыток, ошибки по записям) и оповещение
              «Ошибка синхронизации» у администратора; подробности сбоя - в журнале контейнера API.
            </li>
          </ul>
          <Note>
            Курсор выгрузки (только изменения) и правила удаления записей определяются контрактом API источника. Пока источник
            отдаёт полный снимок, записи, которых в снимке больше нет, в системе не удаляются.
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
            Выложить определённый коммит: Actions → «Деплой» → Run workflow, поле «Коммит, тег или ветка». Подробно - в README
            репозитория, раздел «Боевой стенд».
          </p>
        </>
      ),
    },
    {
      id: "backup",
      title: "Резервное копирование",
      body: (
        <>
          <p>
            Каждую ночь таймер <code>edu-crm-backup.timer</code> снимает копию базы системы, базы Keycloak и файлов вложений в{" "}
            <code>/opt/edu-crm/backups</code>; копии хранятся 14 дней. В копиях персональные данные: каталог доступен только
            пользователю деплоя, копии стоит регулярно забирать за пределы сервера.
          </p>
          <pre>
            <code>{`cd /opt/edu-crm/current
bash cicd/prod/server/release.sh backup     # копия сейчас
systemctl list-timers edu-crm-backup.timer   # следующая по расписанию`}</code>
          </pre>
          <p>Восстановление (ДАТА - из имени файла копии):</p>
          <pre>
            <code>{`R="bash cicd/prod/server/release.sh"
$R compose stop api keycloak nginx
$R compose exec -T db sh -c 'pg_restore -U "$POSTGRES_USER" -d "$POSTGRES_DB" --clean --if-exists --no-owner' \\
  < ../../backups/ДАТА-edu_crm.dump
$R compose exec -T db sh -c 'pg_restore -U "$POSTGRES_USER" -d keycloak --clean --if-exists --no-owner' \\
  < ../../backups/ДАТА-keycloak.dump
$R compose up -d --wait --no-build
$R compose exec -T api sh -c 'rm -rf /app/storage/* && tar xzf - -C /app/storage' \\
  < ../../backups/ДАТА-storage.tgz`}</code>
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
              <code> make seed-load N=3000</code> добавляет взаимодействия для проверки на объёме.
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
            <li>
              Разграничение доступа на сервере: роль, отдельные права и область данных проверяются в каждом запросе; временное
              расширение области - со сроком, основанием и записью в журнале.
            </li>
            <li>Журнал изменений данных и прав с маскированием персональных данных.</li>
            <li>Минимизация: из анкет LMS не сохраняются паспорт, СНИЛС, адрес, сведения о дипломе.</li>
            <li>
              Проверка типа и размера загружаемых файлов; заявки с персональными данными видны только по отдельному праву
              «Персональные данные студентов».
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
              <td>Руководитель после обновления не может завести взаимодействие на себя</td>
              <td>Роли не наследуются: добавьте ему роль «Менеджер» в «Пользователи и права».</td>
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
