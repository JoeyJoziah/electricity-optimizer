'use client'

import React from 'react'
import { Skeleton } from '@/components/ui/skeleton'
import { useCommunityStats } from '@/lib/hooks/useCommunity'
import { useSettingsStore } from '@/lib/store/settings'

export function CommunityStats() {
  const region = useSettingsStore((s) => s.region)
  const { data, isLoading, error } = useCommunityStats(region)

  if (isLoading) {
    return (
      <div data-testid="community-stats-loading" className="rounded-xl border bg-white p-6">
        <Skeleton variant="text" width={300} />
        <Skeleton variant="text" width={200} className="mt-2" />
      </div>
    )
  }

  if (error || !data) {
    return null // Gracefully hide stats on error — non-essential
  }

  return (
    <div data-testid="community-stats" className="rounded-xl border bg-gradient-to-r from-primary-50 to-blue-50 p-6">
      <p className="text-sm font-medium text-gray-800" data-testid="stats-banner">
        {data.user_count} users in your area
        {data.avg_savings_pct != null && (
          <> saved an average of {Math.round(data.avg_savings_pct)}%</>
        )}
      </p>
      {data.since && (
        <p className="mt-1 text-xs text-gray-500" data-testid="stats-attribution">
          Based on {data.post_count} reports since {new Date(data.since).toLocaleDateString()}
        </p>
      )}

      {/* Top tip */}
      {data.top_tip && (
        <div className="mt-3 rounded-lg bg-white/60 p-3" data-testid="top-tip">
          <p className="text-xs font-medium text-gray-600">Top tip</p>
          <p className="mt-1 text-sm text-gray-800">{data.top_tip.title}</p>
        </div>
      )}
    </div>
  )
}
