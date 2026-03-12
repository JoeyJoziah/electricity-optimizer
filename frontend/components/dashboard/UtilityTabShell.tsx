'use client'

import React from 'react'
import dynamic from 'next/dynamic'

// Lazy-load each utility dashboard to avoid loading all at once
const DashboardContent = dynamic(
  () => import('@/components/dashboard/DashboardContent'),
  { ssr: false }
)
const HeatingOilDashboard = dynamic(
  () =>
    import('@/components/heating-oil/HeatingOilDashboard').then((m) => ({
      default: m.HeatingOilDashboard,
    })),
  { ssr: false }
)
const PropaneDashboard = dynamic(
  () =>
    import('@/components/propane/PropaneDashboard').then((m) => ({
      default: m.PropaneDashboard,
    })),
  { ssr: false }
)
const WaterDashboard = dynamic(
  () =>
    import('@/components/water/WaterDashboard').then((m) => ({
      default: m.WaterDashboard,
    })),
  { ssr: false }
)
const CommunitySolarContent = dynamic(
  () => import('@/components/community-solar/CommunitySolarContent'),
  { ssr: false }
)

const UTILITY_DASHBOARDS: Record<string, React.ComponentType> = {
  electricity: DashboardContent,
  heating_oil: HeatingOilDashboard,
  propane: PropaneDashboard,
  water: WaterDashboard,
  community_solar: CommunitySolarContent,
}

const UTILITY_LABELS: Record<string, string> = {
  electricity: 'Electricity',
  natural_gas: 'Natural Gas',
  heating_oil: 'Heating Oil',
  propane: 'Propane',
  community_solar: 'Community Solar',
  water: 'Water',
}

interface UtilityTabShellProps {
  utilityType: string
}

export function UtilityTabShell({ utilityType }: UtilityTabShellProps) {
  const Dashboard = UTILITY_DASHBOARDS[utilityType]

  if (!Dashboard) {
    return (
      <div
        data-testid={`utility-shell-placeholder-${utilityType}`}
        className="flex flex-col items-center justify-center py-16 text-center"
      >
        <h3 className="text-lg font-medium text-gray-700">
          {UTILITY_LABELS[utilityType] || utilityType}
        </h3>
        <p className="mt-2 text-sm text-gray-400">
          Dashboard coming soon. Check back for detailed analytics.
        </p>
      </div>
    )
  }

  return (
    <div data-testid={`utility-shell-${utilityType}`}>
      <Dashboard />
    </div>
  )
}
