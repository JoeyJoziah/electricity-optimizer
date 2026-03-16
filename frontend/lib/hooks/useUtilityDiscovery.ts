import { useQuery } from '@tanstack/react-query'
import { discoverUtilities, getUtilityCompletion } from '@/lib/api/utility-discovery'
import type { UtilityDiscoveryResponse, CompletionResponse } from '@/lib/api/utility-discovery'

/**
 * Discover available utility types for a state.
 */
export function useUtilityDiscovery(state: string | null | undefined) {
  return useQuery<UtilityDiscoveryResponse>({
    queryKey: ['utility-discovery', state],
    queryFn: ({ signal }) => discoverUtilities(state!, signal),
    enabled: !!state,
    staleTime: 1000 * 60 * 60, // 1 hour — deregulation data rarely changes
  })
}

/**
 * Get utility tracking completion status for a user.
 */
export function useUtilityCompletion(
  state: string | null | undefined,
  trackedTypes: string[]
) {
  return useQuery<CompletionResponse>({
    queryKey: ['utility-completion', state, trackedTypes.join(',')],
    queryFn: ({ signal }) => getUtilityCompletion(state!, trackedTypes, signal),
    enabled: !!state && trackedTypes.length > 0,
    staleTime: 1000 * 60 * 60,
  })
}
