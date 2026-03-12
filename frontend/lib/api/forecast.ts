import { apiClient } from './client'

export interface ForecastResponse {
  utility_type: string
  state: string | null
  unit: string
  current_rate: number
  forecasted_rate: number
  horizon_days: number
  trend: 'increasing' | 'decreasing' | 'stable'
  percent_change: number
  confidence: number
  model: string
  data_points: number
  r_squared: number
  generated_at: string
  error?: string
}

export interface ForecastTypesResponse {
  supported_types: string[]
  description: string
}

export async function getForecast(
  utilityType: string,
  state?: string,
  horizonDays?: number,
): Promise<ForecastResponse> {
  const params: Record<string, string> = {}
  if (state) params.state = state
  if (horizonDays) params.horizon_days = String(horizonDays)
  return apiClient.get<ForecastResponse>(`/forecast/${utilityType}`, params)
}

export async function getForecastTypes(): Promise<ForecastTypesResponse> {
  return apiClient.get<ForecastTypesResponse>('/forecast')
}
