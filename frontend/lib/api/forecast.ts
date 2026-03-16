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
  signal?: AbortSignal,
): Promise<ForecastResponse> {
  const params: Record<string, string> = {}
  if (state) params.state = state
  if (horizonDays) params.horizon_days = String(horizonDays)
  return apiClient.get<ForecastResponse>(`/forecast/${utilityType}`, params, { signal })
}

export async function getForecastTypes(signal?: AbortSignal): Promise<ForecastTypesResponse> {
  return apiClient.get<ForecastTypesResponse>('/forecast', undefined, { signal })
}
