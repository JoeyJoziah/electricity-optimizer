/**
 * Base API client for making HTTP requests to the backend.
 * Includes automatic retry with backoff for 5xx/network errors,
 * 401 redirect to login with callback URL preservation,
 * and circuit breaker for CF Worker gateway resilience.
 */

import { API_URL, FALLBACK_API_URL } from "@/lib/config/env";
import { isSafeRedirect } from "@/lib/utils/url";
import { CircuitBreaker } from "./circuit-breaker";

const MAX_RETRIES = 2;
const RETRY_BASE_MS = 500;

/** Circuit breaker singleton — shared across all API client methods */
export const circuitBreaker = new CircuitBreaker({
  failureThreshold: 3,
  resetTimeoutMs: 30_000,
  fallbackUrl: FALLBACK_API_URL,
  primaryUrl: API_URL,
});

export interface ApiError {
  message: string;
  status: number;
  details?: Record<string, unknown>;
}

export class ApiClientError extends Error {
  status: number;
  details?: Record<string, unknown>;

  constructor(error: ApiError) {
    super(error.message);
    this.name = "ApiClientError";
    this.status = error.status;
    this.details = error.details;
  }
}

const REDIRECT_COUNT_KEY = "api_401_redirect_count";
const REDIRECT_TS_KEY = "api_401_redirect_ts";
// Safety valve: stop after 2 consecutive 401 redirects within the same window.
// Counter auto-expires after 10 seconds to avoid permanent lock-out.
const MAX_401_REDIRECTS = 2;
const REDIRECT_WINDOW_MS = 10_000;

// Deduplicate: only one 401 redirect in flight at a time
let redirectInFlight = false;

/** @internal Reset redirect state — exposed for tests only */
export function _resetRedirectState() {
  redirectInFlight = false;
  if (typeof window !== "undefined") {
    sessionStorage.removeItem(REDIRECT_COUNT_KEY);
    sessionStorage.removeItem(REDIRECT_TS_KEY);
  }
}

/**
 * Perform a 401 redirect with full loop-protection logic.
 *
 * Exported so that non-apiClient code (e.g. agent SSE handler) can use
 * the same redirect-loop prevention instead of rolling its own.
 *
 * Returns `true` if a redirect was initiated, `false` if suppressed.
 */
export function handle401Redirect(): boolean {
  if (typeof window === "undefined") return false;

  const pathname = window.location.pathname;

  // Suppress redirect on ALL auth pages
  if (pathname.startsWith("/auth/")) return false;

  if (redirectInFlight) return false;

  // Expire old redirect counters so users aren't permanently locked out
  const lastTs = parseInt(sessionStorage.getItem(REDIRECT_TS_KEY) || "0", 10);
  const now = Date.now();
  if (now - lastTs > REDIRECT_WINDOW_MS) {
    sessionStorage.removeItem(REDIRECT_COUNT_KEY);
  }

  const count = parseInt(sessionStorage.getItem(REDIRECT_COUNT_KEY) || "0", 10);
  if (count >= MAX_401_REDIRECTS) return false;

  redirectInFlight = true;
  sessionStorage.setItem(REDIRECT_COUNT_KEY, String(count + 1));
  sessionStorage.setItem(REDIRECT_TS_KEY, String(now));

  // Preserve the original callback instead of nesting
  const params = new URLSearchParams(window.location.search);
  const existingCallback = params.get("callbackUrl");
  const callbackUrl =
    existingCallback && isSafeRedirect(existingCallback)
      ? existingCallback
      : pathname;

  console.warn("[auth] Session expired or unauthorized. Redirecting to login.");
  window.location.href = `/auth/login?callbackUrl=${encodeURIComponent(callbackUrl)}`;
  return true;
}

/**
 * Check whether a response has an empty body (e.g. 204 No Content).
 * Returns true if the response should be treated as having no JSON body.
 */
function isEmptyResponse(response: Response): boolean {
  if (response.status === 204 || response.status === 205) return true;
  const contentLength = response.headers.get("content-length");
  if (contentLength === "0") return true;
  return false;
}

async function handleResponse<T>(response: Response): Promise<T> {
  if (!response.ok) {
    // On 401, redirect to login — but guard against redirect loops
    if (response.status === 401) {
      if (handle401Redirect()) {
        // Return a never-resolving promise to prevent further processing
        return new Promise<T>(() => {});
      }
    }

    let errorMessage = "An error occurred";
    let details: Record<string, unknown> | undefined;

    try {
      const errorData = await response.json();
      errorMessage = errorData.detail || errorData.message || errorMessage;
      details = errorData;
    } catch {
      errorMessage = response.statusText || errorMessage;
    }

    throw new ApiClientError({
      message: errorMessage,
      status: response.status,
      details,
    });
  }

  // Reset redirect counter on any successful response
  if (typeof window !== "undefined") {
    sessionStorage.removeItem(REDIRECT_COUNT_KEY);
    sessionStorage.removeItem(REDIRECT_TS_KEY);
    redirectInFlight = false;
  }

  // Handle empty responses (204 No Content, 205 Reset Content, content-length: 0)
  if (isEmptyResponse(response)) {
    return undefined as T;
  }

  return response.json();
}

function isRetryable(error: unknown): boolean {
  // Never retry aborted requests
  if (error instanceof DOMException && error.name === "AbortError")
    return false;
  if (error instanceof ApiClientError) {
    // 429 = rate limited — retrying immediately makes it worse
    if (error.status === 429) return false;
    return error.status >= 500;
  }
  // Network errors (fetch throws TypeError on network failure)
  return error instanceof TypeError;
}

// ---------------------------------------------------------------------------
// Global 503 cooldown
//
// When the backend returns 503 (cold start / unavailable), ALL subsequent
// fetch attempts wait for a shared cooldown promise. This prevents the retry
// cascade from overwhelming the CF Worker rate limiter (120 req/min) — without
// it, 10+ parallel queries each retrying 2-3 times create 30-40 requests in
// seconds, all hitting 503 and then 429.
// ---------------------------------------------------------------------------
const BACKEND_COOLDOWN_MS = 3_000;
let _backendCooldown: Promise<void> | null = null;

/** Trigger a global cooldown — all fetchWithRetry calls will wait */
function triggerBackendCooldown() {
  if (_backendCooldown) return; // Already cooling down
  _backendCooldown = new Promise((resolve) => {
    setTimeout(() => {
      _backendCooldown = null;
      resolve();
    }, BACKEND_COOLDOWN_MS);
  });
}

/** @internal Reset cooldown state — exposed for tests only */
export function _resetBackendCooldown() {
  _backendCooldown = null;
}

async function fetchWithRetry<T>(
  url: string,
  options: RequestInit,
): Promise<T> {
  let lastError: unknown;

  for (let attempt = 0; attempt <= MAX_RETRIES; attempt++) {
    // Wait if backend is in cooldown (503 detected by any recent request)
    if (_backendCooldown) {
      await _backendCooldown;
    }

    try {
      const response = await fetch(url, options);
      const result = await handleResponse<T>(response);
      circuitBreaker.recordSuccess();
      return result;
    } catch (error) {
      lastError = error;

      // Re-throw AbortError immediately — no retries, no circuit breaker
      if (error instanceof DOMException && error.name === "AbortError") {
        throw error;
      }

      // On 503, trigger global cooldown so parallel queries don't dogpile
      if (error instanceof ApiClientError && error.status === 503) {
        triggerBackendCooldown();
      }

      // Track gateway errors for circuit breaker (after all retries exhausted)
      if (
        error instanceof ApiClientError &&
        CircuitBreaker.isGatewayError(error.status) &&
        attempt === MAX_RETRIES
      ) {
        circuitBreaker.recordFailure();
      }

      if (!isRetryable(error) || attempt === MAX_RETRIES) {
        throw error;
      }
      // Use longer backoff for 503 to give backend time to warm up
      const backoff =
        error instanceof ApiClientError && error.status === 503
          ? BACKEND_COOLDOWN_MS
          : RETRY_BASE_MS * 2 ** attempt;
      await new Promise((r) => setTimeout(r, backoff));
    }
  }

  throw lastError;
}

function buildHeaders(): Record<string, string> {
  const headers: Record<string, string> = {
    "Content-Type": "application/json",
  };
  if (circuitBreaker.isFallbackMode()) {
    headers["X-Fallback-Mode"] = "true";
  }
  return headers;
}

export const apiClient = {
  async get<T>(
    endpoint: string,
    params?: Record<
      string,
      string | number | boolean | (string | number | boolean)[]
    >,
    options?: { signal?: AbortSignal },
  ): Promise<T> {
    const baseUrl = circuitBreaker.getBaseUrl();
    let urlStr = `${baseUrl}${endpoint}`;
    if (params && Object.keys(params).length > 0) {
      const searchParams = new URLSearchParams();
      for (const [k, v] of Object.entries(params)) {
        if (Array.isArray(v)) {
          for (const item of v) {
            searchParams.append(k, String(item));
          }
        } else {
          searchParams.append(k, String(v));
        }
      }
      const qs = searchParams.toString();
      urlStr += `?${qs}`;
    }

    return fetchWithRetry<T>(urlStr, {
      method: "GET",
      headers: buildHeaders(),
      credentials: "include",
      signal: options?.signal,
    });
  },

  async post<T>(
    endpoint: string,
    data?: unknown,
    options?: { signal?: AbortSignal },
  ): Promise<T> {
    const baseUrl = circuitBreaker.getBaseUrl();
    return fetchWithRetry<T>(`${baseUrl}${endpoint}`, {
      method: "POST",
      headers: buildHeaders(),
      credentials: "include",
      body: data ? JSON.stringify(data) : undefined,
      signal: options?.signal,
    });
  },

  async put<T>(
    endpoint: string,
    data?: unknown,
    options?: { signal?: AbortSignal },
  ): Promise<T> {
    const baseUrl = circuitBreaker.getBaseUrl();
    return fetchWithRetry<T>(`${baseUrl}${endpoint}`, {
      method: "PUT",
      headers: buildHeaders(),
      credentials: "include",
      body: data ? JSON.stringify(data) : undefined,
      signal: options?.signal,
    });
  },

  async patch<T>(
    endpoint: string,
    data?: unknown,
    options?: { signal?: AbortSignal },
  ): Promise<T> {
    const baseUrl = circuitBreaker.getBaseUrl();
    return fetchWithRetry<T>(`${baseUrl}${endpoint}`, {
      method: "PATCH",
      headers: buildHeaders(),
      credentials: "include",
      body: data ? JSON.stringify(data) : undefined,
      signal: options?.signal,
    });
  },

  async delete<T>(
    endpoint: string,
    data?: unknown,
    options?: { signal?: AbortSignal },
  ): Promise<T> {
    const baseUrl = circuitBreaker.getBaseUrl();
    return fetchWithRetry<T>(`${baseUrl}${endpoint}`, {
      method: "DELETE",
      headers: buildHeaders(),
      credentials: "include",
      body: data ? JSON.stringify(data) : undefined,
      signal: options?.signal,
    });
  },
};
