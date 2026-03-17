import { ROUTES, DEFAULT_ROUTE } from "./config";
import type { RouteConfig } from "./types";

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
      parts.push(`${encodeURIComponent(key)}=${encodeURIComponent(val)}`);
    }
  }

  if (parts.length === 0) {
    return `rsgw:${pathname}`;
  }
  return `rsgw:${pathname}|${parts.join("|")}`;
}
