'use client'

import React, { useState, useEffect, useCallback } from 'react'
import { Card } from '@/components/ui/card'
import { Button } from '@/components/ui/button'
import { Badge } from '@/components/ui/badge'
import { cn } from '@/lib/utils/cn'
import {
  TrendingUp,
  TrendingDown,
  AlertTriangle,
  RefreshCw,
  Loader2,
  CheckCircle,
  Clock,
} from 'lucide-react'
import { fetchAnalytics } from './types'
import type { ConnectionHealth, CardLoadingState } from './types'

// ---------------------------------------------------------------------------
// ConnectionHealthCard
// ---------------------------------------------------------------------------

export function ConnectionHealthCard({
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
