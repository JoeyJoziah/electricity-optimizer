'use client'

import React from 'react'
import { Header } from '@/components/layout/Header'
import { Skeleton, ChartSkeleton } from '@/components/ui/skeleton'
import { useCurrentPrices, usePriceHistory, usePriceForecast } from '@/lib/hooks/usePrices'
import { useSuppliers } from '@/lib/hooks/useSuppliers'
import { useRealtimePrices } from '@/lib/hooks/useRealtime'
import { useSavingsSummary } from '@/lib/hooks/useSavings'
import { SetupChecklist } from '@/components/dashboard/SetupChecklist'
import { useSettingsStore } from '@/lib/store/settings'
import {
  TrendingDown,
  TrendingUp,
  Minus,
} from 'lucide-react'
import type { TimeRange, Supplier, RawSupplierRecord } from '@/types'
import type { ApiPrice, ApiPriceResponse, ApiPriceForecastModel } from '@/types/generated/api'

import { DashboardStatsRow } from './DashboardStatsRow'
import { DashboardCharts } from './DashboardCharts'
import { DashboardForecast } from './DashboardForecast'
import { DashboardSchedule } from './DashboardSchedule'
import type { CurrentPriceInfo, OptimalWindow } from './DashboardTypes'

// Map time range labels to hours for API calls
const TIME_RANGE_HOURS: Record<TimeRange, number> = {
  '6h': 6,
  '12h': 12,
  '24h': 24,
  '48h': 48,
  '7d': 168,
}

export default function DashboardContent() {
  const [timeRange, setTimeRange] = React.useState<TimeRange>('24h')
  const region = useSettingsStore((s) => s.region)
  const currentSupplier = useSettingsStore((s) => s.currentSupplier)
  const annualUsage = useSettingsStore((s) => s.annualUsageKwh)

  // Fetch data
  const {
    data: pricesData,
    isLoading: pricesLoading,
    error: pricesError,
  } = useCurrentPrices(region)
  const { data: historyData, isLoading: historyLoading } = usePriceHistory(
    region,
    TIME_RANGE_HOURS[timeRange]
  )
  const { data: forecastData, isLoading: forecastLoading, error: forecastError } = usePriceForecast(
    region,
    24
  )
  const { data: suppliersData } = useSuppliers(region, annualUsage)
  const { data: savingsData, error: savingsError } = useSavingsSummary()

  // Realtime connection (hook must be called for SSE side-effects)
  useRealtimePrices(region)

  // Process price data for chart — historyData.prices are ApiPrice (price_per_kwh is DecimalStr)
  const chartData = React.useMemo(() => {
    if (!historyData?.prices) return []
    return historyData.prices.map((p: ApiPrice) => {
      const price = p.price_per_kwh != null ? parseFloat(p.price_per_kwh) : null
      return {
        time: p.timestamp,
        price,
        forecast: null as number | null,
        isOptimal: price !== null && price < 0.22,
      }
    })
  }, [historyData])

  // Get current price info — pricesData.prices are ApiPriceResponse (current_price is DecimalStr)
  const rawPrice = pricesData?.prices?.[0] as ApiPriceResponse | undefined
  const currentPrice: CurrentPriceInfo | null = rawPrice ? {
    price: parseFloat(rawPrice.current_price),
    trend: 'stable',
    changePercent: rawPrice.price_change_24h != null ? parseFloat(rawPrice.price_change_24h) : null,
    region: rawPrice.region,
    supplier: rawPrice.supplier,
  } : null
  const trend = currentPrice?.trend || 'stable'
  const TrendIcon =
    trend === 'increasing'
      ? TrendingUp
      : trend === 'decreasing'
        ? TrendingDown
        : Minus

  // Compute cheapest 4-hour window from forecast data
  // forecastData.forecast is ApiPriceForecastModel — prices[] contains ApiPrice
  const optimalWindow: OptimalWindow | null = React.useMemo(() => {
    if (!forecastData?.forecast) return null
    const forecastModel = forecastData.forecast as ApiPriceForecastModel
    const prices: ApiPrice[] = forecastModel.prices || []
    if (prices.length < 4) return null

    let minSum = Infinity
    let bestStart = 0
    for (let i = 0; i <= prices.length - 4; i++) {
      const sum = prices
        .slice(i, i + 4)
        .reduce((s: number, p: ApiPrice) => s + parseFloat(p.price_per_kwh), 0)
      if (sum < minSum) {
        minSum = sum
        bestStart = i
      }
    }

    const fmtHour = (h: number) => `${String(h % 24).padStart(2, '0')}:00`
    return {
      startLabel: fmtHour(bestStart),
      endLabel: fmtHour(bestStart + 4),
      avgPrice: minSum / 4,
    }
  }, [forecastData])

  // Top 2 suppliers for quick comparison (map backend fields to frontend types)
  const topSuppliers: Supplier[] = React.useMemo(() => (suppliersData?.suppliers?.slice(0, 2) || []).map((s: RawSupplierRecord) => ({
    id: s.id,
    name: s.name,
    logo: s.logo || s.logo_url,
    avgPricePerKwh: s.avgPricePerKwh ?? 0.22,
    standingCharge: s.standingCharge ?? 0.40,
    greenEnergy: s.greenEnergy ?? s.green_energy_provider ?? false,
    rating: s.rating ?? 0,
    estimatedAnnualCost: s.estimatedAnnualCost ?? 850,
    tariffType: (s.tariffType ?? (s.tariff_types?.[0] || 'variable')) as Supplier['tariffType'],
  })), [suppliersData])

  // Loading state
  if (pricesLoading && historyLoading) {
    return (
      <div data-testid="dashboard-loading">
        <Header title="Dashboard" />
        <div className="p-6">
          <div className="grid gap-6 md:grid-cols-2 lg:grid-cols-4">
            {[1, 2, 3, 4].map((i) => (
              <Skeleton key={i} variant="rectangular" height={120} />
            ))}
          </div>
          <div className="mt-6">
            <ChartSkeleton height={300} />
          </div>
        </div>
      </div>
    )
  }

  // Error state — show actionable message instead of "cannot load"
  if (pricesError) {
    const is401 = pricesError && typeof pricesError === 'object' && 'status' in pricesError && (pricesError as { status: number }).status === 401
    return (
      <div>
        <Header title="Dashboard" />
        <div className="flex h-96 items-center justify-center">
          <div className="text-center">
            <p className="text-lg font-medium text-gray-900">
              {is401 ? 'Session expired' : 'Unable to load price data'}
            </p>
            <p className="mt-1 text-gray-500">
              {is401
                ? 'Please sign in again to continue.'
                : region
                  ? 'There may be a temporary issue with our servers.'
                  : 'Please set your region in Settings to see prices.'}
            </p>
            <button
              onClick={() => is401 ? (window.location.href = '/auth/login') : window.location.reload()}
              className="mt-4 inline-flex items-center rounded-lg bg-primary-600 px-4 py-2 text-sm font-medium text-white hover:bg-primary-700 transition-colors"
            >
              {is401 ? 'Sign In' : 'Retry'}
            </button>
          </div>
        </div>
      </div>
    )
  }

  return (
    <div data-testid="dashboard-container" className="flex flex-col">
      <Header title="Dashboard" />

      {/* Price alert banner */}
      {trend === 'decreasing' && (
        <div className="bg-success-50 px-4 py-3 text-center text-success-800">
          <TrendingDown className="mr-2 inline h-4 w-4" />
          Prices dropping - good time for high-energy tasks!
        </div>
      )}

      <div className="p-6">
        {/* Setup checklist for incomplete profiles */}
        <div className="mb-6">
          <SetupChecklist />
        </div>

        {/* Quick stats row */}
        <DashboardStatsRow
          currentPrice={currentPrice}
          trend={trend}
          TrendIcon={TrendIcon}
          savingsData={savingsData}
          optimalWindow={optimalWindow}
          forecastLoading={forecastLoading}
          suppliersCount={suppliersData?.suppliers?.length || 0}
          currentSupplier={currentSupplier}
          topSuppliers={topSuppliers}
        />

        {/* Main content grid: Price chart + Savings tracker */}
        <DashboardCharts
          chartData={chartData}
          historyLoading={historyLoading}
          timeRange={timeRange}
          onTimeRangeChange={setTimeRange}
          savingsData={savingsData}
          savingsError={savingsError}
        />

        {/* Second row: Forecast + Top suppliers */}
        <DashboardForecast
          forecastData={forecastData}
          forecastLoading={forecastLoading}
          forecastError={forecastError}
          currentPrice={currentPrice}
          topSuppliers={topSuppliers}
          currentSupplier={currentSupplier}
        />

        {/* Schedule section */}
        <DashboardSchedule />
      </div>
    </div>
  )
}
