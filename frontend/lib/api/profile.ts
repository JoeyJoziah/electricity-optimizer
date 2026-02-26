/**
 * Profile API functions
 */

import { apiClient } from './client'

export interface UserProfile {
  email: string
  name: string | null
  region: string | null
  utility_types: string[] | null
  current_supplier_id: string | null
  annual_usage_kwh: number | null
  onboarding_completed: boolean
}

export interface UpdateProfileData {
  name?: string
  region?: string
  utility_types?: string[]
  current_supplier_id?: string
  annual_usage_kwh?: number
  onboarding_completed?: boolean
}

/**
 * Get the authenticated user's profile
 */
export async function getUserProfile(): Promise<UserProfile> {
  return apiClient.get<UserProfile>('/users/profile')
}

/**
 * Update the authenticated user's profile (partial update)
 */
export async function updateUserProfile(data: UpdateProfileData): Promise<UserProfile> {
  return apiClient.put<UserProfile>('/users/profile', data)
}
