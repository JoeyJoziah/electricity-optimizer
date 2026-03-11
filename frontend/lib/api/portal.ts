/**
 * Portal Connection API functions
 *
 * Create portal-based utility connections and trigger scraping
 * of billing data from utility provider websites.
 */

const API_BASE = '/api/v1/connections'

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
  payload: CreatePortalConnectionPayload
): Promise<PortalConnectionResponse> {
  const res = await fetch(`${API_BASE}/portal`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    credentials: 'include',
    body: JSON.stringify(payload),
  })
  if (!res.ok) {
    const err = await res.json().catch(() => ({}))
    throw new Error(err.detail || 'Failed to create portal connection')
  }
  return res.json()
}

/**
 * Trigger an immediate scrape of the portal connection.
 * Returns the scrape result including how many rates were extracted.
 */
export async function triggerPortalScrape(
  connectionId: string
): Promise<PortalScrapeResponse> {
  const res = await fetch(`${API_BASE}/portal/${connectionId}/scrape`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    credentials: 'include',
  })
  if (!res.ok) {
    const err = await res.json().catch(() => ({}))
    throw new Error(err.detail || 'Failed to trigger portal scrape')
  }
  return res.json()
}
