'use client'

import React, { useState, useEffect, useCallback, useRef } from 'react'
import { Card } from '@/components/ui/card'
import { cn } from '@/lib/utils/cn'
import { DollarSign, Loader2 } from 'lucide-react'
import { fetchAnalytics } from './types'
import type { SavingsEstimate, CardLoadingState } from './types'

// ---------------------------------------------------------------------------
// SavingsEstimateCard
// ---------------------------------------------------------------------------

export function SavingsEstimateCard({
  refreshKey,
}: {
  refreshKey: number
}) {
  const [data, setData] = useState<SavingsEstimate | null>(null)
  const [state, setState] = useState<CardLoadingState>('idle')
  const [error, setError] = useState<string | null>(null)
  const [monthlyKwh, setMonthlyKwh] = useState<number>(900)
  const [inputValue, setInputValue] = useState<string>('900')

  const load = useCallback(async () => {
    setState('loading')
    setError(null)
    try {
      const result = await fetchAnalytics<SavingsEstimate>('savings', {
        monthly_kwh: String(monthlyKwh),
      })
      setData(result)
      setState('success')
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to load')
      setState('error')
    }
  }, [monthlyKwh])

  useEffect(() => {
    load()
  }, [load, refreshKey])

  // Debounce kWh changes to avoid excessive API calls
  const debounceRef = useRef<ReturnType<typeof setTimeout> | null>(null)

  const handleKwhChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    const raw = e.target.value
    setInputValue(raw)
    const parsed = parseInt(raw, 10)
    if (!isNaN(parsed) && parsed > 0 && parsed <= 99999) {
      if (debounceRef.current) clearTimeout(debounceRef.current)
      debounceRef.current = setTimeout(() => {
        setMonthlyKwh(parsed)
      }, 500)
    }
  }

  // Cleanup debounce timer on unmount
  useEffect(() => {
    return () => {
      if (debounceRef.current) clearTimeout(debounceRef.current)
    }
  }, [])

  const formatCurrency = (amount: number): string => {
    return new Intl.NumberFormat('en-US', {
      style: 'currency',
      currency: 'USD',
      minimumFractionDigits: 0,
      maximumFractionDigits: 0,
    }).format(amount)
  }

  const isPositiveSavings =
    data !== null && data.estimated_annual_savings_vs_best > 0

  return (
    <Card data-testid="savings-estimate-card">
      <div className="flex items-center gap-2 mb-4">
        <DollarSign className="h-5 w-5 text-success-600" aria-hidden="true" />
        <h3 className="text-lg font-semibold text-gray-900">Savings Estimate</h3>
      </div>

      {state === 'loading' && (
        <div className="flex items-center justify-center py-8" data-testid="savings-estimate-loading" role="status">
          <Loader2 className="h-5 w-5 animate-spin text-gray-400" />
          <span className="ml-2 text-sm text-gray-500">Calculating savings...</span>
        </div>
      )}

      {state === 'error' && (
        <div className="rounded-lg bg-danger-50 border border-danger-200 p-4 text-center" role="alert">
          <p className="text-sm text-danger-700">{error}</p>
          <button
            onClick={load}
            className="mt-2 text-sm font-medium text-danger-600 hover:text-danger-800 transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-danger-500 focus-visible:ring-offset-2 rounded"
            aria-label="Retry loading savings estimate"
          >
            Try again
          </button>
        </div>
      )}

      {state === 'success' && data && (
        <div className="space-y-4">
          {/* Big savings number */}
          <div className="text-center py-2">
            <p className="text-xs font-medium text-gray-500 uppercase tracking-wider">
              Estimated Annual Savings
            </p>
            <p
              className={cn(
                'mt-1 text-4xl font-bold',
                isPositiveSavings ? 'text-success-600' : 'text-gray-900'
              )}
              data-testid="annual-savings-amount"
            >
              {formatCurrency(data.estimated_annual_savings_vs_best)}
            </p>
            <p className="mt-1 text-sm text-gray-500">
              {formatCurrency(data.estimated_monthly_savings_vs_best)}/month vs best available
            </p>
          </div>

          {/* Cost comparison */}
          <div className="rounded-lg bg-gray-50 p-3">
            <div className="flex items-center justify-between text-sm">
              <span className="text-gray-600">Current annual cost</span>
              <span className="font-semibold text-gray-900">
                {formatCurrency(data.current_annual_cost)}
              </span>
            </div>
            <div className="flex items-center justify-between text-sm mt-2">
              <span className="text-gray-600">Best available annual cost</span>
              <span className="font-semibold text-success-700">
                {formatCurrency(
                  data.current_annual_cost - data.estimated_annual_savings_vs_best
                )}
              </span>
            </div>
          </div>

          {/* Usage input */}
          <div>
            <label
              htmlFor="monthly-kwh-input"
              className="block text-xs font-medium text-gray-500 mb-1"
            >
              Monthly usage (kWh)
            </label>
            <input
              id="monthly-kwh-input"
              type="number"
              min={1}
              max={99999}
              value={inputValue}
              onChange={handleKwhChange}
              className="block w-full rounded-lg bg-white border border-gray-300 px-3 py-2 text-sm text-gray-900 focus-visible:border-primary-500 focus-visible:ring-2 focus-visible:ring-primary-500 focus-visible:outline-none"
              aria-label="Monthly electricity usage in kilowatt hours"
            />
          </div>
        </div>
      )}
    </Card>
  )
}
