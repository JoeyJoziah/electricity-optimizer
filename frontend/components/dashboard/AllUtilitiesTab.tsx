'use client'

import React from 'react'
import { useSettingsStore } from '@/lib/store/settings'
import { CombinedSavingsCard } from './CombinedSavingsCard'
import { NeighborhoodCard } from './NeighborhoodCard'

const UTILITY_LABELS: Record<string, string> = {
  electricity: 'Electricity',
  natural_gas: 'Natural Gas',
  heating_oil: 'Heating Oil',
  propane: 'Propane',
  community_solar: 'Community Solar',
  water: 'Water',
}

export function AllUtilitiesTab() {
  const userUtilities = useSettingsStore((s) => s.utilityTypes)

  return (
    <div data-testid="all-utilities-tab" className="space-y-6">
      {/* Combined savings overview */}
      <div className="grid gap-6 md:grid-cols-2">
        <CombinedSavingsCard />
        <NeighborhoodCard />
      </div>

      {/* Per-utility summary cards */}
      <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
        {userUtilities.map((ut) => (
          <div
            key={ut}
            data-testid={`utility-summary-${ut}`}
            className="rounded-xl border bg-white p-4"
          >
            <h4 className="text-sm font-medium text-gray-700">
              {UTILITY_LABELS[ut] || ut}
            </h4>
            <p className="mt-1 text-xs text-gray-400">
              View details in the {UTILITY_LABELS[ut] || ut} tab
            </p>
          </div>
        ))}
      </div>
    </div>
  )
}
