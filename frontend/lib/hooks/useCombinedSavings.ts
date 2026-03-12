import { useQuery } from '@tanstack/react-query'
import { getCombinedSavings } from '../api/savings'

export function useCombinedSavings() {
  return useQuery({
    queryKey: ['savings', 'combined'],
    queryFn: getCombinedSavings,
    staleTime: 1000 * 60 * 5, // 5 min
  })
}
