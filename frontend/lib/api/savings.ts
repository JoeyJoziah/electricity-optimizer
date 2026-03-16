import { apiClient } from './client'

export interface SavingsBreakdown {
  utility_type: string
  monthly_savings: number
}

export interface CombinedSavingsResponse {
  total_monthly_savings: number
  breakdown: SavingsBreakdown[]
  savings_rank_pct: number | null
}

export async function getCombinedSavings(signal?: AbortSignal): Promise<CombinedSavingsResponse> {
  return apiClient.get<CombinedSavingsResponse>('/savings/combined', undefined, { signal })
}
