'use client'

import React from 'react'
import { useUtilityCompletion } from '@/lib/hooks/useUtilityDiscovery'
import { useSettingsStore } from '@/lib/store/settings'
import { chartColor } from '@/lib/constants/chartTokens'

export function CompletionProgress() {
  const region = useSettingsStore((s) => s.region)
  const trackedTypes = useSettingsStore((s) => s.utilityTypes)

  const stateCode = region?.startsWith('us_') ? region.slice(3).toUpperCase() : null

  const { data } = useUtilityCompletion(stateCode, trackedTypes)

  if (!data || data.percent === 100) return null

  const circumference = 2 * Math.PI * 18 // r=18
  const dashOffset = circumference - (data.percent / 100) * circumference

  return (
    <div className="flex items-center gap-3 rounded-lg border border-gray-200 bg-white p-3">
      {/* Progress ring */}
      <div className="relative h-12 w-12 flex-shrink-0">
        <svg className="h-12 w-12 -rotate-90" viewBox="0 0 40 40">
          <circle
            cx="20"
            cy="20"
            r="18"
            fill="none"
            stroke={chartColor.grid}
            strokeWidth="3"
          />
          <circle
            cx="20"
            cy="20"
            r="18"
            fill="none"
            stroke={chartColor.primary}
            strokeWidth="3"
            strokeLinecap="round"
            strokeDasharray={circumference}
            strokeDashoffset={dashOffset}
            className="transition-all duration-500"
          />
        </svg>
        <span className="absolute inset-0 flex items-center justify-center text-xs font-bold text-gray-700">
          {data.tracked}/{data.available}
        </span>
      </div>
      <div className="min-w-0">
        <p className="text-sm font-medium text-gray-900">
          Utilities tracked
        </p>
        <p className="text-xs text-gray-500">
          {data.missing.length} more {data.missing.length === 1 ? 'utility' : 'utilities'} available in your area
        </p>
      </div>
    </div>
  )
}
