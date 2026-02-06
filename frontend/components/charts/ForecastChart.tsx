'use client'

import React, { useMemo } from 'react'
import {
  AreaChart,
  Area,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  ResponsiveContainer,
  ReferenceLine,
} from 'recharts'
import { format, parseISO, addHours } from 'date-fns'
import { cn } from '@/lib/utils/cn'
import { formatCurrency } from '@/lib/utils/format'
import type { PriceForecast } from '@/types'

export interface ForecastChartProps {
  forecast: PriceForecast[]
  showConfidence?: boolean
  currentPrice?: number
  height?: number
  className?: string
}

export const ForecastChart: React.FC<ForecastChartProps> = ({
  forecast,
  showConfidence = true,
  currentPrice,
  height = 250,
  className,
}) => {
  const chartData = useMemo(() => {
    const now = new Date()
    return forecast.map((point) => ({
      ...point,
      time: addHours(now, point.hour).toISOString(),
      formattedTime: format(addHours(now, point.hour), 'HH:mm'),
      confidenceLow: point.confidence[0],
      confidenceHigh: point.confidence[1],
    }))
  }, [forecast])

  // Calculate average forecast price
  const avgForecast = useMemo(() => {
    if (forecast.length === 0) return 0
    return forecast.reduce((sum, f) => sum + f.price, 0) / forecast.length
  }, [forecast])

  // Find lowest price period
  const lowestPricePeriod = useMemo(() => {
    if (forecast.length === 0) return null
    const lowest = forecast.reduce((min, f) => (f.price < min.price ? f : min))
    return lowest
  }, [forecast])

  if (forecast.length === 0) {
    return (
      <div
        className={cn(
          'flex h-48 items-center justify-center rounded-lg border-2 border-dashed border-gray-300 bg-gray-50',
          className
        )}
      >
        <p className="text-gray-500">No forecast data available</p>
      </div>
    )
  }

  return (
    <div className={cn('', className)}>
      {/* Header */}
      <div className="mb-4 flex items-center justify-between">
        <h3 className="font-semibold text-gray-900">24-Hour Forecast</h3>
        {lowestPricePeriod && (
          <div className="text-sm">
            Lowest at{' '}
            <span className="font-medium text-success-600">
              {format(
                addHours(new Date(), lowestPricePeriod.hour),
                'HH:mm'
              )}
            </span>
            {' - '}
            {formatCurrency(lowestPricePeriod.price)}
          </div>
        )}
      </div>

      {/* Chart */}
      <div style={{ height }}>
        <ResponsiveContainer width="100%" height="100%">
          <AreaChart
            data={chartData}
            margin={{ top: 10, right: 30, left: 0, bottom: 0 }}
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
              contentStyle={{
                backgroundColor: 'white',
                border: '1px solid #e5e7eb',
                borderRadius: '8px',
              }}
              formatter={(value: number, name: string) => {
                if (name === 'price') return [formatCurrency(value), 'Forecast']
                if (name === 'confidenceHigh') return [formatCurrency(value), 'Upper bound']
                return [formatCurrency(value), 'Lower bound']
              }}
            />

            {/* Confidence interval */}
            {showConfidence && (
              <>
                <Area
                  type="monotone"
                  dataKey="confidenceHigh"
                  stackId="confidence"
                  stroke="none"
                  fill="#fbbf24"
                  fillOpacity={0.2}
                />
                <Area
                  type="monotone"
                  dataKey="confidenceLow"
                  stackId="confidence"
                  stroke="none"
                  fill="#ffffff"
                  fillOpacity={1}
                />
              </>
            )}

            {/* Forecast line */}
            <Area
              type="monotone"
              dataKey="price"
              stroke="#f59e0b"
              strokeWidth={2}
              fill="#fbbf24"
              fillOpacity={0.3}
            />

            {/* Current price reference */}
            {currentPrice && (
              <ReferenceLine
                y={currentPrice}
                stroke="#3b82f6"
                strokeDasharray="5 5"
                label={{
                  value: `Current: ${formatCurrency(currentPrice)}`,
                  position: 'left',
                  fill: '#3b82f6',
                  fontSize: 12,
                }}
              />
            )}

            {/* Average line */}
            <ReferenceLine
              y={avgForecast}
              stroke="#6b7280"
              strokeDasharray="3 3"
            />
          </AreaChart>
        </ResponsiveContainer>
      </div>

      {/* Legend */}
      <div className="mt-2 flex items-center justify-center gap-6 text-sm text-gray-600">
        <div className="flex items-center gap-2">
          <div className="h-0.5 w-4 bg-warning-500" />
          <span>Forecast</span>
        </div>
        {showConfidence && (
          <div className="flex items-center gap-2">
            <div className="h-3 w-4 bg-warning-200 opacity-50" />
            <span>Confidence interval</span>
          </div>
        )}
        {currentPrice && (
          <div className="flex items-center gap-2">
            <div className="h-0.5 w-4 border-t-2 border-dashed border-primary-500" />
            <span>Current price</span>
          </div>
        )}
      </div>
    </div>
  )
}
