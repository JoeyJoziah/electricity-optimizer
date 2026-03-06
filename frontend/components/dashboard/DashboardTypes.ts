import type { TimeRange, Supplier, PriceDataPoint } from '@/types'
import type { SavingsSummary } from '@/lib/hooks/useSavings'
import type { LucideIcon } from 'lucide-react'

/**
 * Normalized current price info derived from raw API data.
 */
export interface CurrentPriceInfo {
  price: number
  trend: 'increasing' | 'decreasing' | 'stable'
  changePercent: number | null
  region?: string
  supplier?: string
}

/**
 * Computed optimal usage window from forecast data.
 */
export interface OptimalWindow {
  startLabel: string
  endLabel: string
  avgPrice: number
}

/**
 * Re-export the canonical savings type for sub-component convenience.
 */
export type { SavingsSummary }

/**
 * Props for the stat cards row (Current Price, Total Saved, Optimal Times, Suppliers).
 */
export interface DashboardStatsRowProps {
  currentPrice: CurrentPriceInfo | null
  trend: 'increasing' | 'decreasing' | 'stable'
  TrendIcon: LucideIcon
  savingsData: SavingsSummary | null | undefined
  optimalWindow: OptimalWindow | null
  forecastLoading: boolean
  suppliersCount: number
  currentSupplier: { id: string; estimatedAnnualCost: number } | null
  topSuppliers: Supplier[]
}

/**
 * Props for the charts row (Price History + Savings Tracker).
 */
export interface DashboardChartsProps {
  chartData: PriceDataPoint[]
  historyLoading: boolean
  timeRange: TimeRange
  onTimeRangeChange: (range: TimeRange) => void
  savingsData: SavingsSummary | null | undefined
}

/**
 * Props for the forecast row (24-Hour Forecast + Top Suppliers).
 */
export interface DashboardForecastProps {
  forecastData: unknown
  forecastLoading: boolean
  currentPrice: CurrentPriceInfo | null
  topSuppliers: Supplier[]
  currentSupplier: { id: string; estimatedAnnualCost: number } | null
}
