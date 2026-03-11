/**
 * Base API client for making HTTP requests to the backend.
 * Includes automatic retry with backoff for 5xx/network errors
 * and 401 redirect to login with callback URL preservation.
 */

import { API_URL } from '@/lib/config/env'
import { isSafeRedirect } from '@/lib/utils/url'

const BASE_URL = API_URL
const MAX_RETRIES = 2
const RETRY_BASE_MS = 500

export interface ApiError {
  message: string
  status: number
  details?: Record<string, unknown>
}

export class ApiClientError extends Error {
  status: number
  details?: Record<string, unknown>

  constructor(error: ApiError) {
    super(error.message)
    this.name = 'ApiClientError'
    this.status = error.status
    this.details = error.details
  }
}

const REDIRECT_COUNT_KEY = 'api_401_redirect_count'
const REDIRECT_TS_KEY = 'api_401_redirect_ts'
// Safety valve: stop after 2 consecutive 401 redirects within the same window.
// Counter auto-expires after 10 seconds to avoid permanent lock-out.
const MAX_401_REDIRECTS = 2
const REDIRECT_WINDOW_MS = 10_000

// Deduplicate: only one 401 redirect in flight at a time
let redirectInFlight = false

/** @internal Reset redirect state — exposed for tests only */
export function _resetRedirectState() {
  redirectInFlight = false
  if (typeof window !== 'undefined') {
    sessionStorage.removeItem(REDIRECT_COUNT_KEY)
    sessionStorage.removeItem(REDIRECT_TS_KEY)
  }
}

async function handleResponse<T>(response: Response): Promise<T> {
  if (!response.ok) {
    // On 401, redirect to login — but guard against redirect loops
    if (response.status === 401 && typeof window !== 'undefined') {
      const pathname = window.location.pathname

      // Suppress redirect on ALL auth pages and public pages
      if (!pathname.startsWith('/auth/') && !redirectInFlight) {
        // Expire old redirect counters so users aren't permanently locked out
        const lastTs = parseInt(sessionStorage.getItem(REDIRECT_TS_KEY) || '0', 10)
        const now = Date.now()
        if (now - lastTs > REDIRECT_WINDOW_MS) {
          sessionStorage.removeItem(REDIRECT_COUNT_KEY)
        }

        const count = parseInt(sessionStorage.getItem(REDIRECT_COUNT_KEY) || '0', 10)
        if (count < MAX_401_REDIRECTS) {
          redirectInFlight = true
          sessionStorage.setItem(REDIRECT_COUNT_KEY, String(count + 1))
          sessionStorage.setItem(REDIRECT_TS_KEY, String(now))

          // Preserve the original callback instead of nesting
          const params = new URLSearchParams(window.location.search)
          const existingCallback = params.get('callbackUrl')
          const callbackUrl = (existingCallback && isSafeRedirect(existingCallback))
            ? existingCallback
            : pathname

          console.warn(
            '[auth] Session expired or unauthorized. Redirecting to login.'
          )
          window.location.href = `/auth/login?callbackUrl=${encodeURIComponent(callbackUrl)}`
          // Return a never-resolving promise to prevent further processing
          return new Promise<T>(() => {})
        }
      }
    }

    let errorMessage = 'An error occurred'
    let details: Record<string, unknown> | undefined

    try {
      const errorData = await response.json()
      errorMessage = errorData.detail || errorData.message || errorMessage
      details = errorData
    } catch {
      errorMessage = response.statusText || errorMessage
    }

    throw new ApiClientError({
      message: errorMessage,
      status: response.status,
      details,
    })
  }

  // Reset redirect counter on any successful response
  if (typeof window !== 'undefined') {
    sessionStorage.removeItem(REDIRECT_COUNT_KEY)
    sessionStorage.removeItem(REDIRECT_TS_KEY)
    redirectInFlight = false
  }

  return response.json()
}

function isRetryable(error: unknown): boolean {
  if (error instanceof ApiClientError) {
    return error.status >= 500
  }
  // Network errors (fetch throws TypeError on network failure)
  return error instanceof TypeError
}

async function fetchWithRetry<T>(
  url: string,
  options: RequestInit,
): Promise<T> {
  let lastError: unknown

  for (let attempt = 0; attempt <= MAX_RETRIES; attempt++) {
    try {
      const response = await fetch(url, options)
      return await handleResponse<T>(response)
    } catch (error) {
      lastError = error
      if (!isRetryable(error) || attempt === MAX_RETRIES) {
        throw error
      }
      await new Promise((r) => setTimeout(r, RETRY_BASE_MS * 2 ** attempt))
    }
  }

  throw lastError
}

export const apiClient = {
  async get<T>(endpoint: string, params?: Record<string, string>): Promise<T> {
    let urlStr = `${BASE_URL}${endpoint}`
    if (params && Object.keys(params).length > 0) {
      const qs = new URLSearchParams(params).toString()
      urlStr += `?${qs}`
    }

    return fetchWithRetry<T>(urlStr, {
      method: 'GET',
      headers: {
        'Content-Type': 'application/json',
      },
      credentials: 'include',
    })
  },

  async post<T>(endpoint: string, data?: unknown): Promise<T> {
    return fetchWithRetry<T>(`${BASE_URL}${endpoint}`, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
      },
      credentials: 'include',
      body: data ? JSON.stringify(data) : undefined,
    })
  },

  async put<T>(endpoint: string, data?: unknown): Promise<T> {
    return fetchWithRetry<T>(`${BASE_URL}${endpoint}`, {
      method: 'PUT',
      headers: {
        'Content-Type': 'application/json',
      },
      credentials: 'include',
      body: data ? JSON.stringify(data) : undefined,
    })
  },

  async delete<T>(endpoint: string): Promise<T> {
    return fetchWithRetry<T>(`${BASE_URL}${endpoint}`, {
      method: 'DELETE',
      headers: {
        'Content-Type': 'application/json',
      },
      credentials: 'include',
    })
  },
}
