import {
  calculatePriceTrend,
  findOptimalPeriods,
  calculateAnnualSavings,
  calculatePaybackMonths,
  calculateTotalScheduleSavings,
  calculateRecommendationConfidence,
  getPriceCategory,
  calculateChangePercent,
} from "@/lib/utils/calculations";
import type { PriceDataPoint, Supplier, OptimizationSchedule } from "@/types";

function makePoint(time: string, price: number | null): PriceDataPoint {
  return { time, price, forecast: null } as unknown as PriceDataPoint;
}

// ---------------------------------------------------------------------------
// calculatePriceTrend
// ---------------------------------------------------------------------------
describe("calculatePriceTrend", () => {
  it("returns stable for empty array", () => {
    expect(calculatePriceTrend([])).toBe("stable");
  });

  it("returns stable for single-element array", () => {
    expect(calculatePriceTrend([makePoint("t1", 10)])).toBe("stable");
  });

  it("returns increasing when recent prices are clearly rising", () => {
    const data = [
      makePoint("t1", 10),
      makePoint("t2", 10),
      makePoint("t3", 15),
      makePoint("t4", 15),
    ];
    expect(calculatePriceTrend(data)).toBe("increasing");
  });

  it("returns decreasing when recent prices are clearly falling", () => {
    const data = [
      makePoint("t1", 15),
      makePoint("t2", 15),
      makePoint("t3", 10),
      makePoint("t4", 10),
    ];
    expect(calculatePriceTrend(data)).toBe("decreasing");
  });

  it("returns stable when prices are flat", () => {
    const data = [
      makePoint("t1", 10),
      makePoint("t2", 10),
      makePoint("t3", 10),
      makePoint("t4", 10),
    ];
    expect(calculatePriceTrend(data)).toBe("stable");
  });

  it("ignores null price entries", () => {
    const data = [makePoint("t1", null), makePoint("t2", null)];
    expect(calculatePriceTrend(data)).toBe("stable");
  });
});

// ---------------------------------------------------------------------------
// findOptimalPeriods
// ---------------------------------------------------------------------------
describe("findOptimalPeriods", () => {
  it("returns empty array for empty data", () => {
    expect(findOptimalPeriods([])).toEqual([]);
  });

  it("returns periods below the threshold price", () => {
    const data = [
      makePoint("08:00", 5),
      makePoint("09:00", 5),
      makePoint("10:00", 20),
      makePoint("11:00", 20),
      makePoint("12:00", 5),
    ];
    const result = findOptimalPeriods(data, 0.8);
    expect(result.length).toBeGreaterThan(0);
    result.forEach((p) => {
      expect(p.avgPrice).toBeLessThan(20);
    });
  });
});

// ---------------------------------------------------------------------------
// calculateAnnualSavings
// ---------------------------------------------------------------------------
describe("calculateAnnualSavings", () => {
  it("returns difference between current and new annual cost", () => {
    const current = { estimatedAnnualCost: 1200 } as Supplier;
    const newSupplier = { estimatedAnnualCost: 1000 } as Supplier;
    expect(calculateAnnualSavings(current, newSupplier)).toBe(200);
  });

  it("returns negative savings when new supplier is more expensive", () => {
    const current = { estimatedAnnualCost: 1000 } as Supplier;
    const newSupplier = { estimatedAnnualCost: 1200 } as Supplier;
    expect(calculateAnnualSavings(current, newSupplier)).toBe(-200);
  });
});

// ---------------------------------------------------------------------------
// calculatePaybackMonths
// ---------------------------------------------------------------------------
describe("calculatePaybackMonths", () => {
  it("returns Infinity when annualSavings is 0", () => {
    expect(calculatePaybackMonths(0, 100)).toBe(Infinity);
  });

  it("returns Infinity when annualSavings is negative", () => {
    expect(calculatePaybackMonths(-50, 100)).toBe(Infinity);
  });

  it("returns 0 exit fee as immediate payback", () => {
    expect(calculatePaybackMonths(120, 0)).toBe(0);
  });

  it("calculates payback correctly", () => {
    // $120/yr savings = $10/mo; $25 exit fee → ceil(25/10) = 3 months
    expect(calculatePaybackMonths(120, 25)).toBe(3);
  });
});

// ---------------------------------------------------------------------------
// calculateTotalScheduleSavings
// ---------------------------------------------------------------------------
describe("calculateTotalScheduleSavings", () => {
  it("returns 0 for empty array", () => {
    expect(calculateTotalScheduleSavings([])).toBe(0);
  });

  it("sums savings from all schedules", () => {
    const schedules = [
      { savings: 10 },
      { savings: 20 },
      { savings: 30 },
    ] as OptimizationSchedule[];
    expect(calculateTotalScheduleSavings(schedules)).toBe(60);
  });
});

// ---------------------------------------------------------------------------
// calculateRecommendationConfidence
// ---------------------------------------------------------------------------
describe("calculateRecommendationConfidence", () => {
  it("returns a value between 0 and 1", () => {
    const confidence = calculateRecommendationConfidence(100, 0.2, 0.8);
    expect(confidence).toBeGreaterThanOrEqual(0);
    expect(confidence).toBeLessThanOrEqual(1);
  });

  it("returns higher confidence with zero volatility and full data quality", () => {
    const high = calculateRecommendationConfidence(500, 0, 1);
    const low = calculateRecommendationConfidence(10, 0.9, 0.2);
    expect(high).toBeGreaterThan(low);
  });
});

// ---------------------------------------------------------------------------
// getPriceCategory
// ---------------------------------------------------------------------------
describe("getPriceCategory", () => {
  it("returns cheap when price is much lower than average", () => {
    expect(getPriceCategory(7, 10)).toBe("cheap"); // ratio 0.7 < 0.8
  });

  it("returns expensive when price is much higher than average", () => {
    expect(getPriceCategory(13, 10)).toBe("expensive"); // ratio 1.3 > 1.2
  });

  it("returns moderate when price is close to average", () => {
    expect(getPriceCategory(10, 10)).toBe("moderate"); // ratio 1.0
  });

  it("returns moderate at the cheap boundary (ratio=0.8)", () => {
    expect(getPriceCategory(8, 10)).toBe("moderate"); // exactly 0.8 → not < 0.8
  });
});

// ---------------------------------------------------------------------------
// calculateChangePercent
// ---------------------------------------------------------------------------
describe("calculateChangePercent", () => {
  it("returns 0 when oldValue is 0", () => {
    expect(calculateChangePercent(0, 100)).toBe(0);
  });

  it("calculates positive percent change", () => {
    expect(calculateChangePercent(100, 150)).toBe(50);
  });

  it("calculates negative percent change", () => {
    expect(calculateChangePercent(100, 50)).toBe(-50);
  });

  it("calculates 100% change correctly", () => {
    expect(calculateChangePercent(50, 100)).toBe(100);
  });
});
