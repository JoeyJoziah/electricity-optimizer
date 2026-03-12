'use client'

import type { RateChange } from '@/lib/api/rate-changes'

const UTILITY_LABELS: Record<string, string> = {
  electricity: 'Electricity',
  natural_gas: 'Natural Gas',
  heating_oil: 'Heating Oil',
  propane: 'Propane',
  community_solar: 'Community Solar',
}

const UNIT_LABELS: Record<string, string> = {
  electricity: '/kWh',
  natural_gas: '/therm',
  heating_oil: '/gal',
  propane: '/gal',
  community_solar: '/kWh',
}

interface RateChangeCardProps {
  change: RateChange
}

export function RateChangeCard({ change }: RateChangeCardProps) {
  const isIncrease = change.change_direction === 'increase'
  const utilityLabel = UTILITY_LABELS[change.utility_type] ?? change.utility_type
  const unit = UNIT_LABELS[change.utility_type] ?? ''

  return (
    <div className="rounded-lg border p-4" data-testid="rate-change-card">
      <div className="flex items-start justify-between">
        <div>
          <p className="text-sm text-muted-foreground">{utilityLabel}</p>
          <p className="font-semibold">{change.region} &mdash; {change.supplier}</p>
        </div>
        <span
          className={`inline-flex items-center rounded-full px-2 py-1 text-xs font-medium ${
            isIncrease
              ? 'bg-red-100 text-red-700'
              : 'bg-green-100 text-green-700'
          }`}
        >
          {isIncrease ? '\u2191' : '\u2193'} {Math.abs(change.change_pct).toFixed(1)}%
        </span>
      </div>

      <div className="mt-3 flex gap-4 text-sm">
        <div>
          <span className="text-muted-foreground">Previous:</span>{' '}
          ${change.previous_price.toFixed(4)}{unit}
        </div>
        <div>
          <span className="text-muted-foreground">Current:</span>{' '}
          ${change.current_price.toFixed(4)}{unit}
        </div>
      </div>

      {change.recommendation_supplier && (
        <div className="mt-3 rounded bg-blue-50 p-2 text-sm">
          <p className="font-medium text-blue-800">
            Switch to {change.recommendation_supplier}
          </p>
          <p className="text-blue-600">
            ${change.recommendation_price?.toFixed(4)}{unit} &mdash; save $
            {change.recommendation_savings?.toFixed(4)}{unit}
          </p>
        </div>
      )}

      <p className="mt-2 text-xs text-muted-foreground">
        Detected {new Date(change.detected_at).toLocaleDateString()}
      </p>
    </div>
  )
}
