/**
 * Affiliate API functions
 */

import { apiClient } from './client'

export interface RecordClickRequest {
  supplier_name: string
  supplier_id?: string
  utility_type: string
  region: string
  source_page: string
  user_id?: string
}

export interface RecordClickResponse {
  click_id: string
  affiliate_url: string | null
}

/**
 * Record an affiliate click and get the redirect URL.
 */
export async function recordAffiliateClick(
  body: RecordClickRequest
): Promise<RecordClickResponse> {
  return apiClient.post<RecordClickResponse>('/affiliate/click', body)
}
