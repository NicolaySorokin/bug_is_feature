/**
 * Снимки экранов для встроенных руководств (public/help/*.png).
 *
 * Нужен стенд с демоданными в режиме разработки (вход без Keycloak) и,
 * для снимка страницы входа, стенд с Keycloak:
 *
 *   BASE=http://localhost:5173 KEYCLOAK_BASE=http://localhost:8088 \
 *     node scripts/help-screenshots.cjs
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

const ACCOUNTS = {
  manager: { username: "petrov", roles: "manager" },
  head: { username: "fedorov", roles: "head,manager" },
  admin: { username: "admin", roles: "admin,head,manager" },
};

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

async function contractId(page, role, number) {
  const account = ACCOUNTS[role];
  const response = await page.request.get(`${BASE}/api/v1/contracts?search=${encodeURIComponent(number)}`, {
    headers: { "X-Dev-User": account.username, "X-Dev-Roles": account.roles },
  });
  const body = await response.json();
  if (!body.items.length) throw new Error(`договор ${number} не найден`);
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
    const context = await browser.newContext(DESKTOP);
    const page = await context.newPage();
    await page.goto(KEYCLOAK_BASE + "/");
    await page.waitForSelector(".login__panel");
    await shot(page, "login.png");
    await context.close();
  }

  const manager = await session(browser, "manager");
  const processContract = await contractId(manager, "manager", "ДГ-2026-132");
  const composition = await contractId(manager, "manager", "ДГ-2026-047");
  await open(manager, "/contracts");
  await shot(manager, "contracts.png");
  await open(manager, `/contracts/${processContract}?tab=process`);
  await manager.evaluate(() => window.scrollTo(0, 470));
  await shot(manager, "contract-process.png");
  await manager.locator(".stage-panel").getByRole("button", { name: "Преподаватели обучены" }).click();
  await manager.waitForSelector(".modal");
  await manager.locator(".modal textarea").fill("Провели обучение для 12 преподавателей кафедры, протокол во вложении");
  await manager.waitForTimeout(600); // окно появляется с анимацией
  await shot(manager, "transition.png");
  await open(manager, `/contracts/${composition}?tab=composition`);
  await manager.evaluate(() => window.scrollTo(0, 520));
  await shot(manager, "composition.png");

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
  await open(head, "/integrations");
  await shot(head, "integrations.png");

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
  // Журнал пуст на свежих демоданных: руководитель снимает ответственного
  // за вуз и назначает снова - оба изменения попадут в журнал.
  const headers = { "X-Dev-User": ACCOUNTS.head.username, "X-Dev-Roles": ACCOUNTS.head.roles };
  const universities = await (await admin.request.get(`${BASE}/api/v1/universities?limit=1`, { headers })).json();
  const university = universities.items[0];
  if (university) {
    const url = `${BASE}/api/v1/universities/${university.id}`;
    await admin.request.patch(url, { headers, data: { manager_id: null } });
    await admin.request.patch(url, { headers, data: { manager_id: university.manager_id } });
  }
  await open(admin, "/admin/audit");
  await admin.locator(".list-item button").first().click();
  await admin.waitForTimeout(300);
  await shot(admin, "admin-audit.png");

  const phone = await session(browser, "manager", MOBILE);
  await open(phone, `/contracts/${processContract}?tab=process`);
  await phone.evaluate(() => window.scrollTo(0, 900));
  await shot(phone, "mobile.png");

  await browser.close();
})().catch((error) => {
  console.error(error);
  process.exit(1);
});
