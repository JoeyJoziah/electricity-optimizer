import type { LogEntry } from "../types";

// ---------------------------------------------------------------------------
// Per-isolate in-memory metrics (approximate, reset on cold start)
// ---------------------------------------------------------------------------

export interface GatewayMetrics {
  cacheReads: number;
  cacheWrites: number;
  cacheHits: number;
  cacheMisses: number;
  rateLimitChecks: number;
  degradedResponses: number;
  totalRequests: number;
}

export interface GatewayStats {
  counters: GatewayMetrics;
  uptimeMs: number;
  startedAt: string;
  degraded: boolean;
  cacheHitRate: number;
}

let _startTime = Date.now();
let _startedAt = new Date().toISOString();

export const gatewayMetrics: GatewayMetrics = {
  cacheReads: 0,
  cacheWrites: 0,
  cacheHits: 0,
  cacheMisses: 0,
  rateLimitChecks: 0,
  degradedResponses: 0,
  totalRequests: 0,
};

// ---------------------------------------------------------------------------
// Counter recording functions
// ---------------------------------------------------------------------------

export function recordCacheRead(): void {
  gatewayMetrics.cacheReads++;
}

export function recordCacheWrite(): void {
  gatewayMetrics.cacheWrites++;
}

export function recordCacheHit(): void {
  gatewayMetrics.cacheHits++;
}

export function recordCacheMiss(): void {
  gatewayMetrics.cacheMisses++;
}

export function recordRateLimitCheck(): void {
  gatewayMetrics.rateLimitChecks++;
}

export function recordDegradation(): void {
  gatewayMetrics.degradedResponses++;
}

export function recordRequest(): void {
  gatewayMetrics.totalRequests++;
}

/** Reset all counters and timestamps — exposed for tests only. */
export function resetMetrics(): void {
  gatewayMetrics.cacheReads = 0;
  gatewayMetrics.cacheWrites = 0;
  gatewayMetrics.cacheHits = 0;
  gatewayMetrics.cacheMisses = 0;
  gatewayMetrics.rateLimitChecks = 0;
  gatewayMetrics.degradedResponses = 0;
  gatewayMetrics.totalRequests = 0;
  _startTime = Date.now();
  _startedAt = new Date().toISOString();
}

// ---------------------------------------------------------------------------
// Stats snapshot
// ---------------------------------------------------------------------------

export function getGatewayStats(): GatewayStats {
  const totalCacheOps = gatewayMetrics.cacheHits + gatewayMetrics.cacheMisses;
  const cacheHitRate = totalCacheOps > 0 ? gatewayMetrics.cacheHits / totalCacheOps : 0;

  return {
    counters: { ...gatewayMetrics },
    uptimeMs: Date.now() - _startTime,
    startedAt: _startedAt,
    degraded: gatewayMetrics.degradedResponses > 0,
    cacheHitRate,
  };
}

// ---------------------------------------------------------------------------
// Structured logging (existing)
// ---------------------------------------------------------------------------

/**
 * Log a structured JSON entry via console.log.
 * Cloudflare captures these as Worker logs viewable via `wrangler tail`.
 */
export function logRequest(entry: LogEntry): void {
  console.log(JSON.stringify(entry));
}

/**
 * Build a log entry from request context.
 */
export function buildLogEntry(params: {
  requestId: string;
  method: string;
  path: string;
  status: number;
  startTime: number;
  colo: string;
  clientIp: string;
  cacheStatus: LogEntry["cacheStatus"];
  rateLimited: boolean;
  botScore?: number;
}): LogEntry {
  return {
    timestamp: new Date().toISOString(),
    requestId: params.requestId,
    method: params.method,
    path: params.path,
    status: params.status,
    durationMs: Date.now() - params.startTime,
    colo: params.colo,
    clientIp: params.clientIp,
    cacheStatus: params.cacheStatus,
    rateLimited: params.rateLimited,
    botScore: params.botScore,
  };
}
