import { describe, expect, it } from "vitest";
import { bestPerRow, boundsOf, clip, computeLayout, NODE_HEIGHT, NODE_WIDTH } from "./layout";

const stages = (count: number) =>
  Array.from({ length: count }, (_, index) => ({ id: `s${index}`, sort_order: (index + 1) * 10 }));

describe("computeLayout", () => {
  it("lays stages out as a snake: the second row goes right to left", () => {
    const layout = computeLayout(stages(6), 3);
    expect(layout.s0.y).toBe(layout.s2.y);
    expect(layout.s3.y).toBeGreaterThan(layout.s0.y);
    // Четвёртый этап стоит под третьим - переход короткий и вертикальный.
    expect(layout.s3.x).toBe(layout.s2.x);
    expect(layout.s5.x).toBe(layout.s0.x);
  });

  it("keeps saved coordinates", () => {
    const layout = computeLayout([{ id: "a", sort_order: 1, layout_x: 500, layout_y: 300 }, ...stages(2)], 4);
    expect(layout.a).toEqual({ x: 500, y: 300 });
  });

  it("orders by sort_order, not by array order", () => {
    const layout = computeLayout(
      [
        { id: "second", sort_order: 20 },
        { id: "first", sort_order: 10 },
      ],
      4,
    );
    expect(layout.first.x).toBeLessThan(layout.second.x);
  });
});

describe("bestPerRow", () => {
  it("uses a wide layout on a wide screen and a narrow one on a phone", () => {
    expect(bestPerRow(14, 1600, 600)).toBeGreaterThanOrEqual(4);
    expect(bestPerRow(14, 360, 420)).toBeLessThanOrEqual(2);
  });
});

describe("helpers", () => {
  it("bounds include node size", () => {
    const bounds = boundsOf([{ x: 100, y: 100 }]);
    expect(bounds.maxX - bounds.minX).toBe(NODE_WIDTH);
    expect(bounds.maxY - bounds.minY).toBe(NODE_HEIGHT);
  });

  it("clips long names with an ellipsis", () => {
    expect(clip("Передача материалов и лицензий", 20)).toHaveLength(20);
    expect(clip("Короткое", 20)).toBe("Короткое");
  });
});
