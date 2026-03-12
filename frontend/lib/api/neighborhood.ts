import { apiClient } from './client'

export interface NeighborhoodComparison {
  region: string
  utility_type: string
  user_count: number
  percentile: number | null
  user_rate: number | null
  cheapest_supplier: string | null
  cheapest_rate: number | null
  avg_rate: number | null
  potential_savings: number | null
}

export async function getNeighborhoodComparison(
  region: string,
  utilityType: string,
): Promise<NeighborhoodComparison> {
  return apiClient.get<NeighborhoodComparison>(
    '/neighborhood/compare',
    { region, utility_type: utilityType },
  )
}
