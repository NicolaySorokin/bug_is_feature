/**
 * Фирменные знаки Ростелекома.
 *
 * Логотип «Ростелеком ИТ Школа» (белый, для тёмного фона) - предоставленный
 * файл public/rostelecom-it-school.png. Знак - фирменный символ Ростелекома
 * в цветах дизайн-системы: он же значок сайта во вкладке (public/favicon.svg).
 */

/** Логотип «Ростелеком ИТ Школа» для тёмного фона. */
export function RtLogo({ height = 40, className = "" }: { height?: number; className?: string }) {
  return (
    <img
      className={`rt-logo ${className}`.trim()}
      src="/rostelecom-it-school.png"
      alt="Ростелеком ИТ Школа"
      height={height}
      width={Math.round((height * 617) / 160)}
    />
  );
}

/** Фирменный символ Ростелекома: фиолетовый флаг с оранжевым уголком. */
export function RtMark({ size = 32, className = "" }: { size?: number; className?: string }) {
  return (
    <svg className={`rt-mark ${className}`.trim()} width={size} height={size} viewBox="0 0 192 192" aria-hidden="true">
      <path
        fill="#7700FF"
        d="M39 57.4A30 30 0 0 1 47.8 36.2L82.4 1.6a3 3 0 0 1 4.2 0L151 66a3 3 0 0 1 0 4.3L79 142.5V192H57a18 18 0 0 1-18-18Z"
      />
      <path fill="#FF4F12" d="M77 146 123 192H57a12 12 0 0 1-12-12v-2Z" />
    </svg>
  );
}
