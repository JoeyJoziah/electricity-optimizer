'use client'

import { useCCACompare } from '@/lib/hooks/useCCA'

interface CCAComparisonProps {
  ccaId: string
  defaultRate: number
}

export function CCAComparison({ ccaId, defaultRate }: CCAComparisonProps) {
  const { data, isLoading, error } = useCCACompare(ccaId, defaultRate)

  if (isLoading) {
    return <div className="animate-pulse rounded-lg bg-gray-100 p-4 h-32" />
  }

  if (error || !data) return null

  return (
    <div className="rounded-lg border p-4">
      <h3 className="text-sm font-semibold text-gray-900">Rate Comparison</h3>
      <p className="mt-1 text-xs text-gray-500">
        {data.program_name} by {data.provider}
      </p>

      <div className="mt-3 grid grid-cols-2 gap-4">
        <div>
          <p className="text-xs text-gray-500">Default Rate</p>
          <p className="text-lg font-bold text-gray-900">
            ${data.default_rate.toFixed(4)}/kWh
          </p>
        </div>
        <div>
          <p className="text-xs text-gray-500">CCA Rate</p>
          <p className={`text-lg font-bold ${data.is_cheaper ? 'text-green-600' : 'text-red-600'}`}>
            ${data.cca_rate.toFixed(4)}/kWh
          </p>
        </div>
      </div>

      <div className="mt-3 rounded bg-gray-50 p-2">
        <p className="text-sm">
          {data.is_cheaper ? (
            <span className="text-green-700">
              Saving ~${data.estimated_monthly_savings.toFixed(2)}/month
              ({Math.abs(data.rate_difference_pct)}% less)
            </span>
          ) : (
            <span className="text-amber-700">
              Costing ~${Math.abs(data.estimated_monthly_savings).toFixed(2)}/month more
              ({data.rate_difference_pct}% higher)
            </span>
          )}
        </p>
      </div>
    </div>
  )
}
