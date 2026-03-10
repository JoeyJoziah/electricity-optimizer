/**
 * Centralized Environment Variable Configuration
 *
 * All NEXT_PUBLIC_* env vars should be accessed through this module
 * instead of reading process.env directly. This provides:
 *
 *   - A single source of truth for all public env vars
 *   - Sensible development defaults
 *   - Runtime validation in production (missing required vars throw)
 *   - Type-safe exports (no `string | undefined` at call sites)
 *
 * Usage:
 *   import { API_URL, SITE_URL } from '@/lib/config/env'
 *
 * IMPORTANT: Because Next.js inlines NEXT_PUBLIC_* at build time,
 * the process.env.NEXT_PUBLIC_X reads MUST appear literally in this
 * file. They cannot be dynamically constructed from a list of names.
 */

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

const isProduction = process.env.NODE_ENV === 'production'
const isTest = process.env.NODE_ENV === 'test'

/**
 * Resolve an env var with a fallback. In production, if the variable is
 * missing and `required` is true, throw immediately so the build or
 * server start fails fast rather than silently falling back.
 */
function env(
  value: string | undefined,
  fallback: string,
  opts?: { required?: boolean; name?: string },
): string {
  if (value) return value
  if (isProduction && opts?.required) {
    throw new Error(
      `[env] Missing required environment variable: ${opts.name ?? '(unknown)'}. ` +
        'Set it in your deployment configuration.',
    )
  }
  return fallback
}

// ---------------------------------------------------------------------------
// API
// ---------------------------------------------------------------------------

/**
 * Full API base URL **including** the /api/v1 path prefix.
 * Use this for apiClient calls and SSE subscriptions.
 *
 * Example: "https://api.rateshift.app/api/v1"
 */
export const API_URL: string = env(
  process.env.NEXT_PUBLIC_API_URL,
  '/api/v1',
  { required: false, name: 'NEXT_PUBLIC_API_URL' },
)

/**
 * API origin (scheme + host + port) **without** any path.
 * Use this when you need to construct URLs with a different path prefix
 * than /api/v1 (e.g. file uploads, checkout proxy).
 *
 * For relative API_URL (same-origin proxy), returns empty string so that
 * `${API_ORIGIN}/api/v1/...` becomes `/api/v1/...` (relative, same-origin).
 */
export const API_ORIGIN: string = (() => {
  try {
    if (API_URL.startsWith('/')) return ''
    const parsed = new URL(API_URL)
    return `${parsed.protocol}//${parsed.host}`
  } catch {
    return ''
  }
})()

// ---------------------------------------------------------------------------
// Frontend / App
// ---------------------------------------------------------------------------

/**
 * Public-facing app URL. Used by Better Auth for trusted origins and
 * as the SSR fallback for auth client initialization.
 *
 * Example: "https://rateshift.app"
 */
export const APP_URL: string = env(
  process.env.NEXT_PUBLIC_APP_URL,
  'http://localhost:3000',
  { name: 'NEXT_PUBLIC_APP_URL' },
)

/**
 * Canonical site URL used in SEO metadata (sitemap.xml, robots.txt).
 * Falls back to the Vercel deployment URL in production.
 */
export const SITE_URL: string = env(
  process.env.NEXT_PUBLIC_SITE_URL,
  'https://rateshift.app',
  { name: 'NEXT_PUBLIC_SITE_URL' },
)

// ---------------------------------------------------------------------------
// Flags & Utilities
// ---------------------------------------------------------------------------

/** True when NODE_ENV === 'production' */
export const IS_PRODUCTION = isProduction

/** True when NODE_ENV === 'test' */
export const IS_TEST = isTest

/** True when NODE_ENV === 'development' (or unset) */
export const IS_DEV = !isProduction && !isTest

// ---------------------------------------------------------------------------
// Analytics & Integrations
// ---------------------------------------------------------------------------

/** Microsoft Clarity project ID for heatmaps and session recordings (free, unlimited). */
export const CLARITY_PROJECT_ID: string = process.env.NEXT_PUBLIC_CLARITY_PROJECT_ID || ''

/** OneSignal App ID for web push notifications (free tier, 10K web push/send). */
export const ONESIGNAL_APP_ID: string = process.env.NEXT_PUBLIC_ONESIGNAL_APP_ID || ''
