import {
  calculatePriceTrend,
  findOptimalPeriods,
  calculateAnnualSavings,
  calculatePaybackMonths,
  calculateTotalScheduleSavings,
  calculateRecommendationConfidence,
  getPriceCategory,
  calculateChangePercent,
} from '@/lib/utils/calculations'
import type { PriceDataPoint, Supplier, OptimizationSchedule } from '@/types'

// ---------------------------------------------------------------------------
// Helpers to build test fixtures
// ---------------------------------------------------------------------------

function makePricePoint(
  time: string,
  price: number | null,
  forecast: number | null = null
): PriceDataPoint {
  return { time, price, forecast }
}

function makeSupplier(overrides: Partial<Supplier> = {}): Supplier {
  return {
    id: '1',
    name: 'Test Supplier',
    avgPricePerKwh: 0.15,
    standingCharge: 25,
    greenEnergy: false,
    rating: 4,
    estimatedAnnualCost: 1200,
    tariffType: 'variable',
    ...overrides,
  }
}

function makeSchedule(overrides: Partial<OptimizationSchedule> = {}): OptimizationSchedule {
  return {
    applianceId: 'a1',
    applianceName: 'Dishwasher',
    scheduledStart: '2026-01-15T02:00:00Z',
    scheduledEnd: '2026-01-15T04:00:00Z',
    estimatedCost: 0.45,
    savings: 0.15,
    reason: 'Off-peak pricing',
    ...overrides,
  }
}

// ---------------------------------------------------------------------------
// calculatePriceTrend
// ---------------------------------------------------------------------------

describe('calculatePriceTrend', () => {
  it('should return "stable" for empty data', () => {
    expect(calculatePriceTrend([])).toBe('stable')
  })

  it('should return "stable" for a single data point', () => {
    const data = [makePricePoint('2026-01-15T00:00:00Z', 10)]
    expect(calculatePriceTrend(data)).toBe('stable')
  })

  it('should return "increasing" when prices rise significantly', () => {
    // Use even-length array so slice halves divide evenly
    // avgFirst = (10+10)/2 = 10, avgSecond = (13+15)/2 = 14
    // changePercent = (14-10)/10 * 100 = 40 => "increasing"
    const data = [
      makePricePoint('2026-01-15T00:00:00Z', 10),
      makePricePoint('2026-01-15T01:00:00Z', 10),
      makePricePoint('2026-01-15T02:00:00Z', 13),
      makePricePoint('2026-01-15T03:00:00Z', 15),
    ]
    expect(calculatePriceTrend(data)).toBe('increasing')
  })

  it('should return "decreasing" when prices drop significantly', () => {
    // avgFirst = (15+14)/2 = 14.5, avgSecond = (10+9)/2 = 9.5
    // changePercent = (9.5-14.5)/14.5 * 100 = -34.5 => "decreasing"
    const data = [
      makePricePoint('2026-01-15T00:00:00Z', 15),
      makePricePoint('2026-01-15T01:00:00Z', 14),
      makePricePoint('2026-01-15T02:00:00Z', 10),
      makePricePoint('2026-01-15T03:00:00Z', 9),
    ]
    expect(calculatePriceTrend(data)).toBe('decreasing')
  })

  it('should return "stable" when change is within +/-2%', () => {
    // Use even-length array: avgFirst = (10+10)/2 = 10, avgSecond = (10.1+10.1)/2 = 10.1
    // changePercent = (10.1-10)/10 * 100 = 1 => within +/-2 => "stable"
    const data = [
      makePricePoint('2026-01-15T00:00:00Z', 10),
      makePricePoint('2026-01-15T01:00:00Z', 10),
      makePricePoint('2026-01-15T02:00:00Z', 10.1),
      makePricePoint('2026-01-15T03:00:00Z', 10.1),
    ]
    expect(calculatePriceTrend(data)).toBe('stable')
  })

  it('should filter out null prices', () => {
    const data = [
      makePricePoint('2026-01-15T00:00:00Z', null),
      makePricePoint('2026-01-15T01:00:00Z', 10),
      makePricePoint('2026-01-15T02:00:00Z', null),
      makePricePoint('2026-01-15T03:00:00Z', 10.1),
    ]
    expect(calculatePriceTrend(data)).toBe('stable')
  })

  it('should return "stable" when all prices are null', () => {
    const data = [
      makePricePoint('2026-01-15T00:00:00Z', null),
      makePricePoint('2026-01-15T01:00:00Z', null),
    ]
    expect(calculatePriceTrend(data)).toBe('stable')
  })

  it('should only use the last 5 data points', () => {
    // 10 entries: first 6 are decreasing, last 4 are increasing
    // After filter (all non-null) and slice(-5), recentPrices includes last 5
    // If it used all 10, the overall trend would be ambiguous.
    // The last 4 are: [5, 8, 12, 18] - clearly increasing
    // slice(-5) => [3, 5, 8, 12, 18]
    // avgFirst = slice(0,2) = [3,5] => 8/2 = 4
    // avgSecond = slice(3) = [12,18] => 30/3 = 10
    // changePercent = (10-4)/4 * 100 = 150 => "increasing"
    // If function used all 10, first entries (50,40,30,20,10,3) would pull toward "decreasing"
    const data = [
      makePricePoint('2026-01-15T00:00:00Z', 50),
      makePricePoint('2026-01-15T01:00:00Z', 40),
      makePricePoint('2026-01-15T02:00:00Z', 30),
      makePricePoint('2026-01-15T03:00:00Z', 20),
      makePricePoint('2026-01-15T04:00:00Z', 10),
      makePricePoint('2026-01-15T05:00:00Z', 3),
      makePricePoint('2026-01-15T06:00:00Z', 5),
      makePricePoint('2026-01-15T07:00:00Z', 8),
      makePricePoint('2026-01-15T08:00:00Z', 12),
      makePricePoint('2026-01-15T09:00:00Z', 18),
    ]
    expect(calculatePriceTrend(data)).toBe('increasing')
  })
})

// ---------------------------------------------------------------------------
// findOptimalPeriods
// ---------------------------------------------------------------------------

describe('findOptimalPeriods', () => {
  it('should return empty array for empty data', () => {
    expect(findOptimalPeriods([])).toEqual([])
  })

  it('should return empty array when all prices are null with no forecasts', () => {
    const data = [
      makePricePoint('2026-01-15T00:00:00Z', null),
      makePricePoint('2026-01-15T01:00:00Z', null),
    ]
    expect(findOptimalPeriods(data)).toEqual([])
  })

  it('should identify optimal periods below threshold', () => {
    // 10 data points with prices 1..10; default threshold 0.8 => 80th percentile
    // sorted prices: 1,2,3,4,5,6,7,8,9,10
    // thresholdIndex = floor(10 * 0.8) = 8 => thresholdPrice = 9
    // Points with price < 9: prices 1-8
    const data = Array.from({ length: 10 }, (_, i) =>
      makePricePoint(`2026-01-15T${String(i).padStart(2, '0')}:00:00Z`, i + 1)
    )

    const periods = findOptimalPeriods(data)
    expect(periods.length).toBeGreaterThan(0)
    // All optimal periods should have avgPrice < 9
    for (const period of periods) {
      expect(period.avgPrice).toBeLessThan(9)
    }
  })

  it('should use forecast when price is null', () => {
    const data = [
      makePricePoint('2026-01-15T00:00:00Z', null, 5),
      makePricePoint('2026-01-15T01:00:00Z', null, 10),
      makePricePoint('2026-01-15T02:00:00Z', null, 15),
      makePricePoint('2026-01-15T03:00:00Z', null, 20),
      makePricePoint('2026-01-15T04:00:00Z', null, 25),
    ]

    const periods = findOptimalPeriods(data)
    expect(periods.length).toBeGreaterThan(0)
    expect(periods[0].start).toBe('2026-01-15T00:00:00Z')
  })

  it('should support custom threshold', () => {
    const data = Array.from({ length: 10 }, (_, i) =>
      makePricePoint(`2026-01-15T${String(i).padStart(2, '0')}:00:00Z`, i + 1)
    )

    // threshold 0.5 => only bottom half qualify
    const periods50 = findOptimalPeriods(data, 0.5)
    // threshold 0.9 => almost all qualify
    const periods90 = findOptimalPeriods(data, 0.9)

    // More lenient threshold should yield more or equal optimal time
    const totalOptimal50 = periods50.reduce((acc, p) => {
      const prices = data.filter(
        d => d.time >= p.start && d.time <= p.end && d.price !== null
      )
      return acc + prices.length
    }, 0)

    const totalOptimal90 = periods90.reduce((acc, p) => {
      const prices = data.filter(
        d => d.time >= p.start && d.time <= p.end && d.price !== null
      )
      return acc + prices.length
    }, 0)

    expect(totalOptimal90).toBeGreaterThanOrEqual(totalOptimal50)
  })

  it('should handle a trailing optimal period at end of data', () => {
    // Last points are cheap, no subsequent expensive point to end the period
    const data = [
      makePricePoint('2026-01-15T00:00:00Z', 100),
      makePricePoint('2026-01-15T01:00:00Z', 100),
      makePricePoint('2026-01-15T02:00:00Z', 100),
      makePricePoint('2026-01-15T03:00:00Z', 1),
      makePricePoint('2026-01-15T04:00:00Z', 1),
    ]

    const periods = findOptimalPeriods(data)
    // The trailing cheap period should be captured
    const lastPeriod = periods[periods.length - 1]
    expect(lastPeriod.end).toBe('2026-01-15T04:00:00Z')
  })

  it('should return correct avgPrice for each period', () => {
    const data = [
      makePricePoint('2026-01-15T00:00:00Z', 2),
      makePricePoint('2026-01-15T01:00:00Z', 4),
      makePricePoint('2026-01-15T02:00:00Z', 100),
      makePricePoint('2026-01-15T03:00:00Z', 3),
      makePricePoint('2026-01-15T04:00:00Z', 5),
    ]

    const periods = findOptimalPeriods(data)
    for (const period of periods) {
      expect(typeof period.avgPrice).toBe('number')
      expect(period.avgPrice).toBeGreaterThan(0)
    }
  })
})

// ---------------------------------------------------------------------------
// calculateAnnualSavings
// ---------------------------------------------------------------------------

describe('calculateAnnualSavings', () => {
  it('should return positive savings when new supplier is cheaper', () => {
    const current = makeSupplier({ estimatedAnnualCost: 1200 })
    const cheaper = makeSupplier({ estimatedAnnualCost: 1000 })
    expect(calculateAnnualSavings(current, cheaper)).toBe(200)
  })

  it('should return negative savings when new supplier is more expensive', () => {
    const current = makeSupplier({ estimatedAnnualCost: 1000 })
    const expensive = makeSupplier({ estimatedAnnualCost: 1200 })
    expect(calculateAnnualSavings(current, expensive)).toBe(-200)
  })

  it('should return zero when costs are identical', () => {
    const supplierA = makeSupplier({ estimatedAnnualCost: 1200 })
    const supplierB = makeSupplier({ estimatedAnnualCost: 1200 })
    expect(calculateAnnualSavings(supplierA, supplierB)).toBe(0)
  })
})

// ---------------------------------------------------------------------------
// calculatePaybackMonths
// ---------------------------------------------------------------------------

describe('calculatePaybackMonths', () => {
  it('should return 0 months when there is no exit fee', () => {
    expect(calculatePaybackMonths(120, 0)).toBe(0)
  })

  it('should calculate payback months correctly', () => {
    // 120 annual savings => 10/month => 50 exit fee => 5 months
    expect(calculatePaybackMonths(120, 50)).toBe(5)
  })

  it('should round up to the nearest month', () => {
    // 120 annual => 10/month => 15 exit fee => 1.5 => ceil => 2
    expect(calculatePaybackMonths(120, 15)).toBe(2)
  })

  it('should return Infinity when annual savings is zero', () => {
    expect(calculatePaybackMonths(0, 50)).toBe(Infinity)
  })

  it('should return Infinity when annual savings is negative', () => {
    expect(calculatePaybackMonths(-100, 50)).toBe(Infinity)
  })

  it('should default exitFee to 0', () => {
    expect(calculatePaybackMonths(120)).toBe(0)
  })
})

// ---------------------------------------------------------------------------
// calculateTotalScheduleSavings
// ---------------------------------------------------------------------------

describe('calculateTotalScheduleSavings', () => {
  it('should sum up savings from all schedules', () => {
    const schedules = [
      makeSchedule({ savings: 0.15 }),
      makeSchedule({ savings: 0.25 }),
      makeSchedule({ savings: 0.10 }),
    ]
    expect(calculateTotalScheduleSavings(schedules)).toBeCloseTo(0.50, 10)
  })

  it('should return 0 for empty schedules', () => {
    expect(calculateTotalScheduleSavings([])).toBe(0)
  })

  it('should handle a single schedule', () => {
    const schedules = [makeSchedule({ savings: 1.23 })]
    expect(calculateTotalScheduleSavings(schedules)).toBeCloseTo(1.23, 10)
  })
})

// ---------------------------------------------------------------------------
// calculateRecommendationConfidence
// ---------------------------------------------------------------------------

describe('calculateRecommendationConfidence', () => {
  it('should return a value between 0 and 1', () => {
    const result = calculateRecommendationConfidence(250, 0.5, 0.8)
    expect(result).toBeGreaterThanOrEqual(0)
    expect(result).toBeLessThanOrEqual(1)
  })

  it('should return maximum confidence for high savings, low volatility, high data quality', () => {
    // savings 500+ => normalized 1, volatility 0 => normalized 1, dataQuality 1
    const result = calculateRecommendationConfidence(500, 0, 1)
    // 1*0.4 + 1*0.3 + 1*0.3 = 1.0
    expect(result).toBe(1)
  })

  it('should return minimum confidence for zero savings, high volatility, zero data quality', () => {
    const result = calculateRecommendationConfidence(0, 1, 0)
    // 0*0.4 + 0*0.3 + 0*0.3 = 0
    expect(result).toBe(0)
  })

  it('should cap savings normalization at 500', () => {
    const at500 = calculateRecommendationConfidence(500, 0.5, 0.5)
    const at1000 = calculateRecommendationConfidence(1000, 0.5, 0.5)
    expect(at500).toBe(at1000)
  })

  it('should cap volatility at 1', () => {
    const at1 = calculateRecommendationConfidence(250, 1, 0.5)
    const at2 = calculateRecommendationConfidence(250, 2, 0.5)
    expect(at1).toBe(at2)
  })

  it('should return a rounded value with at most 2 decimal places', () => {
    const result = calculateRecommendationConfidence(100, 0.3, 0.7)
    const decimalPlaces = result.toString().split('.')[1]?.length ?? 0
    expect(decimalPlaces).toBeLessThanOrEqual(2)
  })
})

// ---------------------------------------------------------------------------
// getPriceCategory
// ---------------------------------------------------------------------------

describe('getPriceCategory', () => {
  it('should return "cheap" when current price is below 80% of average', () => {
    expect(getPriceCategory(7, 10)).toBe('cheap')
    expect(getPriceCategory(5, 10)).toBe('cheap')
  })

  it('should return "expensive" when current price is above 120% of average', () => {
    expect(getPriceCategory(13, 10)).toBe('expensive')
    expect(getPriceCategory(20, 10)).toBe('expensive')
  })

  it('should return "moderate" when price is between 80% and 120% of average', () => {
    expect(getPriceCategory(10, 10)).toBe('moderate')
    expect(getPriceCategory(8, 10)).toBe('moderate')
    expect(getPriceCategory(12, 10)).toBe('moderate')
  })

  it('should handle boundary values (exactly 0.8 and 1.2 ratio)', () => {
    // ratio = 0.8 => not < 0.8, not > 1.2 => moderate
    expect(getPriceCategory(8, 10)).toBe('moderate')
    // ratio = 1.2 => not < 0.8, not > 1.2 => moderate
    expect(getPriceCategory(12, 10)).toBe('moderate')
  })

  it('should handle equal prices as moderate', () => {
    expect(getPriceCategory(15, 15)).toBe('moderate')
  })
})

// ---------------------------------------------------------------------------
// calculateChangePercent
// ---------------------------------------------------------------------------

describe('calculateChangePercent', () => {
  it('should calculate positive percentage change', () => {
    expect(calculateChangePercent(100, 150)).toBe(50)
  })

  it('should calculate negative percentage change', () => {
    expect(calculateChangePercent(100, 50)).toBe(-50)
  })

  it('should return 0 when old value is 0', () => {
    expect(calculateChangePercent(0, 100)).toBe(0)
  })

  it('should return 0 when both values are 0', () => {
    expect(calculateChangePercent(0, 0)).toBe(0)
  })

  it('should return 0 for no change', () => {
    expect(calculateChangePercent(100, 100)).toBe(0)
  })

  it('should handle small fractional changes', () => {
    const result = calculateChangePercent(10, 10.5)
    expect(result).toBeCloseTo(5, 10)
  })

  it('should return 100 for a doubling', () => {
    expect(calculateChangePercent(50, 100)).toBe(100)
  })

  it('should return -100 when new value is 0', () => {
    expect(calculateChangePercent(50, 0)).toBe(-100)
  })
})
