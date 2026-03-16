/**
 * Portal Connection API functions
 *
 * Create portal-based utility connections and trigger scraping
 * of billing data from utility provider websites.
 */

import { apiClient } from './client'

// ---------------------------------------------------------------------------
// Types
// ---------------------------------------------------------------------------

export interface CreatePortalConnectionPayload {
  supplier_id: string
  portal_username: string
  portal_password: string
  portal_login_url?: string
  consent_given: boolean
}

export interface PortalConnectionResponse {
  connection_id: string
  supplier_id: string
  portal_username: string
  portal_login_url: string | null
  portal_scrape_status: string
  portal_last_scraped_at: string | null
}

export interface PortalScrapeResponse {
  connection_id: string
  status: string
  rates_extracted: number
  error: string | null
  scraped_at: string | null
}

// ---------------------------------------------------------------------------
// API functions
// ---------------------------------------------------------------------------

/**
 * Create a new portal-based utility connection.
 * Stores credentials for automated portal scraping.
 */
export async function createPortalConnection(
  payload: CreatePortalConnectionPayload,
  options?: { signal?: AbortSignal },
): Promise<PortalConnectionResponse> {
  return apiClient.post<PortalConnectionResponse>(
    '/connections/portal',
    payload,
    options,
  )
}

/**
 * Trigger an immediate scrape of the portal connection.
 * Returns the scrape result including how many rates were extracted.
 */
export async function triggerPortalScrape(
  connectionId: string,
  options?: { signal?: AbortSignal },
): Promise<PortalScrapeResponse> {
  return apiClient.post<PortalScrapeResponse>(
    `/connections/portal/${connectionId}/scrape`,
    undefined,
    options,
  )
}
