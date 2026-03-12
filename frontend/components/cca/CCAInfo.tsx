'use client'

import { useCCAInfo } from '@/lib/hooks/useCCA'

interface CCAInfoProps {
  ccaId: string
  onClose?: () => void
}

const ENERGY_COLORS: Record<string, string> = {
  solar: 'bg-yellow-400',
  wind: 'bg-blue-400',
  hydro: 'bg-cyan-400',
  nuclear: 'bg-purple-400',
  gas: 'bg-gray-400',
  coal: 'bg-gray-600',
  other: 'bg-gray-300',
}

export function CCAInfo({ ccaId, onClose }: CCAInfoProps) {
  const { data, isLoading, error } = useCCAInfo(ccaId)

  if (isLoading) {
    return <div className="animate-pulse rounded-lg bg-gray-100 p-6 h-48" />
  }

  if (error || !data) return null

  const generationMix = data.generation_mix
    ? Object.entries(data.generation_mix).sort(([, a], [, b]) => b - a)
    : []

  return (
    <div className="rounded-lg border p-6">
      <div className="flex items-start justify-between">
        <div>
          <h3 className="text-lg font-semibold text-gray-900">{data.program_name}</h3>
          <p className="text-sm text-gray-500">
            {data.provider} &middot; {data.municipality}, {data.state}
          </p>
        </div>
        {onClose && (
          <button
            onClick={onClose}
            className="text-gray-400 hover:text-gray-600"
            aria-label="Close CCA info"
          >
            &times;
          </button>
        )}
      </div>

      {data.rate_vs_default_pct !== null && (
        <div className="mt-3">
          <span
            className={`inline-flex items-center rounded-full px-2.5 py-0.5 text-xs font-medium ${
              data.rate_vs_default_pct < 0
                ? 'bg-green-100 text-green-800'
                : data.rate_vs_default_pct === 0
                  ? 'bg-gray-100 text-gray-800'
                  : 'bg-amber-100 text-amber-800'
            }`}
          >
            {data.rate_vs_default_pct < 0
              ? `${Math.abs(data.rate_vs_default_pct)}% below default rate`
              : data.rate_vs_default_pct === 0
                ? 'Same as default rate'
                : `${data.rate_vs_default_pct}% above default rate`}
          </span>
        </div>
      )}

      {generationMix.length > 0 && (
        <div className="mt-4">
          <p className="text-sm font-medium text-gray-700">Generation Mix</p>
          <div className="mt-2 flex h-3 overflow-hidden rounded-full bg-gray-200">
            {generationMix.map(([source, pct]) => (
              <div
                key={source}
                className={`${ENERGY_COLORS[source] || ENERGY_COLORS.other}`}
                style={{ width: `${pct}%` }}
                title={`${source}: ${pct}%`}
              />
            ))}
          </div>
          <div className="mt-2 flex flex-wrap gap-x-4 gap-y-1">
            {generationMix.map(([source, pct]) => (
              <div key={source} className="flex items-center gap-1.5 text-xs text-gray-600">
                <span className={`inline-block h-2 w-2 rounded-full ${ENERGY_COLORS[source] || ENERGY_COLORS.other}`} />
                <span className="capitalize">{source}</span>
                <span className="text-gray-400">{pct}%</span>
              </div>
            ))}
          </div>
        </div>
      )}

      {(data.opt_out_url || data.program_url) && (
        <div className="mt-4 flex gap-3 border-t pt-4">
          {data.program_url && (
            <a
              href={data.program_url}
              target="_blank"
              rel="noopener noreferrer"
              className="text-sm font-medium text-blue-700 hover:text-blue-900"
            >
              Program Website
            </a>
          )}
          {data.opt_out_url && (
            <a
              href={data.opt_out_url}
              target="_blank"
              rel="noopener noreferrer"
              className="text-sm font-medium text-gray-600 hover:text-gray-900"
            >
              Opt-Out Information
            </a>
          )}
        </div>
      )}
    </div>
  )
}
