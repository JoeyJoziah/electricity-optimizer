'use client'

import { useState } from 'react'
import { WaterRateBenchmark } from './WaterRateBenchmark'
import { WaterTierCalculator } from './WaterTierCalculator'
import { ConservationTips } from './ConservationTips'

const US_STATES: Record<string, string> = {
  AL: 'Alabama', AK: 'Alaska', AZ: 'Arizona', AR: 'Arkansas', CA: 'California',
  CO: 'Colorado', CT: 'Connecticut', DE: 'Delaware', DC: 'District of Columbia',
  FL: 'Florida', GA: 'Georgia', HI: 'Hawaii', ID: 'Idaho', IL: 'Illinois',
  IN: 'Indiana', IA: 'Iowa', KS: 'Kansas', KY: 'Kentucky', LA: 'Louisiana',
  ME: 'Maine', MD: 'Maryland', MA: 'Massachusetts', MI: 'Michigan', MN: 'Minnesota',
  MS: 'Mississippi', MO: 'Missouri', MT: 'Montana', NE: 'Nebraska', NV: 'Nevada',
  NH: 'New Hampshire', NJ: 'New Jersey', NM: 'New Mexico', NY: 'New York',
  NC: 'North Carolina', ND: 'North Dakota', OH: 'Ohio', OK: 'Oklahoma',
  OR: 'Oregon', PA: 'Pennsylvania', RI: 'Rhode Island', SC: 'South Carolina',
  SD: 'South Dakota', TN: 'Tennessee', TX: 'Texas', UT: 'Utah', VT: 'Vermont',
  VA: 'Virginia', WA: 'Washington', WV: 'West Virginia', WI: 'Wisconsin',
  WY: 'Wyoming',
}

export function WaterDashboard() {
  const [selectedState, setSelectedState] = useState<string>('')

  return (
    <div className="space-y-6">
      {/* Info banner */}
      <div className="rounded-lg border bg-cyan-50 p-4">
        <p className="text-sm font-medium text-cyan-900">
          Water Rate Benchmarking
        </p>
        <p className="text-sm text-cyan-700 mt-1">
          Compare municipal water rates in your area. Water utilities are geographic
          monopolies — this tool helps you understand your rates and find ways to conserve.
        </p>
      </div>

      {/* State selector */}
      <div>
        <label htmlFor="water-state-select" className="block text-sm font-medium text-gray-700">
          Select State
        </label>
        <select
          id="water-state-select"
          value={selectedState}
          onChange={(e) => setSelectedState(e.target.value)}
          className="mt-1 block w-full rounded-md border-gray-300 shadow-sm focus:border-cyan-500 focus:ring-cyan-500 sm:text-sm"
        >
          <option value="">Choose a state...</option>
          {Object.entries(US_STATES).map(([code, name]) => (
            <option key={code} value={code}>
              {name}
            </option>
          ))}
        </select>
      </div>

      {/* State-specific sections */}
      {selectedState && (
        <>
          <WaterRateBenchmark state={selectedState} />
          <WaterTierCalculator state={selectedState} />
        </>
      )}

      {/* Conservation tips (always visible) */}
      <ConservationTips />
    </div>
  )
}
