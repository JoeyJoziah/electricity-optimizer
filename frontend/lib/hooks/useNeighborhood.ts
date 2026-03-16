import { useQuery } from '@tanstack/react-query'
import { getNeighborhoodComparison } from '../api/neighborhood'

export function useNeighborhoodComparison(region?: string, utilityType?: string) {
  return useQuery({
    queryKey: ['neighborhood', 'compare', region, utilityType],
    queryFn: ({ signal }) => getNeighborhoodComparison(region!, utilityType!, signal),
    enabled: !!region && !!utilityType,
    staleTime: 1000 * 60 * 10, // 10 min
  })
}
