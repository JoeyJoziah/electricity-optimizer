'use client'

import React, { useState, useEffect, useCallback } from 'react'
import { Card } from '@/components/ui/card'
import { Badge } from '@/components/ui/badge'
import { cn } from '@/lib/utils/cn'
import {
  TrendingUp,
  TrendingDown,
  BarChart3,
  Loader2,
} from 'lucide-react'
import { fetchAnalytics } from './types'
import type { RateComparison, CardLoadingState } from './types'

// ---------------------------------------------------------------------------
// RateComparisonCard
// ---------------------------------------------------------------------------

export function RateComparisonCard({
  refreshKey,
}: {
  refreshKey: number
}) {
  const [data, setData] = useState<RateComparison | null>(null)
  const [state, setState] = useState<CardLoadingState>('idle')
  const [error, setError] = useState<string | null>(null)

  const load = useCallback(async () => {
    setState('loading')
    setError(null)
    try {
      const result = await fetchAnalytics<RateComparison>('comparison')
      setData(result)
      setState('success')
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to load')
      setState('error')
    }
  }, [])

  useEffect(() => {
    load()
  }, [load, refreshKey])

  return (
    <Card data-testid="rate-comparison-card">
      <div className="flex items-center gap-2 mb-4">
        <BarChart3 className="h-5 w-5 text-primary-600" aria-hidden="true" />
        <h3 className="text-lg font-semibold text-gray-900">Rate Comparison</h3>
      </div>

      {state === 'loading' && (
        <div className="flex items-center justify-center py-8" data-testid="rate-comparison-loading" role="status">
          <Loader2 className="h-5 w-5 animate-spin text-gray-400" />
          <span className="ml-2 text-sm text-gray-500">Loading comparison...</span>
        </div>
      )}

      {state === 'error' && (
        <div className="rounded-lg bg-danger-50 border border-danger-200 p-4 text-center" role="alert">
          <p className="text-sm text-danger-700">{error}</p>
          <button
            onClick={load}
            className="mt-2 text-sm font-medium text-danger-600 hover:text-danger-800 transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-danger-500 focus-visible:ring-offset-2 rounded"
            aria-label="Retry loading rate comparison"
          >
            Try again
          </button>
        </div>
      )}

      {state === 'success' && data && (
        <div className="space-y-4">
          <div className="grid grid-cols-2 gap-4">
            <div className="rounded-lg bg-gray-50 p-3">
              <p className="text-xs font-medium text-gray-500 uppercase tracking-wider">Your Rate</p>
              <p className="mt-1 text-2xl font-bold text-gray-900">
                {(data.user_rate * 100).toFixed(2)}
                <span className="text-sm font-normal text-gray-500 ml-1">c/kWh</span>
              </p>
            </div>
            <div className="rounded-lg bg-gray-50 p-3">
              <p className="text-xs font-medium text-gray-500 uppercase tracking-wider">Market Average</p>
              <p className="mt-1 text-2xl font-bold text-gray-900">
                {(data.market_average * 100).toFixed(2)}
                <span className="text-sm font-normal text-gray-500 ml-1">c/kWh</span>
              </p>
            </div>
          </div>

          <div
            className={cn(
              'flex items-center justify-between rounded-lg p-3',
              data.is_above_average ? 'bg-danger-50' : 'bg-success-50'
            )}
          >
            <div className="flex items-center gap-2">
              {data.is_above_average ? (
                <TrendingUp className="h-5 w-5 text-danger-500" aria-hidden="true" />
              ) : (
                <TrendingDown className="h-5 w-5 text-success-500" aria-hidden="true" />
              )}
              <span
                className={cn(
                  'text-sm font-medium',
                  data.is_above_average ? 'text-danger-700' : 'text-success-700'
                )}
              >
                {data.is_above_average ? 'Above' : 'Below'} market average
              </span>
            </div>
            <Badge variant={data.is_above_average ? 'danger' : 'success'}>
              {data.is_above_average ? '+' : ''}
              {data.percentage_difference.toFixed(1)}%
            </Badge>
          </div>
        </div>
      )}
    </Card>
  )
}
