'use client'

import { useWaterBenchmark } from '@/lib/hooks/useWater'

interface WaterRateBenchmarkProps {
  state: string
}

export function WaterRateBenchmark({ state }: WaterRateBenchmarkProps) {
  const { data, isLoading, error } = useWaterBenchmark(state)

  if (isLoading) {
    return (
      <div className="space-y-3">
        {[1, 2, 3].map((i) => (
          <div key={i} className="animate-pulse rounded-lg bg-gray-100 h-12" />
        ))}
      </div>
    )
  }

  if (error || !data) return null

  return (
    <div className="space-y-4">
      <h3 className="text-lg font-semibold text-gray-900">
        Water Rate Benchmark — {state}
      </h3>

      {/* Summary cards */}
      <div className="grid gap-4 sm:grid-cols-3">
        <div className="rounded-lg border bg-cyan-50 p-4">
          <p className="text-sm font-medium text-cyan-700">Average Monthly</p>
          <p className="text-xl font-bold text-cyan-900">
            ${data.avg_monthly_cost?.toFixed(2) ?? '—'}
          </p>
        </div>
        <div className="rounded-lg border bg-green-50 p-4">
          <p className="text-sm font-medium text-green-700">Lowest</p>
          <p className="text-xl font-bold text-green-900">
            ${data.min_monthly_cost?.toFixed(2) ?? '—'}
          </p>
        </div>
        <div className="rounded-lg border bg-red-50 p-4">
          <p className="text-sm font-medium text-red-700">Highest</p>
          <p className="text-xl font-bold text-red-900">
            ${data.max_monthly_cost?.toFixed(2) ?? '—'}
          </p>
        </div>
      </div>

      <p className="text-xs text-gray-500">
        Based on {data.usage_gallons.toLocaleString()} gallons/month typical household usage
        across {data.municipalities} municipalities
      </p>

      {/* Municipality breakdown */}
      {data.rates.length > 0 && (
        <div className="rounded-lg border">
          <div className="border-b px-4 py-2 bg-gray-50">
            <p className="text-sm font-medium text-gray-700">Municipality Comparison</p>
          </div>
          <div className="divide-y">
            {data.rates.map((r) => {
              const avgCost = data.avg_monthly_cost ?? 0
              const diff = avgCost > 0
                ? ((r.monthly_cost - avgCost) / avgCost) * 100
                : 0

              return (
                <div key={r.municipality} className="flex items-center justify-between px-4 py-3">
                  <div>
                    <p className="font-medium text-gray-900">{r.municipality}</p>
                    <p className="text-xs text-gray-500">
                      Base charge: ${r.base_charge.toFixed(2)}/mo
                    </p>
                  </div>
                  <div className="text-right">
                    <p className="font-semibold text-gray-900">
                      ${r.monthly_cost.toFixed(2)}/mo
                    </p>
                    <span
                      className={`text-xs font-medium ${
                        diff < -2 ? 'text-green-600' : diff > 2 ? 'text-red-600' : 'text-gray-500'
                      }`}
                    >
                      {diff > 0 ? '+' : ''}{diff.toFixed(1)}% vs avg
                    </span>
                  </div>
                </div>
              )
            })}
          </div>
        </div>
      )}
    </div>
  )
}
