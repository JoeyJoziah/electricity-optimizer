'use client'

import React from 'react'
import Link from 'next/link'
import { Zap, Flame, Droplets, Sun, ChevronRight, X } from 'lucide-react'
import { cn } from '@/lib/utils/cn'
import { useUtilityDiscovery } from '@/lib/hooks/useUtilityDiscovery'
import { useSettingsStore } from '@/lib/store/settings'
import type { UtilityInfo } from '@/lib/api/utility-discovery'

const ICON_MAP: Record<string, React.ElementType> = {
  electricity: Zap,
  natural_gas: Flame,
  heating_oil: Droplets,
  community_solar: Sun,
}

const ROUTE_MAP: Record<string, string> = {
  electricity: '/prices',
  natural_gas: '/gas-rates',
  heating_oil: '/prices',
  community_solar: '/community-solar',
}

const STATUS_BADGE: Record<string, { label: string; className: string }> = {
  deregulated: { label: 'Supplier choice', className: 'bg-green-100 text-green-700' },
  regulated: { label: 'Regulated', className: 'bg-gray-100 text-gray-600' },
  available: { label: 'Available', className: 'bg-blue-100 text-blue-700' },
}

interface UtilityDiscoveryCardProps {
  onDismiss?: () => void
}

export function UtilityDiscoveryCard({ onDismiss }: UtilityDiscoveryCardProps) {
  const region = useSettingsStore((s) => s.region)
  const trackedTypes = useSettingsStore((s) => s.utilityTypes)

  // Derive state code from region (e.g. "us_ny" -> "NY")
  const stateCode = region?.startsWith('us_') ? region.slice(3).toUpperCase() : null

  const { data, isLoading } = useUtilityDiscovery(stateCode)

  if (isLoading || !data) return null

  // Filter to utilities the user isn't tracking yet
  const trackedSet = new Set(trackedTypes)
  const untracked = data.utilities.filter(
    (u: UtilityInfo) => !trackedSet.has(u.utility_type as typeof trackedTypes[number])
  )

  if (untracked.length === 0) return null

  return (
    <div className="rounded-lg border border-blue-200 bg-blue-50 p-4">
      <div className="mb-3 flex items-center justify-between">
        <h3 className="font-semibold text-blue-900">
          More utilities available in your area
        </h3>
        {onDismiss && (
          <button
            onClick={onDismiss}
            className="rounded p-1 text-blue-400 hover:bg-blue-100 hover:text-blue-600 transition-colors"
            aria-label="Dismiss utility suggestions"
          >
            <X className="h-4 w-4" />
          </button>
        )}
      </div>
      <p className="mb-4 text-sm text-blue-700">
        Track more utility types to maximize your savings.
      </p>
      <div className="space-y-2">
        {untracked.map((utility: UtilityInfo) => {
          const Icon = ICON_MAP[utility.utility_type] || Zap
          const route = ROUTE_MAP[utility.utility_type] || '/settings'
          const badge = STATUS_BADGE[utility.status]

          return (
            <Link
              key={utility.utility_type}
              href={route}
              className="flex items-center gap-3 rounded-lg border border-blue-100 bg-white p-3 transition-colors hover:border-blue-300 hover:bg-blue-50"
            >
              <div className="flex h-8 w-8 items-center justify-center rounded-lg bg-blue-100">
                <Icon className="h-4 w-4 text-blue-600" />
              </div>
              <div className="flex-1 min-w-0">
                <div className="flex items-center gap-2">
                  <span className="font-medium text-gray-900">{utility.label}</span>
                  {badge && (
                    <span className={cn('rounded-full px-2 py-0.5 text-xs font-medium', badge.className)}>
                      {badge.label}
                    </span>
                  )}
                </div>
                <p className="text-xs text-gray-500 truncate">{utility.description}</p>
              </div>
              <ChevronRight className="h-4 w-4 flex-shrink-0 text-gray-400" />
            </Link>
          )
        })}
      </div>
    </div>
  )
}
