'use client'

import { useWaterTips } from '@/lib/hooks/useWater'

const DIFFICULTY_COLORS: Record<string, string> = {
  easy: 'bg-success-100 text-success-700',
  moderate: 'bg-warning-100 text-warning-700',
  hard: 'bg-danger-100 text-danger-700',
}

export function ConservationTips() {
  const { data, isLoading, error } = useWaterTips()

  if (isLoading) {
    return (
      <div className="space-y-3">
        {[1, 2, 3].map((i) => (
          <div key={i} className="animate-pulse rounded-lg bg-gray-100 h-16" />
        ))}
      </div>
    )
  }

  if (error || !data) return null

  const tips = data.tips || []
  const indoorTips = tips.filter((t) => t.category === 'Indoor')
  const outdoorTips = tips.filter((t) => t.category === 'Outdoor')
  const monitoringTips = tips.filter((t) => t.category === 'Monitoring')

  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between">
        <h3 className="text-lg font-semibold text-gray-900">Conservation Tips</h3>
        <span className="text-sm text-cyan-600 font-medium">
          Save up to {data.estimated_annual_savings_gallons.toLocaleString()} gal/year
        </span>
      </div>

      {[
        { label: 'Indoor', tips: indoorTips },
        { label: 'Outdoor', tips: outdoorTips },
        { label: 'Monitoring', tips: monitoringTips },
      ]
        .filter((group) => group.tips.length > 0)
        .map((group) => (
          <div key={group.label}>
            <p className="text-sm font-medium text-gray-600 mb-2">{group.label}</p>
            <div className="space-y-2">
              {group.tips.map((tip) => (
                <div key={tip.title} className="rounded-lg border p-3">
                  <div className="flex items-center justify-between mb-1">
                    <p className="font-medium text-gray-900">{tip.title}</p>
                    <span
                      className={`text-xs px-2 py-0.5 rounded-full font-medium ${
                        DIFFICULTY_COLORS[tip.difficulty] || 'bg-gray-100 text-gray-700'
                      }`}
                    >
                      {tip.difficulty}
                    </span>
                  </div>
                  <p className="text-sm text-gray-600">{tip.description}</p>
                  {tip.estimated_savings_gallons > 0 && (
                    <p className="text-xs text-cyan-600 mt-1">
                      Saves ~{tip.estimated_savings_gallons.toLocaleString()} gallons/year
                    </p>
                  )}
                </div>
              ))}
            </div>
          </div>
        ))}
    </div>
  )
}
