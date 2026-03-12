'use client'

import { usePropaneHistory } from '@/lib/hooks/usePropane'

interface PropanePriceHistoryProps {
  state: string
}

export function PropanePriceHistory({ state }: PropanePriceHistoryProps) {
  const { data, isLoading, error } = usePropaneHistory(state, 12)

  if (isLoading) {
    return <div className="animate-pulse rounded-lg bg-gray-100 h-48" />
  }

  if (error || !data) return null

  const { history, comparison } = data

  return (
    <div className="rounded-lg border p-4">
      <h3 className="text-sm font-semibold text-gray-900">
        Price History &mdash; {state}
      </h3>

      {comparison && (
        <div className="mt-2 grid grid-cols-2 gap-4 text-sm">
          <div>
            <p className="text-gray-500">Current Price</p>
            <p className="text-lg font-bold">${comparison.price_per_gallon.toFixed(2)}/gal</p>
          </div>
          {comparison.national_avg && (
            <div>
              <p className="text-gray-500">vs National Avg</p>
              <p className={`text-lg font-bold ${
                comparison.difference_pct !== null && comparison.difference_pct < 0
                  ? 'text-green-600'
                  : 'text-red-600'
              }`}>
                {comparison.difference_pct !== null
                  ? `${comparison.difference_pct > 0 ? '+' : ''}${comparison.difference_pct}%`
                  : 'N/A'}
              </p>
            </div>
          )}
          <div>
            <p className="text-gray-500">Est. Monthly Cost</p>
            <p className="font-semibold">${comparison.estimated_monthly_cost.toFixed(0)}</p>
          </div>
          <div>
            <p className="text-gray-500">Est. Annual Cost</p>
            <p className="font-semibold">${comparison.estimated_annual_cost.toFixed(0)}</p>
          </div>
        </div>
      )}

      {history.length > 0 && (
        <div className="mt-4">
          <p className="text-xs font-medium text-gray-500 mb-2">Recent Weeks</p>
          <div className="space-y-1">
            {history.slice(0, 8).map((h) => (
              <div
                key={h.id}
                className="flex items-center justify-between text-sm text-gray-700"
              >
                <span>{h.period_date || 'Unknown'}</span>
                <span className="font-medium">${h.price_per_gallon.toFixed(2)}/gal</span>
              </div>
            ))}
          </div>
        </div>
      )}
    </div>
  )
}
