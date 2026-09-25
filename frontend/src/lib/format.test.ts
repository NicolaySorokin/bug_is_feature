import { describe, expect, it } from "vitest";
import { countLabel, fileSize, formatDate, initials, plural, shortName, toInputDate } from "./format";

describe("plural", () => {
  const forms: [string, string, string] = ["договор", "договора", "договоров"];

  it.each([
    [1, "договор"],
    [2, "договора"],
    [5, "договоров"],
    [11, "договоров"],
    [12, "договоров"],
    [21, "договор"],
    [22, "договора"],
    [111, "договоров"],
  ])("%i -> %s", (count, expected) => {
    expect(plural(count, forms)).toBe(expected);
  });

  it("countLabel adds the number", () => {
    expect(countLabel(3, forms)).toBe("3 договора");
  });
});

describe("dates", () => {
  it("date without time stays the same day in any time zone", () => {
    expect(formatDate("2026-09-25")).toBe("25.09.2026");
  });

  it("empty value becomes a dash", () => {
    expect(formatDate(null)).toBe("—");
    expect(formatDate("not a date")).toBe("—");
  });

  it("input date uses local calendar day", () => {
    expect(toInputDate(new Date(2026, 0, 5))).toBe("2026-01-05");
  });
});

describe("names and sizes", () => {
  it("short name keeps surname and initials", () => {
    expect(shortName("Петров Пётр Алексеевич")).toBe("Петров П. А.");
    expect(shortName("Петров")).toBe("Петров");
  });

  it("initials take two words", () => {
    expect(initials("Петров Пётр Алексеевич")).toBe("ПП");
  });

  it("file size is human readable", () => {
    expect(fileSize(512)).toBe("512 Б");
    expect(fileSize(2048)).toBe("2 КБ");
    expect(fileSize(3 * 1024 * 1024)).toBe("3,0 МБ");
  });
});
