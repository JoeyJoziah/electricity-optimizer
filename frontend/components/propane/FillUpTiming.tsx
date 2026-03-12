'use client'

import { usePropaneTiming } from '@/lib/hooks/usePropane'

interface FillUpTimingProps {
  state: string
}

const TIMING_CONFIG = {
  good: {
    border: 'border-green-200',
    bg: 'bg-green-50',
    text: 'text-green-800',
    label: 'Good Time to Buy',
  },
  wait: {
    border: 'border-amber-200',
    bg: 'bg-amber-50',
    text: 'text-amber-800',
    label: 'Consider Waiting',
  },
  neutral: {
    border: 'border-gray-200',
    bg: 'bg-gray-50',
    text: 'text-gray-800',
    label: 'Average Pricing',
  },
} as const

export function FillUpTiming({ state }: FillUpTimingProps) {
  const { data, isLoading, error } = usePropaneTiming(state)

  if (isLoading) {
    return <div className="animate-pulse rounded-lg bg-gray-100 h-24" />
  }

  if (error || !data) return null

  const config = TIMING_CONFIG[data.timing]

  return (
    <div className={`rounded-lg border ${config.border} ${config.bg} p-4`}>
      <div className="flex items-center justify-between">
        <h3 className={`text-sm font-semibold ${config.text}`}>
          Fill-Up Timing
        </h3>
        <span className={`text-xs font-medium px-2 py-0.5 rounded-full ${config.bg} ${config.text} border ${config.border}`}>
          {config.label}
        </span>
      </div>
      <p className={`mt-2 text-sm ${config.text}`}>{data.advice}</p>
      <div className="mt-3 flex gap-6 text-sm">
        <div>
          <p className="text-gray-500">Current</p>
          <p className="font-semibold">${data.current_price.toFixed(2)}/gal</p>
        </div>
        <div>
          <p className="text-gray-500">12-Month Avg</p>
          <p className="font-semibold">${data.avg_price.toFixed(2)}/gal</p>
        </div>
      </div>
    </div>
  )
}
