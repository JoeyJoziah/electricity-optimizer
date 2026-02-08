import type { PriceDataPoint, Supplier, OptimizationSchedule } from '@/types'

/**
 * Calculate the trend of price data
 */
export function calculatePriceTrend(
  data: PriceDataPoint[]
): 'increasing' | 'decreasing' | 'stable' {
  if (data.length < 2) return 'stable'

  const recentPrices = data
    .filter((d) => d.price !== null)
    .slice(-5)
    .map((d) => d.price as number)

  if (recentPrices.length < 2) return 'stable'

  const avgFirst = recentPrices.slice(0, Math.floor(recentPrices.length / 2))
    .reduce((a, b) => a + b, 0) / Math.floor(recentPrices.length / 2)

  const avgSecond = recentPrices.slice(Math.ceil(recentPrices.length / 2))
    .reduce((a, b) => a + b, 0) / Math.ceil(recentPrices.length / 2)

  const changePercent = ((avgSecond - avgFirst) / avgFirst) * 100

  if (changePercent > 2) return 'increasing'
  if (changePercent < -2) return 'decreasing'
  return 'stable'
}

/**
 * Find optimal time periods for energy usage
 */
export function findOptimalPeriods(
  data: PriceDataPoint[],
  threshold: number = 0.8 // 80th percentile
): { start: string; end: string; avgPrice: number }[] {
  const pricesWithTime = data
    .filter((d) => d.price !== null || d.forecast !== null)
    .map((d) => ({
      time: d.time,
      price: d.price ?? d.forecast ?? 0,
    }))

  if (pricesWithTime.length === 0) return []

  // Calculate threshold price
  const sortedPrices = [...pricesWithTime].sort((a, b) => a.price - b.price)
  const thresholdIndex = Math.floor(sortedPrices.length * threshold)
  const thresholdPrice = sortedPrices[thresholdIndex]?.price ?? Infinity

  // Find contiguous periods below threshold
  const optimalPeriods: { start: string; end: string; avgPrice: number }[] = []
  let currentPeriod: { start: string; prices: number[] } | null = null

  for (const point of pricesWithTime) {
    if (point.price < thresholdPrice) {
      if (!currentPeriod) {
        currentPeriod = { start: point.time, prices: [point.price] }
      } else {
        currentPeriod.prices.push(point.price)
      }
    } else if (currentPeriod) {
      optimalPeriods.push({
        start: currentPeriod.start,
        end: point.time,
        avgPrice:
          currentPeriod.prices.reduce((a, b) => a + b, 0) /
          currentPeriod.prices.length,
      })
      currentPeriod = null
    }
  }

  // Handle last period
  if (currentPeriod && pricesWithTime.length > 0) {
    const lastTime = pricesWithTime[pricesWithTime.length - 1].time
    optimalPeriods.push({
      start: currentPeriod.start,
      end: lastTime,
      avgPrice:
        currentPeriod.prices.reduce((a, b) => a + b, 0) /
        currentPeriod.prices.length,
    })
  }

  return optimalPeriods
}

/**
 * Calculate estimated annual savings between two suppliers
 */
export function calculateAnnualSavings(
  currentSupplier: Supplier,
  newSupplier: Supplier
): number {
  return currentSupplier.estimatedAnnualCost - newSupplier.estimatedAnnualCost
}

/**
 * Calculate payback period in months considering exit fees
 */
export function calculatePaybackMonths(
  annualSavings: number,
  exitFee: number = 0
): number {
  if (annualSavings <= 0) return Infinity

  const monthlySavings = annualSavings / 12
  return Math.ceil(exitFee / monthlySavings)
}

/**
 * Calculate total savings from optimization schedules
 */
export function calculateTotalScheduleSavings(
  schedules: OptimizationSchedule[]
): number {
  return schedules.reduce((total, schedule) => total + schedule.savings, 0)
}

/**
 * Calculate confidence score for supplier recommendation
 */
export function calculateRecommendationConfidence(
  savings: number,
  priceVolatility: number,
  dataQuality: number
): number {
  // Weighted factors
  const savingsWeight = 0.4
  const volatilityWeight = 0.3
  const dataQualityWeight = 0.3

  // Normalize savings (cap at 500 for normalization)
  const normalizedSavings = Math.min(savings / 500, 1)

  // Volatility penalizes confidence (lower is better)
  const normalizedVolatility = 1 - Math.min(priceVolatility, 1)

  const confidence =
    normalizedSavings * savingsWeight +
    normalizedVolatility * volatilityWeight +
    dataQuality * dataQualityWeight

  return Math.round(confidence * 100) / 100
}

/**
 * Determine price category based on current vs historical average
 */
export function getPriceCategory(
  currentPrice: number,
  avgPrice: number
): 'cheap' | 'moderate' | 'expensive' {
  const ratio = currentPrice / avgPrice

  if (ratio < 0.8) return 'cheap'
  if (ratio > 1.2) return 'expensive'
  return 'moderate'
}

/**
 * Calculate the percentage change between two values
 */
export function calculateChangePercent(
  oldValue: number,
  newValue: number
): number {
  if (oldValue === 0) return 0
  return ((newValue - oldValue) / oldValue) * 100
}
