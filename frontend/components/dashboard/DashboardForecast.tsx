import React from 'react'
import Link from 'next/link'
import { Card, CardHeader, CardTitle, CardContent } from '@/components/ui/card'
import { Button } from '@/components/ui/button'
import { Skeleton, ChartSkeleton } from '@/components/ui/skeleton'
import { SupplierCard } from '@/components/suppliers/SupplierCard'
import { TrendingUp, ArrowRight } from 'lucide-react'
import { ApiClientError } from '@/lib/api/client'
import dynamic from 'next/dynamic'
import type { RawForecastPriceEntry } from '@/types'
import type { DashboardForecastProps } from './DashboardTypes'

const ForecastChart = dynamic(
  () => import('@/components/charts/ForecastChart').then((m) => m.ForecastChart),
  { ssr: false, loading: () => <ChartSkeleton /> }
)

/**
 * Renders the second content row: 24-Hour Forecast chart (2-column)
 * and Top Suppliers sidebar (1-column).
 */
export function DashboardForecast({
  forecastData,
  forecastLoading,
  forecastError,
  currentPrice,
  topSuppliers,
  currentSupplier,
}: DashboardForecastProps) {
  // Safely access nested forecast shape
  const forecastObj = (forecastData as { forecast?: unknown })?.forecast

  // Determine if the error is a 403 tier-gating response
  const isTierGated =
    forecastError instanceof ApiClientError && forecastError.status === 403

  return (
    <div className="mt-6 grid gap-6 lg:grid-cols-3">
      {/* 24-hour forecast */}
      <Card className="lg:col-span-2">
        <CardHeader>
          <CardTitle>24-Hour Forecast</CardTitle>
        </CardHeader>
        <CardContent>
          {forecastLoading ? (
            <Skeleton variant="rectangular" height={250} />
          ) : forecastObj ? (
            <ForecastChart
              forecast={
                Array.isArray(forecastObj)
                  ? forecastObj
                  : ((forecastObj as { prices?: RawForecastPriceEntry[] }).prices || []).map((p: RawForecastPriceEntry, i: number) => ({
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
          ) : isTierGated ? (
            <div
              className="flex h-64 flex-col items-center justify-center rounded-lg border border-primary-200 bg-primary-50 px-6 text-center"
              data-testid="forecast-upgrade-cta"
            >
              <div className="mb-3 flex h-12 w-12 items-center justify-center rounded-full bg-primary-100">
                <TrendingUp className="h-6 w-6 text-primary-600" />
              </div>
              <h4 className="text-lg font-semibold text-primary-900">
                Unlock ML-Powered Forecasts
              </h4>
              <p className="mt-1 max-w-sm text-sm text-primary-700">
                Upgrade to Pro to see 24-hour price predictions and save more on your electricity bill.
              </p>
              <Link href="/pricing" className="mt-4">
                <Button variant="primary" size="sm">
                  Upgrade to Pro
                  <ArrowRight className="ml-1 h-4 w-4" />
                </Button>
              </Link>
            </div>
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
  )
}
