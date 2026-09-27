/**
 * Снимки экранов для встроенных руководств (public/help/*.png).
 *
 * Нужен стенд с демоданными в режиме разработки (вход без Keycloak) и,
 * для снимка страницы входа, стенд с Keycloak:
 *
 *   BASE=http://localhost:5173 KEYCLOAK_BASE=http://localhost:8088 \
 *     node scripts/help-screenshots.cjs
 *
 * ONLY_LOGIN=1 - только снимки входа (login.png, keycloak-login.png).
 *
 * Playwright в зависимости проекта не входит: npx playwright install
 * chromium или глобальная установка (PLAYWRIGHT_PATH - путь к пакету).
 */
const path = require("node:path");
const { chromium } = require(process.env.PLAYWRIGHT_PATH || "playwright");

const BASE = process.env.BASE || "http://localhost:5173";
const KEYCLOAK_BASE = process.env.KEYCLOAK_BASE || "";
const OUT = path.resolve(__dirname, "../public/help");
const DESKTOP = { viewport: { width: 1440, height: 900 }, locale: "ru-RU" };
const MOBILE = { viewport: { width: 390, height: 844 }, deviceScaleFactor: 2, isMobile: true, hasTouch: true, locale: "ru-RU" };

// Роли не наследуются: у каждого ровно те, что в демоданных. Орлова -
// руководитель, который и сам ведёт вузы.
const ACCOUNTS = {
  manager: { username: "petrov", roles: "manager" },
  head: { username: "orlova", roles: "manager,head" },
  admin: { username: "admin", roles: "admin" },
};

// Взаимодействие Петрова в середине процесса: внедрение продукта, две
// программы, продукты с лицензиями.
const SHOWCASE = "Подготовка инженеров по тестированию";

async function session(browser, role, options = DESKTOP) {
  const context = await browser.newContext(options);
  const page = await context.newPage();
  page.on("pageerror", (error) => console.warn(`[${role}] ${error.message}`));
  await page.goto(BASE + "/");
  await page.waitForSelector(".account");
  await page.fill("input[type=search]", ACCOUNTS[role].username);
  await page.click(".account");
  await page.waitForSelector(".shell");
  return page;
}

function headers(role) {
  const account = ACCOUNTS[role];
  return { "X-Dev-User": account.username, "X-Dev-Roles": account.roles };
}

async function interactionId(page, role, title) {
  const response = await page.request.get(`${BASE}/api/v1/interactions?search=${encodeURIComponent(title)}`, {
    headers: headers(role),
  });
  const body = await response.json();
  if (!body.items || !body.items.length) throw new Error(`взаимодействие «${title}» не найдено`);
  return body.items[0].id;
}

async function open(page, url) {
  await page.goto(BASE + url);
  await page.waitForSelector(".page");
  await page.waitForLoadState("networkidle");
  await page.waitForTimeout(500);
}

async function shot(page, name) {
  await page.mouse.move(0, 0);
  await page.screenshot({ path: path.join(OUT, name) });
  console.log(`  ${name}`);
}

(async () => {
  const browser = await chromium.launch();

  if (KEYCLOAK_BASE) {
    // Стенд с Keycloak бывает с самоподписанным сертификатом (preprod, проверка
    // боевой конфигурации на своей машине).
    const context = await browser.newContext({ ...DESKTOP, ignoreHTTPSErrors: true });
    const page = await context.newPage();
    await page.goto(KEYCLOAK_BASE + "/");
    await page.waitForSelector(".login__panel");
    await shot(page, "login.png");
    await page.getByRole("button", { name: /Войти/ }).click();
    await page.waitForSelector("#kc-form-login");
    await page.waitForTimeout(500);
    await shot(page, "keycloak-login.png");
    await context.close();
  }
  if (process.env.ONLY_LOGIN) {
    await browser.close();
    return;
  }

  // --- Менеджер ---------------------------------------------------------------
  const manager = await session(browser, "manager");
  const showcase = await interactionId(manager, "manager", SHOWCASE);
  await open(manager, "/");
  await shot(manager, "dashboard-manager.png");
  await open(manager, "/interactions");
  await shot(manager, "interactions.png");
  await manager.getByRole("button", { name: "Новое взаимодействие" }).first().click();
  await manager.waitForSelector(".modal");
  await manager.waitForTimeout(600); // окно появляется с анимацией
  await shot(manager, "interaction-new.png");
  await open(manager, `/interactions/${showcase}?tab=process`);
  await shot(manager, "interaction-process.png");
  await manager.locator(".stage-panel").getByRole("button", { name: "Продукт развёрнут" }).click();
  await manager.waitForSelector(".modal");
  await manager.locator(".modal textarea").fill("Развернули песочницу для автотестов, доступы выданы кафедре; акт во вложении");
  await manager.waitForTimeout(600);
  await shot(manager, "transition.png");
  await open(manager, `/interactions/${showcase}?tab=composition`);
  await manager.evaluate(() => window.scrollTo(0, 560));
  await shot(manager, "composition.png");

  // --- Руководитель -------------------------------------------------------------
  const head = await session(browser, "head");
  await open(head, "/");
  await shot(head, "dashboard.png");
  await open(head, "/universities");
  await shot(head, "universities.png");
  await open(head, "/reports");
  await head.evaluate(() => window.scrollTo(0, 250));
  await shot(head, "reports.png");
  await open(head, "/reports?tab=learning");
  await head.evaluate(() => window.scrollTo(0, 250));
  await shot(head, "statistics.png");

  // --- Администратор -----------------------------------------------------------
  const admin = await session(browser, "admin");
  await open(admin, "/admin/users");
  await admin.getByRole("button", { name: "Петров Пётр Алексеевич" }).click();
  await admin.waitForSelector(".drawer");
  await admin.waitForTimeout(700);
  await shot(admin, "admin-users.png");
  await open(admin, "/admin/imports");
  await admin.locator(".card", { hasText: "Справочник вузов" }).getByRole("button", { name: "Выбрать" }).click();
  await admin.setInputFiles("input[type=file]", path.resolve(__dirname, "../../testdata/import/05-universities.xlsx"));
  await admin.getByRole("button", { name: "Прочитать файл" }).click();
  await admin.waitForSelector(".mapping-table");
  await shot(admin, "admin-imports.png");
  await open(admin, "/admin/workflows");
  await shot(admin, "admin-workflows.png");
  await open(admin, "/integrations");
  await shot(admin, "integrations.png");
  await open(admin, "/integrations?tab=mappings");
  await admin.evaluate(() => window.scrollTo(0, 420));
  await shot(admin, "mappings.png");
  // Журнал пуст на свежих демоданных: руководитель снимает менеджера по
  // умолчанию у вуза и назначает снова - оба изменения попадут в журнал.
  const universities = await (await admin.request.get(`${BASE}/api/v1/universities?limit=1`, { headers: headers("head") })).json();
  const university = universities.items[0];
  if (university) {
    const url = `${BASE}/api/v1/universities/${university.id}`;
    await admin.request.patch(url, { headers: headers("head"), data: { manager_id: null } });
    await admin.request.patch(url, { headers: headers("head"), data: { manager_id: university.manager_id } });
  }
  await open(admin, "/admin/audit");
  await admin.locator(".list-item button").first().click();
  await admin.waitForTimeout(300);
  await shot(admin, "admin-audit.png");

  // --- Телефон -------------------------------------------------------------------
  const phone = await session(browser, "manager", MOBILE);
  await open(phone, `/interactions/${showcase}?tab=process`);
  await phone.evaluate(() => window.scrollTo(0, 1450));
  await shot(phone, "mobile.png");

  await browser.close();
})().catch((error) => {
  console.error(error);
  process.exit(1);
});
