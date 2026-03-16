'use client'

import {
  useAlertPreferences,
  useUpsertAlertPreference,
} from '@/lib/hooks/useRateChanges'

const UTILITY_TYPES = [
  { key: 'electricity', label: 'Electricity' },
  { key: 'natural_gas', label: 'Natural Gas' },
  { key: 'heating_oil', label: 'Heating Oil' },
  { key: 'propane', label: 'Propane' },
  { key: 'community_solar', label: 'Community Solar' },
]

const CADENCE_OPTIONS = ['realtime', 'daily', 'weekly'] as const

export function AlertPreferences() {
  const { data, isLoading, error } = useAlertPreferences()
  const mutation = useUpsertAlertPreference()

  if (isLoading) {
    return <div className="h-48 animate-pulse rounded-lg bg-muted" />
  }

  if (error) {
    return <p className="text-sm text-danger-500">Failed to load preferences.</p>
  }

  const prefs = data?.preferences ?? []

  const getPref = (utilityType: string) =>
    prefs.find((p) => p.utility_type === utilityType)

  const handleToggle = (utilityType: string, currentEnabled: boolean) => {
    mutation.mutate({ utility_type: utilityType, enabled: !currentEnabled })
  }

  const handleCadenceChange = (utilityType: string, cadence: string) => {
    mutation.mutate({ utility_type: utilityType, cadence })
  }

  return (
    <div className="space-y-3">
      <h3 className="text-lg font-semibold">Alert Preferences</h3>
      {UTILITY_TYPES.map(({ key, label }) => {
        const pref = getPref(key)
        const enabled = pref?.enabled ?? true
        const cadence = pref?.cadence ?? 'daily'

        return (
          <div
            key={key}
            className="flex items-center justify-between rounded-lg border p-3"
          >
            <div className="flex items-center gap-3">
              <button
                type="button"
                role="switch"
                aria-checked={enabled}
                aria-label={`Toggle ${label} alerts`}
                onClick={() => handleToggle(key, enabled)}
                className={`relative h-6 w-11 rounded-full transition-colors ${
                  enabled ? 'bg-primary-600' : 'bg-gray-300'
                }`}
              >
                <span
                  className={`absolute left-0.5 top-0.5 h-5 w-5 rounded-full bg-white transition-transform ${
                    enabled ? 'translate-x-5' : 'translate-x-0'
                  }`}
                />
              </button>
              <span className="text-sm font-medium">{label}</span>
            </div>

            <select
              value={cadence}
              onChange={(e) => handleCadenceChange(key, e.target.value)}
              className="rounded border px-2 py-1 text-sm"
              aria-label={`${label} cadence`}
              disabled={!enabled}
            >
              {CADENCE_OPTIONS.map((c) => (
                <option key={c} value={c}>
                  {c.charAt(0).toUpperCase() + c.slice(1)}
                </option>
              ))}
            </select>
          </div>
        )
      })}
      {mutation.isPending && (
        <p className="text-xs text-muted-foreground">Saving...</p>
      )}
    </div>
  )
}
