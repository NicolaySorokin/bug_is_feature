/**
 * Собирает src/styles/rt-theme.css - тему Ростелекома для Atomaro.
 *
 * Пакет темы @atomaro-rt/theme-rostelecom закрытый, поэтому тема
 * повторяется так: берутся токены стандартной темы Atomaro
 * (@atomaro/ui-kit/theme/default-light.css), и в каждом, где стоит оттенок
 * акцентного синего #0055FF, он заменяется тем же по номеру оттенком
 * фирменного фиолетового #7700FF. Шкала фиолетового задана ниже: оттенки
 * подобраны на тех же ступенях светлоты, что синие, поэтому контраст
 * текста и фона не меняется.
 *
 *   node scripts/rt-theme.mjs
 *
 * После обновления @atomaro/ui-kit запустите скрипт заново: новые
 * токены компонентов с акцентным цветом подхватятся сами.
 */
import { readFileSync, writeFileSync } from "node:fs";
import { dirname, resolve } from "node:path";
import { fileURLToPath } from "node:url";

const root = resolve(dirname(fileURLToPath(import.meta.url)), "..");
const SOURCE = resolve(root, "node_modules/@atomaro/ui-kit/theme/default-light.css");
const TARGET = resolve(root, "src/styles/rt-theme.css");

/** Оттенки фиолетового по ступеням шкалы Atomaro (500 - базовый цвет). */
const VIOLET = {
  990: "#12002b",
  950: "#250052",
  925: "#2e0066",
  900: "#38007a",
  800: "#44008f",
  700: "#5500b8",
  600: "#6600db",
  500: "#7700ff",
  400: "#8f33ff",
  300: "#a35cff",
  200: "#bb85ff",
  100: "#ddc2ff",
  50: "#f1e6ff",
  25: "#f8f2ff",
  10: "#fbf8ff",
};
const BLUE_RGB = "0, 85, 255";
const VIOLET_RGB = "119, 0, 255";

const HEADER = `/*
 * Тема Ростелекома для дизайн-системы Atomaro (@atomaro/ui-kit).
 *
 * Пакет темы @atomaro-rt/theme-rostelecom закрытый, поэтому здесь её
 * повторение: все токены Atomaro, в которых стоит акцентный синий,
 * получают фирменный фиолетовый Ростелекома #7700FF с той же шкалой
 * светлоты. Файл собирает scripts/rt-theme.mjs из default-light.css -
 * не править руками: см. frontend/README.md.
 */
`;

/** #37f -> #3377ff, регистр букв не важен. */
function normalize(hex) {
  const value = hex.slice(1).toLowerCase();
  return "#" + (value.length === 3 ? [...value].map((char) => char + char).join("") : value);
}

const source = readFileSync(SOURCE, "utf8");
const block = source.match(/:root\s*{([^}]*)}/);
if (!block) throw new Error(`В ${SOURCE} не найден блок :root`);
const tokens = [...block[1].matchAll(/(--[\w-]+)\s*:\s*([^;]+);/g)].map(([, name, value]) => [name, value.trim()]);

// Синяя шкала - из самой темы: так замена не зависит от записи цвета (#37f или #3377ff).
const blueToViolet = new Map();
for (const [step, violet] of Object.entries(VIOLET)) {
  const blue = tokens.find(([name]) => name === `--accent-${step}`);
  if (!blue) throw new Error(`В теме Atomaro нет токена --accent-${step}`);
  blueToViolet.set(normalize(blue[1]), violet);
}

const lines = [];
for (const [name, value] of tokens) {
  let replaced = false;
  const next = value
    .replace(/#[0-9a-f]{3}(?:[0-9a-f]{3})?\b/gi, (hex) => {
      const violet = blueToViolet.get(normalize(hex));
      if (!violet) return hex;
      replaced = true;
      return violet;
    })
    .replaceAll(`rgba(${BLUE_RGB},`, () => {
      replaced = true;
      return `rgba(${VIOLET_RGB},`;
    });
  if (replaced) lines.push(`  ${name}: ${next};`);
}

writeFileSync(TARGET, `${HEADER}:root {\n${lines.join("\n")}\n}\n`);
console.log(`${TARGET}: ${lines.length} токенов`);
