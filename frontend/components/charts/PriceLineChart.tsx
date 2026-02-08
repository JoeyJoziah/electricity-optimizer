'use client'

import React, { useMemo, useCallback } from 'react'
import {
  LineChart,
  Line,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  Legend,
  ResponsiveContainer,
  ReferenceLine,
  ReferenceArea,
} from 'recharts'
import { format, parseISO } from 'date-fns'
import { cn } from '@/lib/utils/cn'
import { formatCurrency } from '@/lib/utils/format'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Skeleton } from '@/components/ui/skeleton'
import { TrendingUp, TrendingDown, Minus } from 'lucide-react'
import type { PriceDataPoint, TimeRange } from '@/types'

const tooltipStyle = {
  backgroundColor: 'white',
  border: '1px solid #e5e7eb',
  borderRadius: '8px',
  boxShadow: '0 4px 6px -1px rgb(0 0 0 / 0.1)',
}

export interface PriceLineChartProps {
  data: PriceDataPoint[]
  showForecast?: boolean
  highlightOptimal?: boolean
  loading?: boolean
  timeRange?: TimeRange
  onTimeRangeChange?: (range: TimeRange) => void
  showCurrentPrice?: boolean
  showTrend?: boolean
  height?: number
  className?: string
}

const TIME_RANGES: TimeRange[] = ['6h', '12h', '24h', '48h', '7d']

export const PriceLineChart: React.FC<PriceLineChartProps> = React.memo(({
  data,
  showForecast = false,
  highlightOptimal = false,
  loading = false,
  timeRange = '24h',
  onTimeRangeChange,
  showCurrentPrice = false,
  showTrend = false,
  height = 300,
  className,
}) => {
  // Process data for the chart
  const chartData = useMemo(() => {
    return data.map((point) => ({
      ...point,
      time: point.time,
      formattedTime: format(parseISO(point.time), 'HH:mm'),
      displayPrice: point.price ?? point.forecast,
    }))
  }, [data])

  // Calculate current price and trend
  const { currentPrice, trend, changePercent } = useMemo(() => {
    const actualPrices = data.filter((d) => d.price !== null)
    if (actualPrices.length === 0) {
      return { currentPrice: null, trend: 'stable' as const, changePercent: 0 }
    }

    const latest = actualPrices[actualPrices.length - 1].price!
    const previous =
      actualPrices.length > 1
        ? actualPrices[actualPrices.length - 2].price!
        : latest

    const change = ((latest - previous) / previous) * 100

    let trendDirection: 'increasing' | 'decreasing' | 'stable' = 'stable'
    if (change > 1) trendDirection = 'increasing'
    else if (change < -1) trendDirection = 'decreasing'

    return {
      currentPrice: latest,
      trend: trendDirection,
      changePercent: change,
    }
  }, [data])

  // Find optimal periods
  const optimalPeriods = useMemo(() => {
    if (!highlightOptimal) return []

    return data
      .filter((d) => d.isOptimal)
      .reduce(
        (acc, d, i, arr) => {
          if (i === 0 || !arr[i - 1].isOptimal) {
            acc.push({ start: d.time, end: d.time })
          } else {
            acc[acc.length - 1].end = d.time
          }
          return acc
        },
        [] as { start: string; end: string }[]
      )
  }, [data, highlightOptimal])

  const handleTimeRangeChange = useCallback(
    (range: TimeRange) => {
      onTimeRangeChange?.(range)
    },
    [onTimeRangeChange]
  )

  // Loading state
  if (loading) {
    return (
      <div
        data-testid="price-chart-container"
        className={cn('w-full', className)}
      >
        <div className="mb-4 flex items-center justify-between">
          <Skeleton variant="text" className="h-6 w-32" />
          <Skeleton variant="text" className="h-8 w-48" />
        </div>
        <Skeleton variant="rectangular" height={height} className="w-full" />
        <p className="text-center text-gray-500 mt-4">Loading...</p>
      </div>
    )
  }

  // Empty state
  if (data.length === 0) {
    return (
      <div
        data-testid="price-chart-container"
        className={cn('w-full', className)}
        role="img"
        aria-label="Price chart - no data available"
      >
        <div className="flex h-64 items-center justify-center rounded-lg border-2 border-dashed border-gray-300 bg-gray-50">
          <p className="text-gray-500">No data available</p>
        </div>
      </div>
    )
  }

  const TrendIcon =
    trend === 'increasing'
      ? TrendingUp
      : trend === 'decreasing'
        ? TrendingDown
        : Minus

  const trendColor =
    trend === 'increasing'
      ? 'text-danger-500'
      : trend === 'decreasing'
        ? 'text-success-500'
        : 'text-gray-500'

  return (
    <div
      data-testid="price-chart-container"
      className={cn('w-full', className)}
    >
      {/* Header with current price and controls */}
      <div className="mb-4 flex flex-wrap items-center justify-between gap-4">
        <div className="flex items-center gap-4">
          {showCurrentPrice && currentPrice !== null && (
            <div data-testid="current-price" className="flex items-baseline gap-2">
              <span className="text-2xl font-bold text-gray-900">
                {formatCurrency(currentPrice)}
              </span>
              <span className="text-sm text-gray-500">/kWh</span>
            </div>
          )}

          {showTrend && (
            <div data-testid="price-trend" className={cn('flex items-center gap-1', trendColor)}>
              <TrendIcon className="h-5 w-5" />
              <span className="text-sm font-medium">
                {changePercent > 0 ? '+' : ''}
                {changePercent.toFixed(1)}%
              </span>
              <span className="text-sm text-gray-500">
                ({trend === 'increasing' ? 'increasing' : trend === 'decreasing' ? 'decreasing' : 'stable'})
              </span>
            </div>
          )}

          {highlightOptimal && optimalPeriods.length > 0 && (
            <Badge variant="success">Cheap periods available</Badge>
          )}
        </div>

        {/* Time range selector */}
        {onTimeRangeChange && (
          <div className="flex gap-1">
            {TIME_RANGES.map((range) => (
              <Button
                key={range}
                variant={timeRange === range ? 'primary' : 'ghost'}
                size="sm"
                onClick={() => handleTimeRangeChange(range)}
                aria-pressed={timeRange === range}
              >
                {range}
              </Button>
            ))}
          </div>
        )}
      </div>

      {/* Chart */}
      <div
        role="img"
        aria-label={`Price chart showing ${showForecast ? 'actual and forecast' : 'actual'} electricity prices over time`}
        style={{ height }}
      >
        <ResponsiveContainer width="100%" height="100%">
          <LineChart
            data={chartData}
            margin={{ top: 5, right: 30, left: 20, bottom: 5 }}
          >
            <CartesianGrid strokeDasharray="3 3" stroke="#e5e7eb" />
            <XAxis
              dataKey="formattedTime"
              stroke="#6b7280"
              fontSize={12}
              tickLine={false}
            />
            <YAxis
              stroke="#6b7280"
              fontSize={12}
              tickLine={false}
              tickFormatter={(value) => formatCurrency(value)}
            />
            <Tooltip
              contentStyle={tooltipStyle}
              formatter={(value: number, name: string) => [
                formatCurrency(value),
                name === 'price' ? 'Actual Price' : 'Forecast',
              ]}
              labelFormatter={(label) => `Time: ${label}`}
            />

            {/* Optimal period highlighting */}
            {highlightOptimal &&
              optimalPeriods.map((period, i) => (
                <ReferenceArea
                  key={i}
                  x1={format(parseISO(period.start), 'HH:mm')}
                  x2={format(parseISO(period.end), 'HH:mm')}
                  fill="#22c55e"
                  fillOpacity={0.1}
                />
              ))}

            {/* Price lines */}
            <Line
              type="monotone"
              dataKey="price"
              stroke="#3b82f6"
              strokeWidth={2}
              dot={false}
              name="price"
              connectNulls={false}
            />

            {showForecast && (
              <Line
                type="monotone"
                dataKey="forecast"
                stroke="#f59e0b"
                strokeWidth={2}
                strokeDasharray="5 5"
                dot={false}
                name="forecast"
                connectNulls={false}
              />
            )}

            {showForecast && (
              <Legend
                formatter={(value) =>
                  value === 'price' ? 'Actual Price' : 'Forecast'
                }
              />
            )}
          </LineChart>
        </ResponsiveContainer>
      </div>
    </div>
  )
})

PriceLineChart.displayName = 'PriceLineChart'
