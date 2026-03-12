'use client'

import { useState } from 'react'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import { useForecast, useForecastTypes } from '@/lib/hooks/useForecast'

const UTILITY_LABELS: Record<string, string> = {
  electricity: 'Electricity',
  natural_gas: 'Natural Gas',
  heating_oil: 'Heating Oil',
  propane: 'Propane',
}

const TREND_COLORS: Record<string, string> = {
  increasing: 'text-red-600',
  decreasing: 'text-green-600',
  stable: 'text-gray-600',
}

const TREND_ARROWS: Record<string, string> = {
  increasing: '\u2191',
  decreasing: '\u2193',
  stable: '\u2192',
}

interface ForecastWidgetProps {
  state?: string
}

export function ForecastWidget({ state }: ForecastWidgetProps) {
  const [selectedUtility, setSelectedUtility] = useState('electricity')
  const [horizonDays, setHorizonDays] = useState(30)
  const { data: types } = useForecastTypes()
  const { data: forecast, isLoading, error } = useForecast(
    selectedUtility,
    state,
    horizonDays,
  )

  return (
    <Card>
      <CardHeader>
        <CardTitle className="text-lg">Rate Forecast</CardTitle>
        <p className="text-sm text-gray-500">
          Trend-based rate predictions by utility type
        </p>
      </CardHeader>
      <CardContent>
        <div className="flex gap-3 mb-4">
          <select
            value={selectedUtility}
            onChange={(e) => setSelectedUtility(e.target.value)}
            className="rounded-md border border-gray-300 px-3 py-1.5 text-sm"
          >
            {(types?.supported_types || Object.keys(UTILITY_LABELS)).map(
              (type) => (
                <option key={type} value={type}>
                  {UTILITY_LABELS[type] || type}
                </option>
              ),
            )}
          </select>
          <select
            value={horizonDays}
            onChange={(e) => setHorizonDays(Number(e.target.value))}
            className="rounded-md border border-gray-300 px-3 py-1.5 text-sm"
          >
            <option value={7}>7 days</option>
            <option value={30}>30 days</option>
            <option value={60}>60 days</option>
            <option value={90}>90 days</option>
          </select>
        </div>

        {isLoading && (
          <div className="py-8 text-center text-sm text-gray-500">
            Loading forecast...
          </div>
        )}

        {error && (
          <div className="rounded-md bg-red-50 p-3 text-sm text-red-700">
            {error instanceof Error ? error.message : 'Failed to load forecast'}
          </div>
        )}

        {forecast && !forecast.error && (
          <div className="space-y-4">
            <div className="grid grid-cols-2 gap-4">
              <div>
                <p className="text-xs text-gray-500">Current Rate</p>
                <p className="text-xl font-semibold">
                  ${forecast.current_rate.toFixed(4)}
                  <span className="text-xs text-gray-400 ml-1">
                    {forecast.unit}
                  </span>
                </p>
              </div>
              <div>
                <p className="text-xs text-gray-500">
                  Forecasted ({horizonDays}d)
                </p>
                <p className="text-xl font-semibold">
                  ${forecast.forecasted_rate.toFixed(4)}
                  <span
                    className={`text-sm ml-2 ${TREND_COLORS[forecast.trend]}`}
                  >
                    {TREND_ARROWS[forecast.trend]}{' '}
                    {Math.abs(forecast.percent_change).toFixed(1)}%
                  </span>
                </p>
              </div>
            </div>

            <div className="flex items-center justify-between text-xs text-gray-500 border-t pt-3">
              <span>
                Confidence: {(forecast.confidence * 100).toFixed(0)}%
              </span>
              <span>Data points: {forecast.data_points}</span>
              <span className="capitalize">{forecast.trend}</span>
            </div>
          </div>
        )}

        {forecast?.error && (
          <div className="py-4 text-center text-sm text-gray-500">
            {forecast.error}
          </div>
        )}
      </CardContent>
    </Card>
  )
}
