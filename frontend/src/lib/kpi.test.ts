import { describe, expect, it } from "vitest";
import { kpiColumns } from "./kpi";

describe("kpiColumns", () => {
  it("все в один ряд, если помещаются", () => {
    expect(kpiColumns(5, 5)).toBe(5);
    expect(kpiColumns(4, 6)).toBe(4);
  });

  it("ряды поровну, а не «5 + 1» или «4 + 2»", () => {
    expect(kpiColumns(6, 5)).toBe(3);
    expect(kpiColumns(6, 4)).toBe(3);
    expect(kpiColumns(6, 2)).toBe(2);
    expect(kpiColumns(4, 3)).toBe(2);
  });

  it("неполный последний ряд - как можно ровнее", () => {
    expect(kpiColumns(5, 4)).toBe(3);
    expect(kpiColumns(5, 2)).toBe(2);
    expect(kpiColumns(3, 2)).toBe(2);
  });

  it("узкий экран и пустой ряд", () => {
    expect(kpiColumns(5, 1)).toBe(1);
    expect(kpiColumns(5, 0)).toBe(1);
    expect(kpiColumns(0, 3)).toBe(1);
  });
});
