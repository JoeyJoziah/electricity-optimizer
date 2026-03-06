'use client'

import React, { useState, useEffect, useCallback } from 'react'
import { Card } from '@/components/ui/card'
import { cn } from '@/lib/utils/cn'
import { TrendingUp, TrendingDown, Loader2 } from 'lucide-react'
import { fetchAnalytics, formatDate } from './types'
import type { RateHistoryPoint, RateHistory, CardLoadingState } from './types'

// ---------------------------------------------------------------------------
// RateHistoryCard
// ---------------------------------------------------------------------------

export function RateHistoryCard({
  refreshKey,
}: {
  refreshKey: number
}) {
  const [data, setData] = useState<RateHistoryPoint[]>([])
  const [state, setState] = useState<CardLoadingState>('idle')
  const [error, setError] = useState<string | null>(null)
  const [showAll, setShowAll] = useState(false)

  const load = useCallback(async () => {
    setState('loading')
    setError(null)
    try {
      const result = await fetchAnalytics<RateHistory>('history')
      setData(result.data_points || [])
      setState('success')
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to load')
      setState('error')
    }
  }, [])

  useEffect(() => {
    load()
  }, [load, refreshKey])

  const visible = showAll ? data : data.slice(0, 12)

  return (
    <Card data-testid="rate-history-card" padding="none">
      <div className="flex items-center gap-2 p-4 pb-0">
        <TrendingUp className="h-5 w-5 text-primary-600" aria-hidden="true" />
        <h3 className="text-lg font-semibold text-gray-900">Rate History</h3>
      </div>

      {state === 'loading' && (
        <div className="flex items-center justify-center py-8" data-testid="rate-history-loading" role="status">
          <Loader2 className="h-5 w-5 animate-spin text-gray-400" />
          <span className="ml-2 text-sm text-gray-500">Loading history...</span>
        </div>
      )}

      {state === 'error' && (
        <div className="m-4 rounded-lg bg-danger-50 border border-danger-200 p-4 text-center" role="alert">
          <p className="text-sm text-danger-700">{error}</p>
          <button
            onClick={load}
            className="mt-2 text-sm font-medium text-danger-600 hover:text-danger-800 transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-danger-500 focus-visible:ring-offset-2 rounded"
            aria-label="Retry loading rate history"
          >
            Try again
          </button>
        </div>
      )}

      {state === 'success' && (
        <>
          {data.length === 0 ? (
            <div className="p-4 text-center">
              <p className="text-sm text-gray-500">No rate history available yet.</p>
            </div>
          ) : (
            <>
              <div className="overflow-x-auto">
                <table className="w-full text-sm" data-testid="rate-history-table">
                  <thead>
                    <tr className="border-b border-gray-200 text-left">
                      <th className="px-4 py-2 font-medium text-gray-500">Date</th>
                      <th className="px-4 py-2 font-medium text-gray-500">Rate</th>
                      <th className="px-4 py-2 font-medium text-gray-500">Supplier</th>
                      <th className="px-4 py-2 font-medium text-gray-500 text-right">Change</th>
                    </tr>
                  </thead>
                  <tbody>
                    {visible.map((point, idx) => {
                      // Calculate change vs previous row (previous in time = next in array for chronological order,
                      // but data_points may already be sorted newest-first or oldest-first.
                      // We compare against the next entry in the visible array as a "previous period")
                      const prevPoint = idx < data.length - 1 ? data[idx + 1] : null
                      let change: number | null = null
                      if (prevPoint) {
                        change = point.rate - prevPoint.rate
                      }

                      return (
                        <tr
                          key={`${point.date}-${idx}`}
                          className="border-b border-gray-100 last:border-b-0 hover:bg-gray-50 transition-colors"
                        >
                          <td className="px-4 py-2 text-gray-700 whitespace-nowrap">
                            {formatDate(point.date)}
                          </td>
                          <td className="px-4 py-2 font-medium text-gray-900 whitespace-nowrap">
                            {(point.rate * 100).toFixed(2)} c/kWh
                          </td>
                          <td className="px-4 py-2 text-gray-600 truncate max-w-[150px]">
                            {point.supplier}
                          </td>
                          <td className="px-4 py-2 text-right whitespace-nowrap">
                            {change !== null ? (
                              <span
                                className={cn(
                                  'inline-flex items-center gap-1 text-sm font-medium',
                                  change > 0
                                    ? 'text-danger-600'
                                    : change < 0
                                      ? 'text-success-600'
                                      : 'text-gray-400'
                                )}
                              >
                                {change > 0 ? (
                                  <TrendingUp className="h-3.5 w-3.5" aria-hidden="true" />
                                ) : change < 0 ? (
                                  <TrendingDown className="h-3.5 w-3.5" aria-hidden="true" />
                                ) : null}
                                {change > 0 ? '+' : ''}
                                {(change * 100).toFixed(2)}
                              </span>
                            ) : (
                              <span className="text-gray-400">&mdash;</span>
                            )}
                          </td>
                        </tr>
                      )
                    })}
                  </tbody>
                </table>
              </div>

              {data.length > 12 && (
                <div className="p-3 text-center border-t border-gray-100">
                  <button
                    onClick={() => setShowAll(!showAll)}
                    className="text-sm font-medium text-primary-600 hover:text-primary-800 transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary-500 focus-visible:ring-offset-2 rounded"
                    data-testid="show-more-history"
                    aria-label={showAll ? 'Show fewer rate history entries' : `Show all ${data.length} rate history entries`}
                  >
                    {showAll
                      ? 'Show less'
                      : `Show all ${data.length} entries`}
                  </button>
                </div>
              )}
            </>
          )}
        </>
      )}
    </Card>
  )
}
