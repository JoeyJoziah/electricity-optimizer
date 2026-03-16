'use client'

import React from 'react'
import { Skeleton } from '@/components/ui/skeleton'
import { useNeighborhoodComparison } from '@/lib/hooks/useNeighborhood'
import { useSettingsStore } from '@/lib/store/settings'

export function NeighborhoodCard() {
  const region = useSettingsStore((s) => s.region)
  const { data, isLoading, error } = useNeighborhoodComparison(region, 'electricity')

  if (isLoading) {
    return (
      <div data-testid="neighborhood-loading" className="rounded-xl border bg-white p-6">
        <Skeleton variant="text" width={200} />
        <Skeleton variant="rectangular" height={48} className="mt-3" />
      </div>
    )
  }

  if (error || !data) {
    return (
      <div data-testid="neighborhood-error" className="rounded-xl border bg-white p-6 text-gray-500">
        Unable to load neighborhood comparison.
      </div>
    )
  }

  // Insufficient data
  if (data.percentile == null || data.user_rate == null) {
    return (
      <div data-testid="neighborhood-insufficient" className="rounded-xl border bg-white p-6">
        <h3 className="text-sm font-medium text-gray-500">Neighborhood Comparison</h3>
        <p className="mt-2 text-sm text-gray-400">
          We need a few more neighbors to build a comparison. Check back soon!
        </p>
      </div>
    )
  }

  const userRate = Number(data.user_rate)
  const avgRate = Number(data.avg_rate)
  const maxRate = Math.max(userRate, avgRate) * 1.1

  return (
    <div data-testid="neighborhood-card" className="rounded-xl border bg-white p-6">
      <h3 className="text-sm font-medium text-gray-500">Neighborhood Comparison</h3>

      {/* Rate context */}
      <p className="mt-2 text-sm text-gray-700" data-testid="neighborhood-context">
        You pay ${userRate.toFixed(4)}/kWh vs. state average ${avgRate.toFixed(4)}/kWh
      </p>

      {/* Simple bar chart */}
      <div className="mt-4 space-y-2" data-testid="neighborhood-bars">
        <div>
          <div className="flex justify-between text-xs text-gray-500 mb-1">
            <span>Your rate</span>
            <span>${userRate.toFixed(4)}</span>
          </div>
          <div className="h-4 rounded bg-gray-100">
            <div
              className="h-4 rounded bg-primary-500 origin-left transition-transform duration-300"
              style={{ transform: `scaleX(${userRate / maxRate})` }}
            />
          </div>
        </div>
        <div>
          <div className="flex justify-between text-xs text-gray-500 mb-1">
            <span>State average</span>
            <span>${avgRate.toFixed(4)}</span>
          </div>
          <div className="h-4 rounded bg-gray-100">
            <div
              className="h-4 rounded bg-gray-400 origin-left transition-transform duration-300"
              style={{ transform: `scaleX(${avgRate / maxRate})` }}
            />
          </div>
        </div>
      </div>

      {/* Percentile */}
      <p className="mt-3 text-xs text-gray-500" data-testid="neighborhood-percentile">
        You pay less than {Math.round(data.percentile * 100)}% of users in your area
      </p>

      {/* Cheapest supplier */}
      {data.cheapest_supplier && data.potential_savings != null && Number(data.potential_savings) > 0 && (
        <p className="mt-1 text-xs text-green-600" data-testid="neighborhood-savings">
          Switch to {data.cheapest_supplier} to save ~${Number(data.potential_savings).toFixed(4)}/kWh
        </p>
      )}
    </div>
  )
}
