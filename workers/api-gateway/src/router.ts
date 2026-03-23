import { ROUTES, DEFAULT_ROUTE, VALID_REGIONS } from "./config";
import type { RouteConfig } from "./types";

/** Maximum length for any query parameter value used in cache keys. */
const MAX_CACHE_PARAM_LENGTH = 64;

/**
 * Match a request path against the route table.
 * Returns the first matching RouteConfig, or DEFAULT_ROUTE if none match.
 */
export function matchRoute(pathname: string): RouteConfig {
  for (const route of ROUTES) {
    if (route.pattern.test(pathname)) {
      return route;
    }
  }
  return DEFAULT_ROUTE;
}

/**
 * Sanitize a query parameter value for inclusion in a cache key.
 *
 * - If the key is "region", validates against VALID_REGIONS; invalid values
 *   are replaced with "unknown" so they share a single cache slot rather than
 *   polluting KV with arbitrary keys.
 * - All values are truncated to MAX_CACHE_PARAM_LENGTH to prevent
 *   cache-key bloat from oversized parameters.
 */
function sanitizeCacheParam(key: string, value: string): string {
  // Truncate first to bound CPU and memory usage
  let sanitized = value.slice(0, MAX_CACHE_PARAM_LENGTH);

  // Validate region against known enum values
  if (key === "region" && !VALID_REGIONS.has(sanitized.toLowerCase())) {
    sanitized = "unknown";
  }

  return sanitized;
}

/**
 * Build a cache key from a pathname and query params, using only
 * the params specified in varyOn (sorted for consistency).
 */
export function buildCacheKey(
  pathname: string,
  searchParams: URLSearchParams,
  varyOn?: string[]
): string {
  if (!varyOn || varyOn.length === 0) {
    return `rsgw:${pathname}`;
  }

  const parts: string[] = [];
  const sorted = [...varyOn].sort();
  for (const key of sorted) {
    const val = searchParams.get(key);
    if (val !== null) {
      const safe = sanitizeCacheParam(key, val);
      parts.push(`${encodeURIComponent(key)}=${encodeURIComponent(safe)}`);
    }
  }

  if (parts.length === 0) {
    return `rsgw:${pathname}`;
  }
  return `rsgw:${pathname}|${parts.join("|")}`;
}
