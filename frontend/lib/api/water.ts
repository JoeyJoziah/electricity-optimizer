import { apiClient } from '../api-client'

export interface WaterRateTier {
  limit_gallons: number | null
  rate_per_gallon: number
}

export interface WaterRate {
  id: string
  municipality: string
  state: string
  rate_tiers: WaterRateTier[]
  base_charge: number
  unit: string
  effective_date: string | null
  source_url: string | null
  updated_at: string | null
}

export interface WaterRatesResponse {
  rates: WaterRate[]
  count?: number
}

export interface WaterCostBreakdown {
  tier: number
  gallons: number
  rate_per_gallon: number
  charge: number
}

export interface WaterBenchmarkRate {
  municipality: string
  monthly_cost: number
  base_charge: number
}

export interface WaterBenchmark {
  state: string
  municipalities: number
  usage_gallons: number
  avg_monthly_cost: number | null
  min_monthly_cost: number | null
  max_monthly_cost: number | null
  rates: WaterBenchmarkRate[]
}

export interface WaterTip {
  category: string
  title: string
  description: string
  estimated_savings_gallons: number
  difficulty: string
}

export interface WaterTipsResponse {
  tips: WaterTip[]
  count: number
  estimated_annual_savings_gallons: number
}

export async function getWaterRates(
  state?: string,
): Promise<WaterRatesResponse> {
  return apiClient.get<WaterRatesResponse>(
    '/rates/water',
    state ? { state } : {},
  )
}

export async function getWaterBenchmark(
  state: string,
  usageGallons?: number,
): Promise<WaterBenchmark> {
  return apiClient.get<WaterBenchmark>(
    '/rates/water/benchmark',
    { state, ...(usageGallons ? { usage_gallons: String(usageGallons) } : {}) },
  )
}

export async function getWaterTips(): Promise<WaterTipsResponse> {
  return apiClient.get<WaterTipsResponse>('/rates/water/tips')
}
