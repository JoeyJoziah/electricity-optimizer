import { useQuery } from '@tanstack/react-query'
import { exportRates, getExportTypes } from '../api/export'

export function useExportRates(
  utilityType?: string,
  format: 'json' | 'csv' = 'json',
  state?: string,
  enabled = false,
) {
  return useQuery({
    queryKey: ['export', 'rates', utilityType, format, state],
    queryFn: ({ signal }) => exportRates(utilityType!, format, state, undefined, undefined, signal),
    enabled: enabled && !!utilityType,
    staleTime: 1000 * 60 * 5, // 5 minutes
  })
}

export function useExportTypes() {
  return useQuery({
    queryKey: ['export', 'types'],
    queryFn: ({ signal }) => getExportTypes(signal),
    staleTime: 1000 * 60 * 60 * 24, // 24 hours
  })
}
