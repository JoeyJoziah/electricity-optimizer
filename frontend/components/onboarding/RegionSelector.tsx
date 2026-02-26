'use client'

import React, { useState, useMemo } from 'react'
import { Button } from '@/components/ui/button'
import { Badge } from '@/components/ui/badge'
import { MapPin, Search, Zap } from 'lucide-react'
import { US_REGIONS, DEREGULATED_ELECTRICITY_STATES } from '@/lib/constants/regions'
import type { StateOption } from '@/lib/constants/regions'

interface RegionSelectorProps {
  onSelect: (region: string) => void
  isLoading?: boolean
}

export function RegionSelector({ onSelect, isLoading }: RegionSelectorProps) {
  const [search, setSearch] = useState('')
  const [selected, setSelected] = useState<string | null>(null)

  const filteredRegions = useMemo(() => {
    if (!search.trim()) return US_REGIONS

    const q = search.toLowerCase()
    return US_REGIONS.map((group) => ({
      ...group,
      states: group.states.filter(
        (s) =>
          s.label.toLowerCase().includes(q) ||
          s.abbr.toLowerCase().includes(q)
      ),
    })).filter((group) => group.states.length > 0)
  }, [search])

  const handleSubmit = () => {
    if (selected) {
      onSelect(selected)
    }
  }

  return (
    <div className="mx-auto max-w-lg space-y-6">
      <div className="text-center">
        <div className="mx-auto mb-4 flex h-16 w-16 items-center justify-center rounded-full bg-blue-100">
          <MapPin className="h-8 w-8 text-blue-600" />
        </div>
        <h1 className="text-2xl font-bold text-gray-900">Select your state</h1>
        <p className="mt-2 text-gray-600">
          We&apos;ll show you local electricity rates and supplier options for your area.
        </p>
      </div>

      {/* Search */}
      <div className="relative">
        <Search className="absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-gray-400" />
        <input
          type="text"
          placeholder="Search states..."
          value={search}
          onChange={(e) => setSearch(e.target.value)}
          className="w-full rounded-lg border border-gray-300 py-2.5 pl-10 pr-4 text-sm focus:border-blue-500 focus:outline-none focus:ring-1 focus:ring-blue-500"
        />
      </div>

      {/* State list */}
      <div className="max-h-80 overflow-y-auto rounded-lg border border-gray-200">
        {filteredRegions.map((group) => (
          <div key={group.label}>
            <div className="sticky top-0 bg-gray-50 px-3 py-1.5 text-xs font-semibold uppercase tracking-wide text-gray-500">
              {group.label}
            </div>
            {group.states.map((state: StateOption) => {
              const isDeregulated = DEREGULATED_ELECTRICITY_STATES.has(state.abbr)
              const isSelected = selected === state.value
              return (
                <button
                  key={state.value}
                  type="button"
                  onClick={() => setSelected(state.value)}
                  className={`flex w-full items-center justify-between px-4 py-2.5 text-left text-sm transition-colors ${
                    isSelected
                      ? 'bg-blue-50 text-blue-700'
                      : 'text-gray-700 hover:bg-gray-50'
                  }`}
                >
                  <span className="flex items-center gap-2">
                    <span className="font-medium">{state.label}</span>
                    <span className="text-gray-400">({state.abbr})</span>
                  </span>
                  {isDeregulated && (
                    <Badge variant="info" size="sm">
                      <Zap className="mr-1 h-3 w-3" />
                      Supplier choice
                    </Badge>
                  )}
                </button>
              )
            })}
          </div>
        ))}
        {filteredRegions.length === 0 && (
          <p className="px-4 py-8 text-center text-sm text-gray-500">
            No states match &quot;{search}&quot;
          </p>
        )}
      </div>

      {/* Submit */}
      <Button
        variant="primary"
        className="w-full"
        disabled={!selected || isLoading}
        onClick={handleSubmit}
      >
        {isLoading ? 'Saving...' : 'Continue to Dashboard'}
      </Button>

      <p className="text-center text-xs text-gray-500">
        * States marked with &quot;Supplier choice&quot; have deregulated electricity markets,
        meaning you can choose your energy supplier.
      </p>
    </div>
  )
}
