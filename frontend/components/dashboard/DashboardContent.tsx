'use client'

import React from 'react'
import Link from 'next/link'
import { Header } from '@/components/layout/Header'
import { Card, CardHeader, CardTitle, CardContent } from '@/components/ui/card'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Skeleton, ChartSkeleton } from '@/components/ui/skeleton'
import dynamic from 'next/dynamic'

const PriceLineChart = dynamic(
  () => import('@/components/charts/PriceLineChart').then((m) => m.PriceLineChart),
  { ssr: false, loading: () => <ChartSkeleton /> }
)
const ForecastChart = dynamic(
  () => import('@/components/charts/ForecastChart').then((m) => m.ForecastChart),
  { ssr: false, loading: () => <ChartSkeleton /> }
)
import { SupplierCard } from '@/components/suppliers/SupplierCard'
import { useCurrentPrices, usePriceHistory, usePriceForecast } from '@/lib/hooks/usePrices'
import { useSuppliers } from '@/lib/hooks/useSuppliers'
import { useRealtimePrices } from '@/lib/hooks/useRealtime'
import { useSavingsSummary } from '@/lib/hooks/useSavings'
import { SavingsTracker } from '@/components/gamification/SavingsTracker'
import { SetupChecklist } from '@/components/dashboard/SetupChecklist'
import { useSettingsStore } from '@/lib/store/settings'
import { formatCurrency } from '@/lib/utils/format'
import { cn } from '@/lib/utils/cn'
import {
  TrendingDown,
  TrendingUp,
  Minus,
  ArrowRight,
  Zap,
  Clock,
} from 'lucide-react'
import type { TimeRange, Supplier, RawPricePoint, RawForecastPriceEntry, RawSupplierRecord } from '@/types'

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
  const { data: forecastData, isLoading: forecastLoading } = usePriceForecast(
    region,
    24
  )
  const { data: suppliersData } = useSuppliers(region, annualUsage)
  const { data: savingsData } = useSavingsSummary()

  // Realtime connection
  const { isConnected } = useRealtimePrices(region)

  // Process price data for chart (handle both frontend and backend field names)
  const chartData = React.useMemo(() => {
    if (!historyData?.prices) return []
    return historyData.prices.map((p: RawPricePoint) => {
      const time = p.time || p.timestamp
      const price = p.price ?? (p.price_per_kwh != null ? Number(p.price_per_kwh) : null)
      return {
        time: typeof time === 'string' ? time : new Date(time as number).toISOString(),
        price,
        forecast: p.forecast ?? null,
        isOptimal: price !== null && price < 0.22,
      }
    })
  }, [historyData])

  // Get current price info (handle backend field names: current_price vs price)
  const rawPrice = pricesData?.prices?.[0] as RawPricePoint | undefined
  const currentPrice = rawPrice ? {
    price: Number(rawPrice.price ?? rawPrice.price_per_kwh ?? 0),
    trend: rawPrice.trend || 'stable',
    changePercent: rawPrice.changePercent ?? (rawPrice.price_change_24h ? Number(rawPrice.price_change_24h) : null),
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
  const optimalWindow = React.useMemo(() => {
    if (!forecastData?.forecast) return null
    const forecastObj = forecastData.forecast as RawForecastPriceEntry[] | { prices?: RawForecastPriceEntry[] }
    const prices: RawForecastPriceEntry[] = Array.isArray(forecastObj)
      ? forecastObj
      : (forecastObj as { prices?: RawForecastPriceEntry[] }).prices || []
    if (prices.length < 4) return null

    let minSum = Infinity
    let bestStart = 0
    for (let i = 0; i <= prices.length - 4; i++) {
      const sum = prices
        .slice(i, i + 4)
        .reduce((s: number, p: RawForecastPriceEntry) => s + Number(p.price_per_kwh ?? p.price ?? 0), 0)
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
  const topSuppliers = React.useMemo(() => (suppliersData?.suppliers?.slice(0, 2) || []).map((s: RawSupplierRecord) => ({
    id: s.id,
    name: s.name,
    logo: s.logo || s.logo_url,
    avgPricePerKwh: s.avgPricePerKwh ?? 0.22,
    standingCharge: s.standingCharge ?? 0.40,
    greenEnergy: s.greenEnergy ?? s.green_energy_provider ?? false,
    rating: s.rating ?? 0,
    estimatedAnnualCost: s.estimatedAnnualCost ?? 850,
    tariffType: (s.tariffType ?? (s.tariff_types?.[0] || 'variable')) as Supplier['tariffType'],
  })), [suppliersData, currentSupplier])

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

  // Error state
  if (pricesError) {
    return (
      <div>
        <Header title="Dashboard" />
        <div className="flex h-96 items-center justify-center">
          <div className="text-center">
            <p className="text-lg font-medium text-gray-900">
              Failed to load price data
            </p>
            <p className="mt-1 text-gray-500">
              Please try refreshing the page
            </p>
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
        <div className="grid gap-6 md:grid-cols-2 lg:grid-cols-4">
          {/* Current Price */}
          <Card>
            <CardContent className="p-4">
              <div className="flex items-center justify-between">
                <p className="text-sm font-medium text-gray-500">
                  Current Price
                </p>
                <Zap className="h-5 w-5 text-primary-500" />
              </div>
              <div className="mt-2 flex items-baseline gap-2">
                <p
                  data-testid="current-price"
                  className="text-2xl font-bold text-gray-900"
                >
                  {currentPrice
                    ? formatCurrency(currentPrice.price)
                    : '--'}
                </p>
                <span className="text-sm text-gray-500">/kWh</span>
              </div>
              <div
                data-testid="price-trend"
                className={cn(
                  'mt-2 flex items-center gap-1 text-sm',
                  trend === 'increasing'
                    ? 'text-danger-600'
                    : trend === 'decreasing'
                      ? 'text-success-600'
                      : 'text-gray-500'
                )}
              >
                <TrendIcon className="h-4 w-4" />
                <span>
                  {currentPrice?.changePercent
                    ? `${currentPrice.changePercent > 0 ? '+' : ''}${currentPrice.changePercent.toFixed(1)}%`
                    : 'Stable'}
                </span>
              </div>
            </CardContent>
          </Card>

          {/* Total Saved with streak */}
          <Card>
            <CardContent className="p-4">
              <div className="flex items-center justify-between">
                <p className="text-sm font-medium text-gray-500">
                  Total Saved
                </p>
                {savingsData && savingsData.streak_days > 0 && (
                  <Badge variant="success">{savingsData.streak_days}-day streak</Badge>
                )}
              </div>
              <p className="mt-2 text-2xl font-bold text-success-600">
                {savingsData ? formatCurrency(savingsData.monthly) : '--'}
              </p>
              <p className="mt-1 text-sm text-gray-500">
                {savingsData
                  ? `${formatCurrency(savingsData.weekly / 7)} today`
                  : 'Start saving to track'}
              </p>
            </CardContent>
          </Card>

          {/* Optimal Times - computed from forecast */}
          <Card>
            <CardContent className="p-4">
              <div className="flex items-center justify-between">
                <p className="text-sm font-medium text-gray-500">
                  Optimal Times
                </p>
                <Clock className="h-5 w-5 text-warning-500" />
              </div>
              {optimalWindow ? (
                <>
                  <p className="mt-2 text-lg font-semibold text-gray-900">
                    {optimalWindow.startLabel} - {optimalWindow.endLabel}
                  </p>
                  <p className="mt-1 text-sm text-success-600">
                    Avg {formatCurrency(optimalWindow.avgPrice)}/kWh
                  </p>
                </>
              ) : forecastLoading ? (
                <p className="mt-2 text-lg text-gray-400">Loading forecast...</p>
              ) : (
                <p className="mt-2 text-lg text-gray-400">No forecast data</p>
              )}
            </CardContent>
          </Card>

          {/* Suppliers */}
          <Card>
            <CardContent className="p-4">
              <div className="flex items-center justify-between">
                <p className="text-sm font-medium text-gray-500">
                  Suppliers
                </p>
                <Badge variant="success">Cheaper available</Badge>
              </div>
              <p className="mt-2 text-lg font-semibold text-gray-900">
                {suppliersData?.suppliers?.length || 0} options
              </p>
              <Link
                href="/suppliers"
                className="mt-1 inline-flex items-center text-sm text-primary-600 hover:text-primary-700"
              >
                Compare all
                <ArrowRight className="ml-1 h-4 w-4" />
              </Link>
            </CardContent>
          </Card>
        </div>

        {/* Main content grid */}
        <div className="mt-6 grid gap-6 lg:grid-cols-3">
          {/* Price chart - 2 columns */}
          <Card className="lg:col-span-2">
            <CardHeader>
              <div className="flex items-center justify-between">
                <CardTitle>Price History</CardTitle>
                <Link href="/prices">
                  <Button variant="ghost" size="sm">
                    View all prices
                    <ArrowRight className="ml-1 h-4 w-4" />
                  </Button>
                </Link>
              </div>
            </CardHeader>
            <CardContent>
              <PriceLineChart
                data={chartData}
                loading={historyLoading}
                timeRange={timeRange}
                onTimeRangeChange={setTimeRange}
                showCurrentPrice
                showTrend
                highlightOptimal
                height={300}
              />
            </CardContent>
          </Card>

          {/* Savings tracker with gamification */}
          <Card>
            <CardHeader>
              <CardTitle>Savings & Streaks</CardTitle>
            </CardHeader>
            <CardContent>
              <SavingsTracker
                dailySavings={savingsData ? savingsData.weekly / 7 : 0}
                weeklySavings={savingsData?.weekly ?? 0}
                monthlySavings={savingsData?.monthly ?? 0}
                streakDays={savingsData?.streak_days ?? 0}
                bestStreak={savingsData?.streak_days ?? 0}
                optimizationScore={0}
              />
            </CardContent>
          </Card>
        </div>

        {/* Second row */}
        <div className="mt-6 grid gap-6 lg:grid-cols-3">
          {/* 24-hour forecast */}
          <Card className="lg:col-span-2">
            <CardHeader>
              <CardTitle>24-Hour Forecast</CardTitle>
            </CardHeader>
            <CardContent>
              {forecastLoading ? (
                <Skeleton variant="rectangular" height={250} />
              ) : forecastData?.forecast ? (
                <ForecastChart
                  forecast={
                    Array.isArray(forecastData.forecast)
                      ? forecastData.forecast
                      : ((forecastData.forecast as { prices?: RawForecastPriceEntry[] }).prices || []).map((p: RawForecastPriceEntry, i: number) => ({
                          hour: i + 1,
                          price: Number(p.price_per_kwh ?? p.price ?? 0),
                          confidence: [
                            Number(p.price_per_kwh ?? p.price ?? 0) * 0.85,
                            Number(p.price_per_kwh ?? p.price ?? 0) * 1.15,
                          ] as [number, number],
                          timestamp: p.timestamp || new Date().toISOString(),
                        }))
                  }
                  currentPrice={currentPrice?.price}
                  showConfidence
                  height={250}
                />
              ) : (
                <div className="flex h-64 items-center justify-center text-gray-500">
                  Forecast unavailable
                </div>
              )}
            </CardContent>
          </Card>

          {/* Top suppliers */}
          <Card>
            <CardHeader>
              <div className="flex items-center justify-between">
                <CardTitle>Top Suppliers</CardTitle>
                <Link href="/suppliers">
                  <Button variant="ghost" size="sm">
                    View all
                  </Button>
                </Link>
              </div>
            </CardHeader>
            <CardContent className="space-y-4">
              {topSuppliers.map((supplier) => (
                <SupplierCard
                  key={supplier.id}
                  supplier={supplier}
                  isCurrent={supplier.id === currentSupplier?.id}
                  currentAnnualCost={currentSupplier?.estimatedAnnualCost}
                />
              ))}
            </CardContent>
          </Card>
        </div>

        {/* Schedule section - empty state until appliances are configured */}
        <Card className="mt-6">
          <CardHeader>
            <CardTitle>Today's Schedule</CardTitle>
          </CardHeader>
          <CardContent>
            <div className="flex h-32 items-center justify-center text-gray-400">
              <p>No optimization schedule set. Configure appliances in Settings to get started.</p>
            </div>
          </CardContent>
        </Card>
      </div>
    </div>
  )
}
