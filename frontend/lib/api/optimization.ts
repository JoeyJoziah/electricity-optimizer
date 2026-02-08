/**
 * Optimization API functions
 */

import { apiClient } from './client'
import type { Appliance, OptimizationResult, OptimizationSchedule } from '@/types'

export interface GetOptimalScheduleRequest {
  appliances: Appliance[]
  region?: string
  date?: string
}

export interface GetOptimalScheduleResponse {
  schedules: OptimizationSchedule[]
  totalSavings: number
  totalCost: number
}

/**
 * Get optimal schedule for appliances
 */
export async function getOptimalSchedule(
  request: GetOptimalScheduleRequest
): Promise<GetOptimalScheduleResponse> {
  return apiClient.post<GetOptimalScheduleResponse>(
    '/optimization/schedule',
    request
  )
}

/**
 * Get optimization result for a specific date
 */
export async function getOptimizationResult(
  date: string,
  region: string = 'uk'
): Promise<OptimizationResult> {
  return apiClient.get<OptimizationResult>('/optimization/result', {
    date,
    region,
  })
}

/**
 * Save user's appliance configuration
 */
export async function saveAppliances(
  appliances: Appliance[]
): Promise<{ success: boolean }> {
  return apiClient.post('/optimization/appliances', { appliances })
}

/**
 * Get saved appliances
 */
export async function getAppliances(): Promise<{ appliances: Appliance[] }> {
  return apiClient.get('/optimization/appliances')
}

/**
 * Calculate potential savings for a set of appliances
 */
export async function calculatePotentialSavings(
  appliances: Appliance[],
  region: string = 'uk'
): Promise<{
  dailySavings: number
  weeklySavings: number
  monthlySavings: number
  annualSavings: number
}> {
  return apiClient.post('/optimization/potential-savings', {
    appliances,
    region,
  })
}
