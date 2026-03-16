import { useQuery } from '@tanstack/react-query'
import { getOptimizationReport } from '../api/reports'

export function useOptimizationReport(state?: string) {
  return useQuery({
    queryKey: ['reports', 'optimization', state],
    queryFn: ({ signal }) => getOptimizationReport(state!, signal),
    enabled: !!state,
    staleTime: 1000 * 60 * 60, // 1 hour
  })
}
