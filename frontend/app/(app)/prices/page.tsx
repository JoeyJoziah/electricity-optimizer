'use client'

import React from 'react'
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
import { useCurrentPrices, usePriceHistory, usePriceForecast, useOptimalPeriods } from '@/lib/hooks/usePrices'
import { useSettingsStore } from '@/lib/store/settings'
import { formatCurrency, formatTime } from '@/lib/utils/format'
import { cn } from '@/lib/utils/cn'
import {
  TrendingDown,
  TrendingUp,
  Minus,
  Clock,
  Calendar,
  Bell,
  AlertCircle,
} from 'lucide-react'
import type { TimeRange } from '@/types'

export default function PricesPage() {
  const [timeRange, setTimeRange] = React.useState<TimeRange>('24h')
  const region = useSettingsStore((s) => s.region)

  // Fetch data
  const { data: pricesData, isLoading: pricesLoading } = useCurrentPrices(region)
  const { data: historyData, isLoading: historyLoading } = usePriceHistory(
    region,
    parseInt(timeRange) || 24
  )
  const { data: forecastData, isLoading: forecastLoading } = usePriceForecast(
    region,
    48
  )
  const { data: optimalData } = useOptimalPeriods(region, 24)

  // Process chart data (handle both frontend and backend field names)
  const chartData = React.useMemo(() => {
    if (!historyData?.prices) return []

    const history: { time: string; price: number | null; forecast: number | null; isOptimal: boolean }[] = historyData.prices.map((p: any) => {
      const time = p.time || p.timestamp
      const price = p.price ?? (p.price_per_kwh != null ? Number(p.price_per_kwh) : null)
      return {
        time: typeof time === 'string' ? time : new Date(time).toISOString(),
        price,
        forecast: null as number | null,
        isOptimal: price !== null && price < 0.22,
      }
    })

    // Add forecast data (handle both array and backend object shape)
    if (forecastData?.forecast) {
      const fc = forecastData.forecast as any
      const forecastItems = Array.isArray(fc)
        ? fc
        : (fc.prices || []).map((p: any, i: number) => ({
            hour: i + 1,
            price: Number(p.price_per_kwh ?? p.price ?? 0),
          }))
      const now = new Date()
      forecastItems.forEach((f: any) => {
        const forecastTime = new Date(now.getTime() + f.hour * 60 * 60 * 1000)
        history.push({
          time: forecastTime.toISOString(),
          price: null,
          forecast: f.price,
          isOptimal: f.price < 0.20,
        })
      })
    }

    return history
  }, [historyData, forecastData])

  // Map current price from backend fields
  const rawPrice = pricesData?.prices?.[0] as any
  const currentPrice = rawPrice ? {
    price: Number(rawPrice.price ?? rawPrice.current_price ?? 0),
    trend: rawPrice.trend || 'stable' as const,
    changePercent: rawPrice.changePercent ?? (rawPrice.price_change_24h ? Number(rawPrice.price_change_24h) : null),
    region: rawPrice.region,
  } : null
  const trend = currentPrice?.trend || 'stable'
  const TrendIcon =
    trend === 'increasing'
      ? TrendingUp
      : trend === 'decreasing'
        ? TrendingDown
        : Minus

  // Calculate price statistics (handle backend field names)
  const stats = React.useMemo(() => {
    if (!historyData?.prices) return null

    const prices = historyData.prices
      .map((p: any) => p.price ?? (p.price_per_kwh != null ? Number(p.price_per_kwh) : null))
      .filter((p: number | null): p is number => p !== null)

    if (prices.length === 0) return null

    return {
      min: Math.min(...prices),
      max: Math.max(...prices),
      avg: prices.reduce((a: number, b: number) => a + b, 0) / prices.length,
    }
  }, [historyData])

  return (
    <div className="flex flex-col">
      <Header title="Electricity Prices" />

      <div className="p-6">
        {/* Stats row */}
        <div className="grid gap-6 md:grid-cols-2 lg:grid-cols-4">
          {/* Current Price */}
          <Card>
            <CardContent className="p-4">
              <p className="text-sm font-medium text-gray-500">Current Price</p>
              {pricesLoading ? (
                <Skeleton variant="text" className="mt-2 h-8 w-24" />
              ) : (
                <>
                  <div className="mt-2 flex items-baseline gap-2">
                    <p className="text-3xl font-bold text-gray-900">
                      {currentPrice ? formatCurrency(currentPrice.price) : '--'}
                    </p>
                    <span className="text-gray-500">/kWh</span>
                  </div>
                  <div
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
                    <span className="text-gray-400">vs last hour</span>
                  </div>
                </>
              )}
            </CardContent>
          </Card>

          {/* Today's Low */}
          <Card>
            <CardContent className="p-4">
              <p className="text-sm font-medium text-gray-500">Today's Low</p>
              {pricesLoading ? (
                <Skeleton variant="text" className="mt-2 h-8 w-24" />
              ) : (
                <>
                  <p className="mt-2 text-3xl font-bold text-success-600">
                    {stats ? formatCurrency(stats.min) : '--'}
                  </p>
                  <p className="mt-1 text-sm text-gray-500">/kWh</p>
                </>
              )}
            </CardContent>
          </Card>

          {/* Today's High */}
          <Card>
            <CardContent className="p-4">
              <p className="text-sm font-medium text-gray-500">Today's High</p>
              {pricesLoading ? (
                <Skeleton variant="text" className="mt-2 h-8 w-24" />
              ) : (
                <>
                  <p className="mt-2 text-3xl font-bold text-danger-600">
                    {stats ? formatCurrency(stats.max) : '--'}
                  </p>
                  <p className="mt-1 text-sm text-gray-500">/kWh</p>
                </>
              )}
            </CardContent>
          </Card>

          {/* Average */}
          <Card>
            <CardContent className="p-4">
              <p className="text-sm font-medium text-gray-500">Average</p>
              {pricesLoading ? (
                <Skeleton variant="text" className="mt-2 h-8 w-24" />
              ) : (
                <>
                  <p className="mt-2 text-3xl font-bold text-gray-900">
                    {stats ? formatCurrency(stats.avg) : '--'}
                  </p>
                  <p className="mt-1 text-sm text-gray-500">/kWh</p>
                </>
              )}
            </CardContent>
          </Card>
        </div>

        {/* Main chart */}
        <Card className="mt-6">
          <CardHeader>
            <div className="flex items-center justify-between">
              <CardTitle>Price History & Forecast</CardTitle>
              <div className="flex items-center gap-2">
                <Badge variant="info" className="flex items-center gap-1">
                  <Clock className="h-3 w-3" />
                  Live updates
                </Badge>
              </div>
            </div>
          </CardHeader>
          <CardContent>
            <PriceLineChart
              data={chartData}
              loading={historyLoading}
              timeRange={timeRange}
              onTimeRangeChange={setTimeRange}
              showForecast
              highlightOptimal
              height={400}
            />
          </CardContent>
        </Card>

        {/* Optimal periods and forecast */}
        <div className="mt-6 grid gap-6 lg:grid-cols-2">
          {/* Optimal Periods */}
          <Card>
            <CardHeader>
              <CardTitle className="flex items-center gap-2">
                <Clock className="h-5 w-5 text-success-600" />
                Optimal Time Periods
              </CardTitle>
            </CardHeader>
            <CardContent>
              {optimalData?.periods?.length ? (
                <div className="space-y-4">
                  {optimalData.periods.slice(0, 5).map((period, i) => (
                    <div
                      key={i}
                      className="flex items-center justify-between rounded-lg bg-success-50 p-4"
                    >
                      <div>
                        <p className="font-medium text-gray-900">
                          {formatTime(period.start)} - {formatTime(period.end)}
                        </p>
                        <p className="text-sm text-gray-500">
                          Avg: {formatCurrency(period.avgPrice)}/kWh
                        </p>
                      </div>
                      <Badge variant="success">Best Time</Badge>
                    </div>
                  ))}
                </div>
              ) : (
                <div className="flex h-48 items-center justify-center text-gray-500">
                  No optimal periods found
                </div>
              )}
            </CardContent>
          </Card>

          {/* Price Alerts */}
          <Card>
            <CardHeader>
              <CardTitle className="flex items-center gap-2">
                <Bell className="h-5 w-5 text-primary-600" />
                Price Alerts
              </CardTitle>
            </CardHeader>
            <CardContent>
              <div className="space-y-4">
                <div className="flex items-center justify-between rounded-lg border border-gray-200 p-4">
                  <div className="flex items-center gap-3">
                    <AlertCircle className="h-5 w-5 text-warning-500" />
                    <div>
                      <p className="font-medium text-gray-900">
                        Price below 20p
                      </p>
                      <p className="text-sm text-gray-500">
                        Get notified when prices drop
                      </p>
                    </div>
                  </div>
                  <Button variant="outline" size="sm">
                    Set Alert
                  </Button>
                </div>

                <div className="flex items-center justify-between rounded-lg border border-gray-200 p-4">
                  <div className="flex items-center gap-3">
                    <AlertCircle className="h-5 w-5 text-danger-500" />
                    <div>
                      <p className="font-medium text-gray-900">
                        Price above 30p
                      </p>
                      <p className="text-sm text-gray-500">
                        Get warned about peak prices
                      </p>
                    </div>
                  </div>
                  <Button variant="outline" size="sm">
                    Set Alert
                  </Button>
                </div>

                <div className="text-center text-sm text-gray-500">
                  Configure more alerts in Settings
                </div>
              </div>
            </CardContent>
          </Card>
        </div>

        {/* 48-hour Forecast */}
        <Card className="mt-6">
          <CardHeader>
            <CardTitle className="flex items-center gap-2">
              <Calendar className="h-5 w-5 text-warning-600" />
              48-Hour Forecast
            </CardTitle>
          </CardHeader>
          <CardContent>
            {forecastLoading ? (
              <Skeleton variant="rectangular" height={300} />
            ) : forecastData?.forecast ? (
              <ForecastChart
                forecast={forecastData.forecast}
                currentPrice={currentPrice?.price}
                showConfidence
                height={300}
              />
            ) : (
              <div className="flex h-64 items-center justify-center text-gray-500">
                Forecast unavailable
              </div>
            )}
          </CardContent>
        </Card>
      </div>
    </div>
  )
}
