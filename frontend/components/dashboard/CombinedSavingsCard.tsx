'use client'

import React from 'react'
import { Skeleton } from '@/components/ui/skeleton'
import { useCombinedSavings } from '@/lib/hooks/useCombinedSavings'

const UTILITY_COLORS: Record<string, string> = {
  electricity: 'bg-yellow-400',
  natural_gas: 'bg-blue-400',
  heating_oil: 'bg-orange-400',
  propane: 'bg-red-400',
  community_solar: 'bg-green-400',
  water: 'bg-cyan-400',
}

export function CombinedSavingsCard() {
  const { data, isLoading, error } = useCombinedSavings()

  if (isLoading) {
    return (
      <div data-testid="combined-savings-loading" className="rounded-xl border bg-white p-6">
        <Skeleton variant="text" width={180} />
        <Skeleton variant="rectangular" height={32} className="mt-3" />
        <Skeleton variant="text" width={120} className="mt-2" />
      </div>
    )
  }

  if (error || !data) {
    return (
      <div data-testid="combined-savings-error" className="rounded-xl border bg-white p-6 text-gray-500">
        Unable to load combined savings.
      </div>
    )
  }

  const total = Number(data.total_monthly_savings)
  const maxSavings = Math.max(...data.breakdown.map((b) => Number(b.monthly_savings)), 1)

  return (
    <div data-testid="combined-savings-card" className="rounded-xl border bg-white p-6">
      <h3 className="text-sm font-medium text-gray-500">Combined Monthly Savings</h3>
      <p className="mt-1 text-3xl font-bold text-gray-900">
        ${total.toFixed(2)}
      </p>

      {/* Stacked bar */}
      <div className="mt-4 flex h-3 rounded-full overflow-hidden bg-gray-100" data-testid="savings-bar">
        {data.breakdown.map((b) => {
          const pct = maxSavings > 0 ? (Number(b.monthly_savings) / total) * 100 : 0
          return (
            <div
              key={b.utility_type}
              className={`${UTILITY_COLORS[b.utility_type] || 'bg-gray-400'}`}
              style={{ width: `${pct}%` }}
              title={`${b.utility_type}: $${Number(b.monthly_savings).toFixed(2)}`}
            />
          )
        })}
      </div>

      {/* Breakdown labels */}
      <div className="mt-3 flex flex-wrap gap-3 text-xs text-gray-600">
        {data.breakdown.map((b) => (
          <span key={b.utility_type} className="flex items-center gap-1">
            <span className={`inline-block h-2 w-2 rounded-full ${UTILITY_COLORS[b.utility_type] || 'bg-gray-400'}`} />
            {b.utility_type.replace('_', ' ')}: ${Number(b.monthly_savings).toFixed(2)}
          </span>
        ))}
      </div>

      {/* Percentile badge */}
      {data.savings_rank_pct != null && (
        <p className="mt-3 text-xs text-gray-500" data-testid="savings-percentile">
          Top {Math.round((1 - data.savings_rank_pct) * 100)}% of savers
        </p>
      )}
    </div>
  )
}
