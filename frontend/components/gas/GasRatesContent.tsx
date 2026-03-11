'use client'

import React from 'react'
import { Header } from '@/components/layout/Header'
import { Card, CardHeader, CardTitle, CardContent } from '@/components/ui/card'
import { Badge } from '@/components/ui/badge'
import { Skeleton } from '@/components/ui/skeleton'
import { useGasRates, useGasHistory, useGasStats, useGasSupplierComparison } from '@/lib/hooks/useGasRates'
import { useSettingsStore } from '@/lib/store/settings'
import { formatCurrency, formatDateTime } from '@/lib/utils/format'
import {
  Flame,
  TrendingDown,
  TrendingUp,
  Minus,
  Building2,
  BarChart3,
} from 'lucide-react'

export default function GasRatesContent() {
  const region = useSettingsStore((s) => s.region)

  const { data: ratesData, isLoading: ratesLoading } = useGasRates(region)
  const { data: statsData, isLoading: statsLoading } = useGasStats(region, 30)
  const { data: historyData, isLoading: historyLoading } = useGasHistory(region, 90)
  const { data: compareData, isLoading: compareLoading } = useGasSupplierComparison(
    ratesData?.is_deregulated ? region : null
  )

  const latestPrice = ratesData?.prices?.[0]
  const priceNum = latestPrice ? parseFloat(latestPrice.price) : null

  // Derive trend from stats
  const avgPrice = statsData?.avg_price ? parseFloat(statsData.avg_price) : null
  const trend: 'increasing' | 'decreasing' | 'stable' =
    priceNum != null && avgPrice != null
      ? priceNum > avgPrice * 1.02
        ? 'increasing'
        : priceNum < avgPrice * 0.98
          ? 'decreasing'
          : 'stable'
      : 'stable'
  const TrendIcon = trend === 'increasing' ? TrendingUp : trend === 'decreasing' ? TrendingDown : Minus

  if (!region) {
    return (
      <div className="flex flex-col">
        <Header title="Natural Gas Rates" />
        <div className="flex h-96 items-center justify-center">
          <div className="text-center">
            <Flame className="mx-auto h-12 w-12 text-gray-300" />
            <p className="mt-4 text-lg font-medium text-gray-900">No region set</p>
            <p className="mt-1 text-gray-500">
              Set your region in Settings to view natural gas rates.
            </p>
          </div>
        </div>
      </div>
    )
  }

  return (
    <div className="flex flex-col">
      <Header title="Natural Gas Rates" />

      <div className="p-6">
        {/* Deregulation badge */}
        {ratesData && (
          <div className="mb-4">
            <Badge variant={ratesData.is_deregulated ? 'success' : 'default'}>
              {ratesData.is_deregulated
                ? 'Deregulated market — you can choose your supplier'
                : 'Regulated market — rates set by your utility'}
            </Badge>
          </div>
        )}

        {/* Stats row */}
        <div className="grid gap-6 md:grid-cols-2 lg:grid-cols-4">
          {/* Current Rate */}
          <Card>
            <CardContent className="p-4">
              <div className="flex items-center gap-2">
                <Flame className="h-4 w-4 text-orange-500" />
                <p className="text-sm font-medium text-gray-500">Current Rate</p>
              </div>
              {ratesLoading ? (
                <Skeleton variant="text" className="mt-2 h-8 w-24" />
              ) : (
                <>
                  <div className="mt-2 flex items-baseline gap-2">
                    <p className="text-3xl font-bold text-gray-900">
                      {priceNum != null ? formatCurrency(priceNum) : '--'}
                    </p>
                    <span className="text-gray-500">
                      /{ratesData?.unit || 'therm'}
                    </span>
                  </div>
                  <div className="mt-2 flex items-center gap-1 text-sm text-gray-500">
                    <TrendIcon className="h-4 w-4" />
                    <span className="capitalize">{trend}</span>
                    {latestPrice && (
                      <span className="text-gray-400">
                        via {latestPrice.source}
                      </span>
                    )}
                  </div>
                </>
              )}
            </CardContent>
          </Card>

          {/* 30-Day Average */}
          <Card>
            <CardContent className="p-4">
              <p className="text-sm font-medium text-gray-500">30-Day Average</p>
              {statsLoading ? (
                <Skeleton variant="text" className="mt-2 h-8 w-24" />
              ) : (
                <>
                  <p className="mt-2 text-3xl font-bold text-gray-900">
                    {avgPrice != null ? formatCurrency(avgPrice) : '--'}
                  </p>
                  <p className="mt-1 text-sm text-gray-500">
                    /{statsData?.unit || 'therm'}
                  </p>
                </>
              )}
            </CardContent>
          </Card>

          {/* 30-Day Low */}
          <Card>
            <CardContent className="p-4">
              <p className="text-sm font-medium text-gray-500">30-Day Low</p>
              {statsLoading ? (
                <Skeleton variant="text" className="mt-2 h-8 w-24" />
              ) : (
                <>
                  <p className="mt-2 text-3xl font-bold text-success-600">
                    {statsData?.min_price ? formatCurrency(parseFloat(statsData.min_price)) : '--'}
                  </p>
                  <p className="mt-1 text-sm text-gray-500">
                    /{statsData?.unit || 'therm'}
                  </p>
                </>
              )}
            </CardContent>
          </Card>

          {/* 30-Day High */}
          <Card>
            <CardContent className="p-4">
              <p className="text-sm font-medium text-gray-500">30-Day High</p>
              {statsLoading ? (
                <Skeleton variant="text" className="mt-2 h-8 w-24" />
              ) : (
                <>
                  <p className="mt-2 text-3xl font-bold text-danger-600">
                    {statsData?.max_price ? formatCurrency(parseFloat(statsData.max_price)) : '--'}
                  </p>
                  <p className="mt-1 text-sm text-gray-500">
                    /{statsData?.unit || 'therm'}
                  </p>
                </>
              )}
            </CardContent>
          </Card>
        </div>

        {/* Price history */}
        <Card className="mt-6">
          <CardHeader>
            <CardTitle className="flex items-center gap-2">
              <BarChart3 className="h-5 w-5 text-orange-500" />
              Price History (90 days)
            </CardTitle>
          </CardHeader>
          <CardContent>
            {historyLoading ? (
              <Skeleton variant="rectangular" height={200} />
            ) : historyData?.prices?.length ? (
              <div className="space-y-2">
                {historyData.prices.slice(0, 20).map((p, i) => (
                  <div
                    key={i}
                    className="flex items-center justify-between rounded-lg border border-gray-100 px-4 py-2"
                  >
                    <div>
                      <p className="text-sm font-medium text-gray-900">
                        {formatCurrency(parseFloat(p.price))}/therm
                      </p>
                      <p className="text-xs text-gray-500">{p.supplier}</p>
                    </div>
                    <p className="text-xs text-gray-400">
                      {formatDateTime(p.timestamp, 'dd MMM yyyy')}
                    </p>
                  </div>
                ))}
                {historyData.count > 20 && (
                  <p className="pt-2 text-center text-sm text-gray-500">
                    Showing 20 of {historyData.count} records
                  </p>
                )}
              </div>
            ) : (
              <div className="flex h-48 items-center justify-center text-gray-500">
                No price history available yet. Rates are fetched weekly from EIA.
              </div>
            )}
          </CardContent>
        </Card>

        {/* Supplier comparison (deregulated states only) */}
        {ratesData?.is_deregulated && (
          <Card className="mt-6">
            <CardHeader>
              <CardTitle className="flex items-center gap-2">
                <Building2 className="h-5 w-5 text-primary-600" />
                Supplier Comparison
              </CardTitle>
            </CardHeader>
            <CardContent>
              {compareLoading ? (
                <Skeleton variant="rectangular" height={200} />
              ) : compareData?.suppliers?.length ? (
                <div className="space-y-3">
                  {compareData.suppliers.map((s, i) => (
                    <div
                      key={s.supplier}
                      className="flex items-center justify-between rounded-lg border border-gray-200 p-4"
                    >
                      <div className="flex items-center gap-3">
                        <span className="flex h-8 w-8 items-center justify-center rounded-full bg-gray-100 text-sm font-bold text-gray-600">
                          {i + 1}
                        </span>
                        <div>
                          <p className="font-medium text-gray-900">{s.supplier}</p>
                          <p className="text-xs text-gray-500">
                            Updated {formatDateTime(s.timestamp, 'dd MMM yyyy')}
                          </p>
                        </div>
                      </div>
                      <div className="text-right">
                        <p className="text-lg font-bold text-gray-900">
                          {formatCurrency(parseFloat(s.price))}
                        </p>
                        <p className="text-xs text-gray-500">per therm</p>
                        {i === 0 && (
                          <Badge variant="success" className="mt-1">Cheapest</Badge>
                        )}
                      </div>
                    </div>
                  ))}
                </div>
              ) : (
                <div className="flex h-48 items-center justify-center text-gray-500">
                  {compareData?.message || 'No supplier data available yet.'}
                </div>
              )}
            </CardContent>
          </Card>
        )}
      </div>
    </div>
  )
}
