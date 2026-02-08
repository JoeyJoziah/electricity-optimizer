'use client'

import React, { useMemo } from 'react'
import {
  PieChart,
  Pie,
  Cell,
  ResponsiveContainer,
  Tooltip,
} from 'recharts'
import { cn } from '@/lib/utils/cn'
import { formatCurrency } from '@/lib/utils/format'

const tooltipStyle = {
  backgroundColor: 'white',
  border: '1px solid #e5e7eb',
  borderRadius: '8px',
}

export interface SavingsCategory {
  category: string
  amount: number
  percentage: number
}

export interface SavingsData {
  totalSavings: number
  breakdown: SavingsCategory[]
  period: 'day' | 'week' | 'month' | 'year'
}

export interface SavingsDonutProps {
  data: SavingsData
  showLegend?: boolean
  currency?: 'USD' | 'GBP' | 'EUR'
  className?: string
}

const COLORS = ['#3b82f6', '#22c55e', '#f59e0b', '#ef4444', '#8b5cf6', '#06b6d4']

const periodLabels: Record<SavingsData['period'], string> = {
  day: 'Today',
  week: 'This week',
  month: 'This month',
  year: 'This year',
}

export const SavingsDonut: React.FC<SavingsDonutProps> = React.memo(({
  data,
  showLegend = false,
  currency = 'USD',
  className,
}) => {
  const { totalSavings, breakdown, period } = data

  const chartData = useMemo(() => {
    return breakdown.map((item, index) => ({
      ...item,
      color: COLORS[index % COLORS.length],
    }))
  }, [breakdown])

  // Empty state
  if (totalSavings === 0 || breakdown.length === 0) {
    return (
      <div
        className={cn('flex flex-col items-center justify-center py-8', className)}
        role="img"
        aria-label="Savings chart - no savings yet"
      >
        <div className="mb-2 h-32 w-32 rounded-full border-4 border-dashed border-gray-200" />
        <p className="text-gray-500">No savings yet</p>
        <p className="text-sm text-gray-400">{periodLabels[period]}</p>
      </div>
    )
  }

  return (
    <div className={cn('flex flex-col', className)}>
      <div
        role="img"
        aria-label={`Savings chart showing ${formatCurrency(totalSavings, currency)} total savings ${periodLabels[period].toLowerCase()}`}
        className="relative"
      >
        <ResponsiveContainer width="100%" height={200}>
          <PieChart>
            <Pie
              data={chartData}
              cx="50%"
              cy="50%"
              innerRadius={60}
              outerRadius={80}
              paddingAngle={2}
              dataKey="amount"
            >
              {chartData.map((entry, index) => (
                <Cell key={entry.category} fill={entry.color} />
              ))}
            </Pie>
            <Tooltip
              formatter={(value: number) => formatCurrency(value, currency)}
              contentStyle={tooltipStyle}
            />
          </PieChart>
        </ResponsiveContainer>

        {/* Center text */}
        <div className="absolute inset-0 flex flex-col items-center justify-center">
          <span className="text-2xl font-bold text-gray-900">
            {formatCurrency(totalSavings, currency)}
          </span>
          <span className="text-sm text-gray-500">{periodLabels[period]}</span>
        </div>
      </div>

      {/* Legend */}
      {showLegend && (
        <div className="mt-4 space-y-2">
          {chartData.map((item) => (
            <div
              key={item.category}
              data-testid="legend-item"
              className="flex items-center justify-between"
            >
              <div className="flex items-center gap-2">
                <div
                  className="h-3 w-3 rounded-full"
                  style={{ backgroundColor: item.color }}
                />
                <span className="text-sm text-gray-700">{item.category}</span>
              </div>
              <div className="flex items-center gap-2">
                <span className="text-sm font-medium text-gray-900">
                  {formatCurrency(item.amount, currency)}
                </span>
                <span className="text-xs text-gray-500">
                  ({item.percentage.toFixed(2)}%)
                </span>
              </div>
            </div>
          ))}
        </div>
      )}
    </div>
  )
})

SavingsDonut.displayName = 'SavingsDonut'
