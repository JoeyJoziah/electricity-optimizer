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
  region: string,
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
  region: string
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

// ============================================================================
// User Supplier Management (backend: /api/v1/user/supplier)
// ============================================================================

export interface UserSupplierResponse {
  supplier_id: string
  supplier_name: string
  regions: string[]
  rating: number | null
  green_energy: boolean
  website: string | null
}

export interface LinkAccountRequest {
  supplier_id: string
  account_number: string
  meter_number?: string
  service_zip?: string
  account_nickname?: string
  consent_given: boolean
}

export interface LinkedAccountResponse {
  supplier_id: string
  supplier_name: string
  account_number_masked: string | null
  meter_number_masked: string | null
  service_zip: string | null
  account_nickname: string | null
  is_primary: boolean
  verified_at: string | null
  created_at: string
}

/**
 * Set the authenticated user's current supplier
 */
export async function setUserSupplier(
  supplierId: string
): Promise<UserSupplierResponse> {
  return apiClient.put<UserSupplierResponse>('/user/supplier', {
    supplier_id: supplierId,
  })
}

/**
 * Get the authenticated user's current supplier
 */
export async function getUserSupplier(): Promise<{
  supplier: UserSupplierResponse | null
}> {
  return apiClient.get('/user/supplier')
}

/**
 * Remove the authenticated user's current supplier
 */
export async function removeUserSupplier(): Promise<{ message: string }> {
  return apiClient.delete('/user/supplier')
}

/**
 * Link a utility account to a supplier
 */
export async function linkSupplierAccount(
  data: LinkAccountRequest
): Promise<LinkedAccountResponse> {
  return apiClient.post<LinkedAccountResponse>('/user/supplier/link', data)
}

/**
 * Get all linked supplier accounts (masked)
 */
export async function getUserSupplierAccounts(): Promise<{
  accounts: LinkedAccountResponse[]
}> {
  return apiClient.get('/user/supplier/accounts')
}

/**
 * Unlink a specific supplier account
 */
export async function unlinkSupplierAccount(
  supplierId: string
): Promise<{ message: string }> {
  return apiClient.delete(`/user/supplier/accounts/${supplierId}`)
}
