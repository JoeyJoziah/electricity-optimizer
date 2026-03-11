import { apiClient } from './client'

export interface UtilityInfo {
  utility_type: string
  label: string
  status: 'deregulated' | 'regulated' | 'available'
  description: string
}

export interface UtilityDiscoveryResponse {
  state: string
  count: number
  utilities: UtilityInfo[]
}

export interface CompletionResponse {
  state: string
  tracked: number
  available: number
  percent: number
  missing: UtilityInfo[]
}

export async function discoverUtilities(
  state: string
): Promise<UtilityDiscoveryResponse> {
  return apiClient.get<UtilityDiscoveryResponse>('/utility-discovery/discover', {
    state,
  })
}

export async function getUtilityCompletion(
  state: string,
  tracked: string[]
): Promise<CompletionResponse> {
  return apiClient.get<CompletionResponse>('/utility-discovery/completion', {
    state,
    tracked: tracked.join(','),
  })
}
