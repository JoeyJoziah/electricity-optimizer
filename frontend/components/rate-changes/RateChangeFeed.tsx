'use client'

import { useState } from 'react'
import { useRateChanges } from '@/lib/hooks/useRateChanges'
import { RateChangeCard } from './RateChangeCard'

const UTILITY_OPTIONS = [
  { value: '', label: 'All Utilities' },
  { value: 'electricity', label: 'Electricity' },
  { value: 'natural_gas', label: 'Natural Gas' },
  { value: 'heating_oil', label: 'Heating Oil' },
  { value: 'propane', label: 'Propane' },
  { value: 'community_solar', label: 'Community Solar' },
]

const DAYS_OPTIONS = [
  { value: 7, label: '7 days' },
  { value: 14, label: '14 days' },
  { value: 30, label: '30 days' },
]

export function RateChangeFeed() {
  const [utilityType, setUtilityType] = useState('')
  const [days, setDays] = useState(7)

  const { data, isLoading, error } = useRateChanges({
    utility_type: utilityType || undefined,
    days,
    limit: 50,
  })

  if (isLoading) {
    return (
      <div className="space-y-4">
        {[1, 2, 3].map((i) => (
          <div key={i} className="h-32 animate-pulse rounded-lg bg-muted" />
        ))}
      </div>
    )
  }

  if (error) {
    return <p className="text-sm text-danger-500">Failed to load rate changes.</p>
  }

  const changes = data?.changes ?? []

  return (
    <div>
      <div className="mb-4 flex gap-3">
        <select
          value={utilityType}
          onChange={(e) => setUtilityType(e.target.value)}
          className="rounded border px-3 py-1.5 text-sm"
          aria-label="Filter by utility type"
        >
          {UTILITY_OPTIONS.map((opt) => (
            <option key={opt.value} value={opt.value}>
              {opt.label}
            </option>
          ))}
        </select>

        <select
          value={days}
          onChange={(e) => setDays(Number(e.target.value))}
          className="rounded border px-3 py-1.5 text-sm"
          aria-label="Time range"
        >
          {DAYS_OPTIONS.map((opt) => (
            <option key={opt.value} value={opt.value}>
              {opt.label}
            </option>
          ))}
        </select>
      </div>

      {changes.length === 0 ? (
        <p className="text-sm text-muted-foreground">
          No rate changes detected in the last {days} days.
        </p>
      ) : (
        <div className="space-y-3">
          {changes.map((c) => (
            <RateChangeCard key={c.id} change={c} />
          ))}
        </div>
      )}
    </div>
  )
}
