import {
  CHART_COLORS,
  chartColor,
  chartTooltipStyle,
  chartTooltipStyleWithShadow,
} from "@/lib/constants/chartTokens";

describe("CHART_COLORS", () => {
  it("has 6 entries", () => {
    expect(CHART_COLORS).toHaveLength(6);
  });

  it("each entry is a CSS variable reference", () => {
    for (const c of CHART_COLORS) {
      expect(c).toMatch(/^var\(--chart-\d+\)$/);
    }
  });
});

describe("chartColor", () => {
  it("has primary color", () => {
    expect(chartColor.primary).toBe("var(--chart-1)");
  });

  it("has success color", () => {
    expect(typeof chartColor.success).toBe("string");
    expect(chartColor.success).toMatch(/var\(--/);
  });

  it("each value is a CSS variable reference", () => {
    for (const val of Object.values(chartColor)) {
      expect(val).toMatch(/^var\(--/);
    }
  });
});

describe("chartTooltipStyle", () => {
  it("has backgroundColor from chart token", () => {
    expect(chartTooltipStyle.backgroundColor).toMatch(/var\(--/);
  });

  it("has borderRadius", () => {
    expect(chartTooltipStyle.borderRadius).toBeTruthy();
  });
});

describe("chartTooltipStyleWithShadow", () => {
  it("includes all base tooltip styles", () => {
    expect(chartTooltipStyleWithShadow.backgroundColor).toMatch(/var\(--/);
    expect(chartTooltipStyleWithShadow.borderRadius).toBeTruthy();
  });

  it("adds boxShadow over base style", () => {
    expect(chartTooltipStyleWithShadow.boxShadow).toBeTruthy();
    expect(chartTooltipStyle.boxShadow).toBeUndefined();
  });
});
