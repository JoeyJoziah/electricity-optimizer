/**
 * Base API client for making HTTP requests to the backend.
 * Includes automatic retry with backoff for 5xx/network errors
 * and 401 redirect to login.
 */

const BASE_URL = process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000/api/v1'
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

async function handleResponse<T>(response: Response): Promise<T> {
  if (!response.ok) {
    // On 401, redirect to login (session expired)
    if (response.status === 401 && typeof window !== 'undefined') {
      window.location.href = '/auth/login'
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
    const url = new URL(`${BASE_URL}${endpoint}`)
    if (params) {
      Object.entries(params).forEach(([key, value]) => {
        url.searchParams.append(key, value)
      })
    }

    return fetchWithRetry<T>(url.toString(), {
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
