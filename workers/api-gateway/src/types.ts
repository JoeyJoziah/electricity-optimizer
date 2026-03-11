export interface Env {
  // KV Namespaces
  CACHE: KVNamespace;
  RATE_LIMIT: KVNamespace;

  // Environment variables
  ORIGIN_URL: string;
  ALLOWED_ORIGINS: string;
  RATE_LIMIT_STANDARD: string;
  RATE_LIMIT_STRICT: string;
  RATE_LIMIT_INTERNAL: string;
  RATE_LIMIT_WINDOW_SECONDS: string;

  // Secrets (set via `wrangler secret put`)
  INTERNAL_API_KEY: string;
  RATE_LIMIT_BYPASS_KEY: string;
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
