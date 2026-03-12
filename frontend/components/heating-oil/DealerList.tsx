'use client'

import { useHeatingOilDealers } from '@/lib/hooks/useHeatingOil'

interface DealerListProps {
  state: string
}

export function DealerList({ state }: DealerListProps) {
  const { data, isLoading, error } = useHeatingOilDealers(state)

  if (isLoading) {
    return <div className="animate-pulse rounded-lg bg-gray-100 h-32" />
  }

  if (error || !data || data.dealers.length === 0) return null

  return (
    <div className="rounded-lg border p-4">
      <h3 className="text-sm font-semibold text-gray-900">
        Local Dealers &mdash; {state}
      </h3>

      <div className="mt-3 divide-y">
        {data.dealers.map((dealer) => (
          <div key={dealer.id} className="py-3 first:pt-0 last:pb-0">
            <div className="flex items-start justify-between">
              <div>
                <p className="font-medium text-gray-900">{dealer.name}</p>
                {dealer.city && (
                  <p className="text-sm text-gray-500">{dealer.city}, {state}</p>
                )}
              </div>
              {dealer.rating && (
                <span className="inline-flex items-center rounded-full bg-yellow-100 px-2 py-0.5 text-xs font-medium text-yellow-800">
                  {dealer.rating.toFixed(1)}
                </span>
              )}
            </div>
            <div className="mt-1 flex gap-3 text-sm">
              {dealer.phone && (
                <a
                  href={`tel:${dealer.phone}`}
                  className="text-blue-700 hover:text-blue-900"
                >
                  {dealer.phone}
                </a>
              )}
              {dealer.website && (
                <a
                  href={dealer.website}
                  target="_blank"
                  rel="noopener noreferrer"
                  className="text-blue-700 hover:text-blue-900"
                >
                  Website
                </a>
              )}
            </div>
          </div>
        ))}
      </div>
    </div>
  )
}
