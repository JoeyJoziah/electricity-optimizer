/**
 * Cloudflare Workers native Rate Limiting binding.
 * GA since Sept 2025. Counters maintained in-memory at edge PoP.
 */
export interface RateLimitBinding {
  limit(options: { key: string }): Promise<{ success: boolean }>;
}

export interface Env {
  // KV Namespaces
  CACHE: KVNamespace;

  // Native rate limiting bindings (zero KV cost)
  RATE_LIMITER_STANDARD: RateLimitBinding;
  RATE_LIMITER_STRICT: RateLimitBinding;
  RATE_LIMITER_INTERNAL: RateLimitBinding;

  // Environment variables
  ORIGIN_URL: string;
  ALLOWED_ORIGINS: string;

  // Secrets (set via `wrangler secret put`)
  // These are optional at the type level because Cloudflare Workers can run
  // without every secret bound (e.g. local dev, misconfigured deployments).
  // Code that reads them must always guard against undefined.
  INTERNAL_API_KEY?: string;
  RATE_LIMIT_BYPASS_KEY?: string;
}

export interface RouteConfig {
  pattern: RegExp;
  cache?: CacheConfig;
  rateLimit: RateLimitTier;
  requireApiKey?: boolean;
  passthrough?: boolean;
}

export interface CacheConfig {
  ttlSeconds: number;
  staleWhileRevalidateSeconds?: number;
  varyOn?: string[];
}

export type RateLimitTier = "standard" | "strict" | "internal" | "bypass";

export interface RequestContext {
  requestId: string;
  startTime: number;
  route: RouteConfig | null;
  clientIp: string;
  colo: string;
}

export interface RateLimitResult {
  allowed: boolean;
  remaining: number;
  limit: number;
  resetAt: number;
  /** True when KV operations failed and rate limiting is degraded (fail-open) */
  degraded?: boolean;
}

export interface CacheEntry {
  body: string;
  headers: Record<string, string>;
  status: number;
  storedAt: number;
  ttlSeconds: number;
}

export interface LogEntry {
  timestamp: string;
  requestId: string;
  method: string;
  path: string;
  status: number;
  durationMs: number;
  colo: string;
  clientIp: string;
  cacheStatus: "HIT" | "MISS" | "BYPASS" | "STALE";
  rateLimited: boolean;
  botScore?: number;
}
