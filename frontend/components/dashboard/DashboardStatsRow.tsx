import React from 'react'
import Link from 'next/link'
import { Card, CardContent } from '@/components/ui/card'
import { Badge } from '@/components/ui/badge'
import { formatCurrency } from '@/lib/utils/format'
import { cn } from '@/lib/utils/cn'
import { Zap, Clock, ArrowRight } from 'lucide-react'
import type { DashboardStatsRowProps } from './DashboardTypes'

/**
 * Renders the top row of four dashboard stat cards:
 * Current Price, Total Saved, Optimal Times, and Suppliers.
 */
export const DashboardStatsRow = React.memo(function DashboardStatsRow({
  currentPrice,
  trend,
  TrendIcon,
  savingsData,
  optimalWindow,
  forecastLoading,
  suppliersCount,
  currentSupplier,
  topSuppliers,
}: DashboardStatsRowProps) {
  return (
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
            {currentSupplier && topSuppliers.some(s => s.estimatedAnnualCost < currentSupplier.estimatedAnnualCost) ? (
              <Badge variant="success">Cheaper available</Badge>
            ) : null}
          </div>
          <p className="mt-2 text-lg font-semibold text-gray-900">
            {suppliersCount} options
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
  )
})
