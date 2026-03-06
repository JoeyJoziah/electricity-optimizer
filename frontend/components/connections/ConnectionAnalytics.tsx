'use client'

import React, { useState, useCallback } from 'react'
import { Button } from '@/components/ui/button'
import { cn } from '@/lib/utils/cn'
import { API_ORIGIN } from '@/lib/config/env'
import { RefreshCw } from 'lucide-react'
import {
  RateComparisonCard,
  SavingsEstimateCard,
  RateHistoryCard,
  ConnectionHealthCard,
} from './analytics'

// Re-export types for consumers that may import from this module
export type {
  RateComparison,
  SavingsEstimate,
  RateHistoryPoint,
  RateHistory,
  StaleConnection,
  RateChangeAlert,
  ConnectionHealth,
  CardLoadingState,
} from './analytics'

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
      `${API_ORIGIN}/api/v1/connections/${connectionId}/sync`,
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
