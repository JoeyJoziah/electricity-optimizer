import { apiClient } from './client'

export interface SavingsOpportunity {
  utility_type: string
  action: string
  monthly_savings: number
  annual_savings: number
  difficulty: 'easy' | 'moderate' | 'hard'
}

export interface UtilitySpend {
  utility_type: string
  unit: string
  current_rate: number
  monthly_consumption: number
  consumption_unit: string
  monthly_cost: number
  savings: SavingsOpportunity | null
}

export interface OptimizationReport {
  state: string
  generated_at: string
  utilities: UtilitySpend[]
  total_monthly_spend: number
  total_annual_spend: number
  savings_opportunities: SavingsOpportunity[]
  total_potential_monthly_savings: number
  total_potential_annual_savings: number
  utility_count: number
}

export async function getOptimizationReport(
  state: string,
): Promise<OptimizationReport> {
  return apiClient.get<OptimizationReport>('/reports/optimization', { state })
}
