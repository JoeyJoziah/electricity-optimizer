'use client'

import React, { useState, useEffect, useCallback } from 'react'
import { Card } from '@/components/ui/card'
import { Button } from '@/components/ui/button'
import { Badge } from '@/components/ui/badge'
import { cn } from '@/lib/utils/cn'
import {
  TrendingUp,
  TrendingDown,
  DollarSign,
  AlertTriangle,
  BarChart3,
  RefreshCw,
  Loader2,
  CheckCircle,
  XCircle,
  Clock,
} from 'lucide-react'

const API_BASE = process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000'

// ---------------------------------------------------------------------------
// Types
// ---------------------------------------------------------------------------

interface RateComparison {
  user_rate: number
  market_average: number
  delta: number
  percentage_difference: number
  is_above_average: boolean
}

interface SavingsEstimate {
  estimated_annual_savings_vs_best: number
  estimated_monthly_savings_vs_best: number
  current_annual_cost: number
}

interface RateHistoryPoint {
  date: string
  rate: number
  supplier: string
}

interface RateHistory {
  data_points: RateHistoryPoint[]
}

interface StaleConnection {
  id: string
  supplier_name: string
  last_sync_at: string | null
  days_since_sync: number
}

interface RateChangeAlert {
  id: string
  supplier_name: string
  old_rate: number
  new_rate: number
  change_percentage: number
  detected_at: string
}

interface ConnectionHealth {
  stale_connections: StaleConnection[]
  rate_change_alerts: RateChangeAlert[]
}

type CardLoadingState = 'idle' | 'loading' | 'success' | 'error'

// ---------------------------------------------------------------------------
// Fetch helper
// ---------------------------------------------------------------------------

async function fetchAnalytics<T>(
  path: string,
  params?: Record<string, string>
): Promise<T> {
  const url = new URL(`${API_BASE}/api/v1/connections/analytics/${path}`)
  if (params) {
    Object.entries(params).forEach(([k, v]) => url.searchParams.set(k, v))
  }
  const res = await fetch(url.toString(), { credentials: 'include' })
  if (!res.ok) {
    throw new Error(`Failed to fetch ${path}: ${res.status}`)
  }
  return res.json()
}

// ---------------------------------------------------------------------------
// RateComparisonCard
// ---------------------------------------------------------------------------

function RateComparisonCard({
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

// ---------------------------------------------------------------------------
// SavingsEstimateCard
// ---------------------------------------------------------------------------

function SavingsEstimateCard({
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

  const handleKwhChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    const raw = e.target.value
    setInputValue(raw)
    const parsed = parseInt(raw, 10)
    if (!isNaN(parsed) && parsed > 0 && parsed <= 99999) {
      setMonthlyKwh(parsed)
    }
  }

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
              className="block w-full rounded-lg border border-gray-300 px-3 py-2 text-sm text-gray-900 focus-visible:border-primary-500 focus-visible:ring-2 focus-visible:ring-primary-500 focus-visible:outline-none"
              aria-label="Monthly electricity usage in kilowatt hours"
            />
          </div>
        </div>
      )}
    </Card>
  )
}

// ---------------------------------------------------------------------------
// RateHistoryCard
// ---------------------------------------------------------------------------

function RateHistoryCard({
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

function formatDate(dateString: string): string {
  try {
    const d = new Date(dateString)
    return d.toLocaleDateString('en-US', {
      month: 'short',
      day: 'numeric',
      year: 'numeric',
    })
  } catch {
    return dateString
  }
}

// ---------------------------------------------------------------------------
// ConnectionHealthCard
// ---------------------------------------------------------------------------

function ConnectionHealthCard({
  refreshKey,
  onSync,
}: {
  refreshKey: number
  onSync?: (connectionId: string) => Promise<void>
}) {
  const [data, setData] = useState<ConnectionHealth | null>(null)
  const [state, setState] = useState<CardLoadingState>('idle')
  const [error, setError] = useState<string | null>(null)
  const [syncingIds, setSyncingIds] = useState<Set<string>>(new Set())

  const load = useCallback(async () => {
    setState('loading')
    setError(null)
    try {
      const result = await fetchAnalytics<ConnectionHealth>('health')
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

  const handleSyncConnection = async (connectionId: string) => {
    if (!onSync) return
    setSyncingIds((prev) => new Set(prev).add(connectionId))
    try {
      await onSync(connectionId)
    } finally {
      setSyncingIds((prev) => {
        const next = new Set(prev)
        next.delete(connectionId)
        return next
      })
    }
  }

  const totalIssues =
    (data?.stale_connections.length || 0) + (data?.rate_change_alerts.length || 0)

  return (
    <Card data-testid="connection-health-card">
      <div className="flex items-center gap-2 mb-4">
        {totalIssues > 0 && state === 'success' ? (
          <AlertTriangle className="h-5 w-5 text-warning-500" aria-hidden="true" />
        ) : (
          <CheckCircle className="h-5 w-5 text-success-500" aria-hidden="true" />
        )}
        <h3 className="text-lg font-semibold text-gray-900">Connection Health</h3>
        {state === 'success' && totalIssues > 0 && (
          <Badge variant="warning">{totalIssues} issue{totalIssues !== 1 ? 's' : ''}</Badge>
        )}
      </div>

      {state === 'loading' && (
        <div className="flex items-center justify-center py-8" data-testid="connection-health-loading" role="status">
          <Loader2 className="h-5 w-5 animate-spin text-gray-400" />
          <span className="ml-2 text-sm text-gray-500">Checking health...</span>
        </div>
      )}

      {state === 'error' && (
        <div className="rounded-lg bg-danger-50 border border-danger-200 p-4 text-center" role="alert">
          <p className="text-sm text-danger-700">{error}</p>
          <button
            onClick={load}
            className="mt-2 text-sm font-medium text-danger-600 hover:text-danger-800 transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-danger-500 focus-visible:ring-offset-2 rounded"
            aria-label="Retry loading connection health"
          >
            Try again
          </button>
        </div>
      )}

      {state === 'success' && data && (
        <div className="space-y-3">
          {/* All healthy */}
          {totalIssues === 0 && (
            <div className="flex items-center gap-3 rounded-lg bg-success-50 p-4">
              <CheckCircle className="h-5 w-5 text-success-500 shrink-0" aria-hidden="true" />
              <p className="text-sm text-success-700">
                All connections are healthy and up to date.
              </p>
            </div>
          )}

          {/* Stale connections */}
          {data.stale_connections.map((conn) => (
            <div
              key={conn.id}
              className="flex items-center justify-between rounded-lg border border-warning-200 bg-warning-50 p-3"
              data-testid={`stale-connection-${conn.id}`}
            >
              <div className="flex items-center gap-3 min-w-0">
                <Clock className="h-4 w-4 text-warning-500 shrink-0" aria-hidden="true" />
                <div className="min-w-0">
                  <p className="text-sm font-medium text-warning-800 truncate">
                    {conn.supplier_name}
                  </p>
                  <p className="text-xs text-warning-600">
                    Last synced {conn.days_since_sync} day{conn.days_since_sync !== 1 ? 's' : ''} ago
                  </p>
                </div>
              </div>
              {onSync && (
                <Button
                  variant="outline"
                  size="sm"
                  onClick={() => handleSyncConnection(conn.id)}
                  loading={syncingIds.has(conn.id)}
                  disabled={syncingIds.has(conn.id)}
                  aria-label={`Sync ${conn.supplier_name}`}
                >
                  <RefreshCw
                    className={cn(
                      'h-3.5 w-3.5 mr-1',
                      syncingIds.has(conn.id) && 'animate-spin'
                    )}
                  />
                  Sync Now
                </Button>
              )}
            </div>
          ))}

          {/* Rate change alerts */}
          {data.rate_change_alerts.map((alert) => {
            const isIncrease = alert.new_rate > alert.old_rate

            return (
              <div
                key={alert.id}
                className={cn(
                  'rounded-lg border p-3',
                  isIncrease
                    ? 'border-danger-200 bg-danger-50'
                    : 'border-success-200 bg-success-50'
                )}
                data-testid={`rate-alert-${alert.id}`}
              >
                <div className="flex items-center gap-2 mb-1">
                  {isIncrease ? (
                    <TrendingUp className="h-4 w-4 text-danger-500" aria-hidden="true" />
                  ) : (
                    <TrendingDown className="h-4 w-4 text-success-500" aria-hidden="true" />
                  )}
                  <span
                    className={cn(
                      'text-sm font-medium',
                      isIncrease ? 'text-danger-800' : 'text-success-800'
                    )}
                  >
                    {alert.supplier_name} rate {isIncrease ? 'increased' : 'decreased'}
                  </span>
                  <Badge variant={isIncrease ? 'danger' : 'success'} className="ml-auto">
                    {isIncrease ? '+' : ''}
                    {alert.change_percentage.toFixed(1)}%
                  </Badge>
                </div>
                <p
                  className={cn(
                    'text-xs',
                    isIncrease ? 'text-danger-600' : 'text-success-600'
                  )}
                >
                  {(alert.old_rate * 100).toFixed(2)} c/kWh &rarr;{' '}
                  {(alert.new_rate * 100).toFixed(2)} c/kWh
                </p>
              </div>
            )
          })}
        </div>
      )}
    </Card>
  )
}

// ---------------------------------------------------------------------------
// Main ConnectionAnalytics component
// ---------------------------------------------------------------------------

export function ConnectionAnalytics() {
  const [refreshKey, setRefreshKey] = useState(0)
  const [refreshing, setRefreshing] = useState(false)

  const handleRefreshAll = useCallback(() => {
    setRefreshing(true)
    setRefreshKey((k) => k + 1)
    // Reset the visual spinner after a short delay
    setTimeout(() => setRefreshing(false), 600)
  }, [])

  const handleSyncConnection = useCallback(async (connectionId: string) => {
    const res = await fetch(
      `${API_BASE}/api/v1/connections/${connectionId}/sync`,
      {
        method: 'POST',
        credentials: 'include',
      }
    )
    if (!res.ok) {
      throw new Error('Sync failed')
    }
    // Refresh health card after sync
    setRefreshKey((k) => k + 1)
  }, [])

  return (
    <div className="space-y-6" data-testid="connection-analytics">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div>
          <h2 className="text-xl font-bold text-gray-900">Connection Analytics</h2>
          <p className="mt-1 text-sm text-gray-500">
            Insights into your electricity rates and potential savings.
          </p>
        </div>
        <Button
          variant="outline"
          size="sm"
          onClick={handleRefreshAll}
          disabled={refreshing}
          aria-label="Refresh all analytics"
          data-testid="refresh-analytics"
        >
          <RefreshCw
            className={cn('h-4 w-4 mr-1.5', refreshing && 'animate-spin')}
          />
          Refresh
        </Button>
      </div>

      {/* Cards grid */}
      <div className="grid gap-6 lg:grid-cols-2">
        <RateComparisonCard refreshKey={refreshKey} />
        <SavingsEstimateCard refreshKey={refreshKey} />
      </div>

      <RateHistoryCard refreshKey={refreshKey} />
      <ConnectionHealthCard
        refreshKey={refreshKey}
        onSync={handleSyncConnection}
      />
    </div>
  )
}
