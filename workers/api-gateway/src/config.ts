import type { RouteConfig } from "./types";

export const ROUTES: RouteConfig[] = [
  // Webhooks — passthrough, no rate limit (Stripe sends retries)
  {
    pattern: /^\/api\/v1\/webhooks\//,
    rateLimit: "bypass",
    passthrough: true,
  },

  // SSE streaming — passthrough, no caching
  {
    pattern: /^\/api\/v1\/prices\/stream$/,
    rateLimit: "standard",
    passthrough: true,
  },

  // Gateway stats — internal, API key required
  {
    pattern: /^\/api\/v1\/internal\/gateway-stats$/,
    rateLimit: "internal",
    requireApiKey: true,
  },

  // Internal endpoints — API key required, no caching
  {
    pattern: /^\/api\/v1\/internal\//,
    rateLimit: "internal",
    requireApiKey: true,
  },

  // Price refresh — triggers cache invalidation
  {
    pattern: /^\/api\/v1\/prices\/refresh$/,
    rateLimit: "strict",
  },

  // Current prices — short cache, vary on region
  {
    pattern: /^\/api\/v1\/prices\/current$/,
    cache: {
      ttlSeconds: 300, // 5 min
      staleWhileRevalidateSeconds: 60,
      varyOn: ["region"],
    },
    rateLimit: "standard",
  },

  // Price history — medium cache
  {
    pattern: /^\/api\/v1\/prices\/history$/,
    cache: {
      ttlSeconds: 1800, // 30 min
      staleWhileRevalidateSeconds: 300,
      varyOn: ["region", "days"],
    },
    rateLimit: "standard",
  },

  // Price analytics — longer cache
  {
    pattern: /^\/api\/v1\/prices\/analytics/,
    cache: {
      ttlSeconds: 3600, // 1 hr
      staleWhileRevalidateSeconds: 600,
      varyOn: ["region"],
    },
    rateLimit: "standard",
  },

  // Supplier registry — long cache (rarely changes)
  {
    pattern: /^\/api\/v1\/suppliers\/registry$/,
    cache: {
      ttlSeconds: 7200, // 2 hr
      staleWhileRevalidateSeconds: 1800,
    },
    rateLimit: "standard",
  },

  // Suppliers list — medium-long cache
  {
    pattern: /^\/api\/v1\/suppliers(?:\/|$)/,
    cache: {
      ttlSeconds: 3600, // 1 hr
      staleWhileRevalidateSeconds: 600,
      varyOn: ["region"],
    },
    rateLimit: "standard",
  },

  // Health check — short cache
  {
    pattern: /^\/health$/,
    cache: {
      ttlSeconds: 30,
    },
    rateLimit: "bypass",
  },

  // Auth endpoints — strict rate limit, no cache
  {
    pattern: /^\/api\/v1\/auth\//,
    rateLimit: "strict",
  },

  // Feedback — strict rate limit
  {
    pattern: /^\/api\/v1\/feedback$/,
    rateLimit: "strict",
  },
];

// Default config for unmatched routes
export const DEFAULT_ROUTE: RouteConfig = {
  pattern: /.*/,
  rateLimit: "standard",
};

// Cache key prefix to enable bulk invalidation
export const CACHE_KEY_PREFIX = "rsgw:";

// Price-related cache key patterns for invalidation on /prices/refresh
export const PRICE_CACHE_PATTERNS = [
  "rsgw:/api/v1/prices/current",
  "rsgw:/api/v1/prices/history",
  "rsgw:/api/v1/prices/analytics",
];
