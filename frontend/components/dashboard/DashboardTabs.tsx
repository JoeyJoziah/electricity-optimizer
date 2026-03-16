'use client'

import React from 'react'
import { useSearchParams, useRouter } from 'next/navigation'
import { useSettingsStore } from '@/lib/store/settings'
import { AllUtilitiesTab } from './AllUtilitiesTab'
import { UtilityTabShell } from './UtilityTabShell'

interface TabDef {
  key: string
  label: string
}

const ALL_TABS: TabDef[] = [
  { key: 'all', label: 'All Utilities' },
  { key: 'electricity', label: 'Electricity' },
  { key: 'natural_gas', label: 'Natural Gas' },
  { key: 'heating_oil', label: 'Heating Oil' },
  { key: 'propane', label: 'Propane' },
  { key: 'community_solar', label: 'Community Solar' },
  { key: 'water', label: 'Water' },
]

function getDefaultTab(userUtilities: string[]): string {
  if (userUtilities.length === 1) return userUtilities[0]
  return 'all'
}

export default function DashboardTabs() {
  const searchParams = useSearchParams()
  const router = useRouter()
  const userUtilities = useSettingsStore((s) => s.utilityTypes)

  // Visible tabs: "All" always shows if 2+ utilities, plus each user utility
  const visibleTabs = React.useMemo(() => {
    const enabled = new Set<string>(userUtilities)
    return ALL_TABS.filter((t) => {
      if (t.key === 'all') return userUtilities.length >= 2
      return enabled.has(t.key)
    })
  }, [userUtilities])

  const tabFromUrl = searchParams.get('tab')
  const defaultTab = getDefaultTab(userUtilities)
  const activeTab = tabFromUrl && visibleTabs.some((t) => t.key === tabFromUrl)
    ? tabFromUrl
    : defaultTab

  const setTab = React.useCallback(
    (key: string) => {
      const params = new URLSearchParams(searchParams.toString())
      params.set('tab', key)
      router.replace(`?${params.toString()}`, { scroll: false })
    },
    [searchParams, router],
  )

  return (
    <div data-testid="dashboard-tabs">
      {/* Tab bar */}
      <div className="relative border-b border-gray-200">
        {/* Gradient fade affordance for mobile scroll */}
        <div className="pointer-events-none absolute right-0 top-0 bottom-0 w-8 bg-gradient-to-l from-white to-transparent sm:hidden" />
        <nav
          className="flex gap-0 overflow-x-auto scrollbar-hide px-4 sm:px-6"
          aria-label="Dashboard tabs"
          data-testid="tab-bar"
        >
          {visibleTabs.map((tab) => (
            <button
              key={tab.key}
              onClick={() => setTab(tab.key)}
              className={`whitespace-nowrap px-4 py-3 text-sm font-medium transition-colors ${
                activeTab === tab.key
                  ? 'border-b-2 border-primary-600 text-primary-600'
                  : 'text-gray-500 hover:text-gray-700'
              }`}
              data-testid={`tab-${tab.key}`}
              aria-selected={activeTab === tab.key}
              role="tab"
            >
              {tab.label}
            </button>
          ))}
        </nav>
      </div>

      {/* Tab content */}
      <div className="p-6" data-testid="tab-content">
        {activeTab === 'all' ? (
          <AllUtilitiesTab />
        ) : (
          <UtilityTabShell utilityType={activeTab} />
        )}
      </div>
    </div>
  )
}
