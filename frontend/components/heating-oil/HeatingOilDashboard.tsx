'use client'

import { useState } from 'react'
import { useHeatingOilPrices } from '@/lib/hooks/useHeatingOil'
import { OilPriceHistory } from './OilPriceHistory'
import { DealerList } from './DealerList'

const STATE_NAMES: Record<string, string> = {
  CT: 'Connecticut',
  MA: 'Massachusetts',
  NY: 'New York',
  NJ: 'New Jersey',
  PA: 'Pennsylvania',
  ME: 'Maine',
  NH: 'New Hampshire',
  VT: 'Vermont',
  RI: 'Rhode Island',
}

export function HeatingOilDashboard() {
  const [selectedState, setSelectedState] = useState<string | undefined>()
  const { data, isLoading, error } = useHeatingOilPrices()

  if (isLoading) {
    return (
      <div className="space-y-4">
        {[1, 2, 3].map((i) => (
          <div key={i} className="animate-pulse rounded-lg bg-gray-100 h-16" />
        ))}
      </div>
    )
  }

  if (error) {
    return (
      <div className="rounded-lg border border-red-200 bg-red-50 p-4 text-sm text-red-700">
        Unable to load heating oil prices. Please try again later.
      </div>
    )
  }

  const prices = data?.prices || []
  const trackedStates = data?.tracked_states || []
  const nationalPrice = prices.find((p) => p.state === 'US')
  const statePrices = prices.filter((p) => p.state !== 'US')

  return (
    <div className="space-y-6">
      {/* National average */}
      {nationalPrice && (
        <div className="rounded-lg border bg-amber-50 p-4">
          <p className="text-sm font-medium text-amber-900">National Average</p>
          <p className="text-2xl font-bold text-amber-900">
            ${nationalPrice.price_per_gallon.toFixed(2)}/gallon
          </p>
          {nationalPrice.period_date && (
            <p className="text-xs text-amber-600">
              Week of {nationalPrice.period_date}
            </p>
          )}
        </div>
      )}

      {/* State selector */}
      <div>
        <label htmlFor="state-select" className="block text-sm font-medium text-gray-700">
          Select State
        </label>
        <select
          id="state-select"
          value={selectedState || ''}
          onChange={(e) => setSelectedState(e.target.value || undefined)}
          className="mt-1 block w-full rounded-md border-gray-300 shadow-sm focus:border-blue-500 focus:ring-blue-500 sm:text-sm"
        >
          <option value="">All States</option>
          {trackedStates.map((st) => (
            <option key={st} value={st}>
              {STATE_NAMES[st] || st}
            </option>
          ))}
        </select>
      </div>

      {/* State price cards */}
      <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
        {statePrices
          .filter((p) => !selectedState || p.state === selectedState)
          .map((p) => {
            const diff = nationalPrice
              ? ((p.price_per_gallon - nationalPrice.price_per_gallon) /
                  nationalPrice.price_per_gallon) *
                100
              : null

            return (
              <div
                key={p.state}
                className="rounded-lg border p-4 cursor-pointer hover:border-blue-300 transition-colors"
                onClick={() => setSelectedState(p.state)}
              >
                <div className="flex items-center justify-between">
                  <p className="font-semibold text-gray-900">
                    {STATE_NAMES[p.state] || p.state}
                  </p>
                  {diff !== null && (
                    <span
                      className={`text-xs font-medium ${
                        diff < 0 ? 'text-green-600' : diff > 0 ? 'text-red-600' : 'text-gray-500'
                      }`}
                    >
                      {diff > 0 ? '+' : ''}
                      {diff.toFixed(1)}%
                    </span>
                  )}
                </div>
                <p className="text-lg font-bold text-gray-900">
                  ${p.price_per_gallon.toFixed(2)}/gal
                </p>
              </div>
            )
          })}
      </div>

      {/* Detail sections when a state is selected */}
      {selectedState && (
        <>
          <OilPriceHistory state={selectedState} />
          <DealerList state={selectedState} />
        </>
      )}
    </div>
  )
}
