/**
 * Supplier API functions
 */

import { apiClient } from './client'
import type { Supplier, SupplierRecommendation } from '@/types'

export interface GetSuppliersResponse {
  suppliers: Supplier[]
}

export interface GetRecommendationResponse {
  recommendation: SupplierRecommendation
}

export interface InitiateSwitchRequest {
  newSupplierId: string
  gdprConsent: boolean
  currentSupplierId?: string
}

export interface InitiateSwitchResponse {
  success: boolean
  referenceNumber: string
  estimatedCompletionDate: string
}

/**
 * Get list of available suppliers
 */
export async function getSuppliers(
  region: string = 'uk',
  annualUsage?: number
): Promise<GetSuppliersResponse> {
  const params: Record<string, string> = { region }
  if (annualUsage) {
    params.annual_usage = annualUsage.toString()
  }
  return apiClient.get<GetSuppliersResponse>('/suppliers', params)
}

/**
 * Get a specific supplier by ID
 */
export async function getSupplier(supplierId: string): Promise<Supplier> {
  return apiClient.get<Supplier>(`/suppliers/${supplierId}`)
}

/**
 * Get supplier recommendation based on user's usage
 */
export async function getRecommendation(
  currentSupplierId: string,
  annualUsage: number,
  region: string = 'uk'
): Promise<GetRecommendationResponse> {
  return apiClient.post<GetRecommendationResponse>('/suppliers/recommend', {
    currentSupplierId,
    annualUsage,
    region,
  })
}

/**
 * Compare multiple suppliers
 */
export async function compareSuppliers(
  supplierIds: string[],
  annualUsage: number
): Promise<{ comparisons: Supplier[] }> {
  return apiClient.post('/suppliers/compare', {
    supplierIds,
    annualUsage,
  })
}

/**
 * Initiate a supplier switch
 */
export async function initiateSwitch(
  request: InitiateSwitchRequest
): Promise<InitiateSwitchResponse> {
  return apiClient.post<InitiateSwitchResponse>('/suppliers/switch', request)
}

/**
 * Get switch status
 */
export async function getSwitchStatus(
  referenceNumber: string
): Promise<{
  status: 'pending' | 'processing' | 'completed' | 'failed'
  estimatedCompletionDate: string
  lastUpdated: string
}> {
  return apiClient.get(`/suppliers/switch/${referenceNumber}`)
}
