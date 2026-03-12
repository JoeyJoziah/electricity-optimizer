'use client'

import { useState } from 'react'
import { ForecastWidget } from './ForecastWidget'
import { OptimizationReport } from './OptimizationReport'
import { DataExport } from './DataExport'

const US_STATES = [
  'AL', 'AK', 'AZ', 'AR', 'CA', 'CO', 'CT', 'DE', 'FL', 'GA',
  'HI', 'ID', 'IL', 'IN', 'IA', 'KS', 'KY', 'LA', 'ME', 'MD',
  'MA', 'MI', 'MN', 'MS', 'MO', 'MT', 'NE', 'NV', 'NH', 'NJ',
  'NM', 'NY', 'NC', 'ND', 'OH', 'OK', 'OR', 'PA', 'RI', 'SC',
  'SD', 'TN', 'TX', 'UT', 'VT', 'VA', 'WA', 'WV', 'WI', 'WY',
  'DC',
]

export function AnalyticsDashboard() {
  const [state, setState] = useState('CT')

  return (
    <div className="space-y-6">
      {/* State selector */}
      <div className="flex items-center gap-3">
        <label htmlFor="state-select" className="text-sm font-medium text-gray-700">
          State
        </label>
        <select
          id="state-select"
          value={state}
          onChange={(e) => setState(e.target.value)}
          className="rounded-md border border-gray-300 px-3 py-1.5 text-sm"
        >
          {US_STATES.map((s) => (
            <option key={s} value={s}>
              {s}
            </option>
          ))}
        </select>
      </div>

      {/* Forecast (Pro tier) */}
      <ForecastWidget state={state} />

      {/* Optimization Report (Business tier) */}
      <OptimizationReport state={state} />

      {/* Data Export (Business tier) */}
      <DataExport state={state} />
    </div>
  )
}
