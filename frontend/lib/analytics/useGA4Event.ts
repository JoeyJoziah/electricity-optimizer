/**
 * useGA4Event — lightweight hook for firing GA4 custom events.
 *
 * Safe to call before gtag.js has loaded — calls are silently dropped
 * when window.gtag is undefined (e.g. ad-blockers, dev, test envs).
 *
 * Usage:
 *   const { trackEvent } = useGA4Event()
 *   trackEvent('plan_upgrade', { plan: 'pro', value: 4.99 })
 */

// ---------------------------------------------------------------------------
// Types
// ---------------------------------------------------------------------------

/** All supported GA4 custom event names for this application. */
export type GA4EventName =
  | "signup"
  | "login"
  | "forecast_view"
  | "switch_initiated"
  | "plan_upgrade"
  | "connection_added";

/** Arbitrary key/value pairs forwarded as the GA4 event parameters object. */
export type GA4EventParams = Record<
  string,
  string | number | boolean | null | undefined
>;

// ---------------------------------------------------------------------------
// Window augmentation — gtag is injected by the GA4Analytics script
// ---------------------------------------------------------------------------

declare global {
  interface Window {
    // eslint-disable-next-line @typescript-eslint/no-explicit-any
    gtag?: (...args: any[]) => void;
    dataLayer?: unknown[];
  }
}

// ---------------------------------------------------------------------------
// Hook
// ---------------------------------------------------------------------------

interface UseGA4EventReturn {
  /**
   * Fire a GA4 custom event.
   *
   * @param name   - One of the supported GA4EventName values.
   * @param params - Optional event parameters forwarded to gtag.
   */
  trackEvent: (name: GA4EventName, params?: GA4EventParams) => void;
}

/**
 * Returns a stable `trackEvent` helper that delegates to `window.gtag`.
 * The function reference is recreated on every render but is intentionally
 * lightweight — no memoisation needed for analytics calls.
 */
export function useGA4Event(): UseGA4EventReturn {
  function trackEvent(name: GA4EventName, params?: GA4EventParams): void {
    if (typeof window === "undefined") return;
    if (typeof window.gtag !== "function") return;
    window.gtag("event", name, params);
  }

  return { trackEvent };
}
