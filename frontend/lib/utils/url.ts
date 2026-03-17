/**
 * URL safety utilities for client-side redirect validation.
 *
 * Prevents open redirect attacks by validating that redirect targets
 * resolve to the same origin as the current page.
 */

/**
 * Returns true if `url` resolves to the same origin as the current page.
 * Rejects external URLs, protocol-relative URLs (//evil.com), javascript:
 * URLs, and any other scheme that would leave the application.
 *
 * Usage:
 *   if (isSafeRedirect(callbackUrl)) window.location.href = callbackUrl
 *   else window.location.href = '/dashboard'
 */
export function isSafeRedirect(url: string): boolean {
  try {
    const parsed = new URL(url, window.location.origin)
    return parsed.origin === window.location.origin
  } catch {
    return false
  }
}

/**
 * Returns true if `href` uses a safe URL scheme (http: or https:).
 * Rejects `javascript:`, `data:`, `vbscript:`, and other dangerous schemes
 * that could be injected via server-supplied URLs rendered as `<a href>`.
 *
 * Usage:
 *   if (isSafeHref(program.enrollment_url)) ...render link...
 */
export function isSafeHref(href: string): boolean {
  try {
    const parsed = new URL(href)
    return parsed.protocol === 'https:' || parsed.protocol === 'http:'
  } catch {
    // Relative URLs or malformed strings — reject
    return false
  }
}

/**
 * Returns true if `url` is a known safe OAuth provider origin or the same
 * origin as the current page. Used for OAuth flow redirects where the
 * destination is an external identity provider (Google, Microsoft, UtilityAPI).
 *
 * Only `https:` external origins are permitted — plain `http:` is rejected.
 */
export function isSafeOAuthRedirect(
  url: string,
  allowedExternalOrigins: string[]
): boolean {
  try {
    const parsed = new URL(url)
    // Same-origin is always safe (handles dev http too)
    if (parsed.origin === window.location.origin) return true
    // External origins: must be https and explicitly whitelisted
    return parsed.protocol === 'https:' && allowedExternalOrigins.includes(parsed.origin)
  } catch {
    return false
  }
}
