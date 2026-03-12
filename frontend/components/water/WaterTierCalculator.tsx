'use client'

import { useState } from 'react'
import { useWaterRates } from '@/lib/hooks/useWater'
import type { WaterRate } from '@/lib/api/water'

interface WaterTierCalculatorProps {
  state: string
}

export function WaterTierCalculator({ state }: WaterTierCalculatorProps) {
  const { data, isLoading, error } = useWaterRates(state)
  const [selectedMunicipality, setSelectedMunicipality] = useState<string>('')
  const [usageGallons, setUsageGallons] = useState<number>(5760)

  if (isLoading) {
    return (
      <div className="space-y-3">
        {[1, 2].map((i) => (
          <div key={i} className="animate-pulse rounded-lg bg-gray-100 h-12" />
        ))}
      </div>
    )
  }

  if (error || !data) return null

  const rates = data.rates || []
  const selectedRate = rates.find((r) => r.municipality === selectedMunicipality)

  const calculateCost = (rate: WaterRate, gallons: number) => {
    const tiers = rate.rate_tiers || []
    let remaining = gallons
    let tierCharges = 0
    let prevLimit = 0
    const breakdown: { tier: number; gallons: number; rate: number; charge: number }[] = []

    for (let i = 0; i < tiers.length; i++) {
      const tier = tiers[i]
      const limit = tier.limit_gallons
      const ratePerGal = tier.rate_per_gallon

      const tierCapacity = limit === null ? remaining : limit - prevLimit
      const gallonsInTier = Math.min(remaining, tierCapacity)
      const charge = gallonsInTier * ratePerGal

      tierCharges += charge
      breakdown.push({ tier: i + 1, gallons: gallonsInTier, rate: ratePerGal, charge })

      remaining -= gallonsInTier
      if (limit !== null) prevLimit = limit
      if (remaining <= 0) break
    }

    return {
      base: rate.base_charge,
      tierCharges: Math.round(tierCharges * 100) / 100,
      total: Math.round((rate.base_charge + tierCharges) * 100) / 100,
      breakdown,
    }
  }

  const cost = selectedRate ? calculateCost(selectedRate, usageGallons) : null

  return (
    <div className="space-y-4">
      <h3 className="text-lg font-semibold text-gray-900">Water Cost Calculator</h3>

      <div className="grid gap-4 sm:grid-cols-2">
        <div>
          <label htmlFor="water-municipality" className="block text-sm font-medium text-gray-700">
            Municipality
          </label>
          <select
            id="water-municipality"
            value={selectedMunicipality}
            onChange={(e) => setSelectedMunicipality(e.target.value)}
            className="mt-1 block w-full rounded-md border-gray-300 shadow-sm focus:border-cyan-500 focus:ring-cyan-500 sm:text-sm"
          >
            <option value="">Select municipality</option>
            {rates.map((r) => (
              <option key={r.municipality} value={r.municipality}>
                {r.municipality}
              </option>
            ))}
          </select>
        </div>

        <div>
          <label htmlFor="water-usage" className="block text-sm font-medium text-gray-700">
            Monthly Usage (gallons)
          </label>
          <input
            id="water-usage"
            type="number"
            min={0}
            max={100000}
            value={usageGallons}
            onChange={(e) => setUsageGallons(Number(e.target.value) || 0)}
            className="mt-1 block w-full rounded-md border-gray-300 shadow-sm focus:border-cyan-500 focus:ring-cyan-500 sm:text-sm"
          />
        </div>
      </div>

      {cost && selectedRate && (
        <div className="rounded-lg border bg-cyan-50 p-4 space-y-3">
          <div className="flex items-center justify-between">
            <p className="text-sm font-medium text-cyan-700">Estimated Monthly Bill</p>
            <p className="text-2xl font-bold text-cyan-900">${cost.total.toFixed(2)}</p>
          </div>

          <div className="space-y-1 text-sm text-cyan-800">
            <div className="flex justify-between">
              <span>Base charge</span>
              <span>${cost.base.toFixed(2)}</span>
            </div>
            {cost.breakdown.map((b) => (
              <div key={b.tier} className="flex justify-between">
                <span>Tier {b.tier}: {b.gallons.toLocaleString()} gal @ ${b.rate.toFixed(4)}/gal</span>
                <span>${b.charge.toFixed(2)}</span>
              </div>
            ))}
          </div>

          <p className="text-xs text-cyan-600">
            Annual estimate: ${(cost.total * 12).toFixed(2)}
          </p>
        </div>
      )}
    </div>
  )
}
