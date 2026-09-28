/**
 * Собирает src/styles/rt-theme.css, тему Ростелекома для Atomaro.
 *
 * Пакет фирменной темы закрытый, поэтому берём стандартную тему Atomaro и в каждом токене заменяем
 * оттенок синего #0055FF тем же по номеру оттенком фиолетового #7700FF. Ступени светлоты те же,
 * поэтому контраст не меняется. После обновления @atomaro/ui-kit скрипт запускают заново:
 *
 *   node scripts/rt-theme.mjs
 */
import { readFileSync, writeFileSync } from "node:fs";
import { dirname, resolve } from "node:path";
import { fileURLToPath } from "node:url";

const root = resolve(dirname(fileURLToPath(import.meta.url)), "..");
const SOURCE = resolve(root, "node_modules/@atomaro/ui-kit/theme/default-light.css");
const TARGET = resolve(root, "src/styles/rt-theme.css");

/** Оттенки фиолетового по ступеням шкалы Atomaro, 500 базовый цвет. */
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
 * Тема Ростелекома для Atomaro: акцентный синий заменён фиолетовым #7700FF.
 * Файл собирает scripts/rt-theme.mjs, руками не править.
 */
`;

/** #37f в #3377ff, регистр букв не важен. */
function normalize(hex) {
  const value = hex.slice(1).toLowerCase();
  return "#" + (value.length === 3 ? [...value].map((char) => char + char).join("") : value);
}

const source = readFileSync(SOURCE, "utf8");
const block = source.match(/:root\s*{([^}]*)}/);
if (!block) throw new Error(`В ${SOURCE} не найден блок :root`);
const tokens = [...block[1].matchAll(/(--[\w-]+)\s*:\s*([^;]+);/g)].map(([, name, value]) => [name, value.trim()]);

// Синюю шкалу берём из самой темы, так замена не зависит от записи цвета (#37f или #3377ff).
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
