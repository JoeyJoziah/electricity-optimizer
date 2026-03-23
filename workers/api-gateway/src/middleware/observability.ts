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
// GDPR-compliant IP anonymization
// ---------------------------------------------------------------------------

/**
 * Anonymize an IPv4 or IPv6 address for GDPR-compliant logging.
 *
 * IPv4: zero the last octet            192.168.1.42  →  192.168.1.0
 * IPv6: zero the last 80 bits (5 groups) of the 128-bit address so that only
 *       the first 48 bits (network prefix) are retained.
 *       2001:0db8:85a3:0000:0000:8a2e:0370:7334  →  2001:db8:85a3::
 *
 * Returns the original value unchanged when the format is not recognised
 * (e.g. "unknown") so that logging never crashes on unexpected input.
 */
export function anonymizeIp(ip: string): string {
  if (!ip || ip === "unknown") {
    return ip;
  }

  // IPv4: replace last octet
  const ipv4Re = /^(\d{1,3}\.\d{1,3}\.\d{1,3})\.\d{1,3}$/;
  const ipv4Match = ip.match(ipv4Re);
  if (ipv4Match) {
    return `${ipv4Match[1]}.0`;
  }

  // IPv6 (including mapped IPv4-in-IPv6 like ::ffff:192.168.1.1):
  // Expand the address to its full 8-group form, zero the last 5 groups,
  // then re-compress with the :: notation.
  if (ip.includes(":")) {
    try {
      const expanded = expandIPv6(ip);
      if (expanded !== null) {
        // Keep first 3 groups (48 bits), zero remaining 5 groups (80 bits)
        const groups = expanded.split(":");
        const anonymized = groups.slice(0, 3).concat(["0", "0", "0", "0", "0"]);
        // Re-compress: replace longest run of consecutive "0" groups with ::
        return compressIPv6(anonymized);
      }
    } catch {
      // Fall through to returning the original on any parse error
    }
  }

  // Unknown format — return as-is rather than crashing
  return ip;
}

/** Expand a potentially compressed IPv6 address to 8 colon-separated groups. */
function expandIPv6(ip: string): string | null {
  // Handle IPv4-mapped addresses (::ffff:x.x.x.x)
  const ipv4MappedRe = /^::ffff:(\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3})$/i;
  if (ipv4MappedRe.test(ip)) {
    // Treat as plain IPv6 by replacing the IPv4 suffix with hex groups
    const parts = ip.split("::");
    // Convert to all-zero prefix with the mapped portion — zero last 5 groups
    return "0:0:0:0:0:ffff:0:0";
  }

  const halves = ip.split("::");
  if (halves.length > 2) return null; // malformed

  const left = halves[0] ? halves[0].split(":") : [];
  const right = halves[1] ? halves[1].split(":") : [];
  const missing = 8 - left.length - right.length;
  if (missing < 0) return null;

  const full = [...left, ...Array(missing).fill("0"), ...right];
  if (full.length !== 8) return null;

  return full.map((g) => g.padStart(1, "0")).join(":");
}

/** Compress an 8-element IPv6 group array back to canonical :: notation. */
function compressIPv6(groups: string[]): string {
  // Find the longest consecutive run of "0" groups
  let bestStart = -1;
  let bestLen = 0;
  let curStart = -1;
  let curLen = 0;

  for (let i = 0; i < groups.length; i++) {
    if (groups[i] === "0") {
      if (curStart === -1) {
        curStart = i;
        curLen = 1;
      } else {
        curLen++;
      }
      if (curLen > bestLen) {
        bestLen = curLen;
        bestStart = curStart;
      }
    } else {
      curStart = -1;
      curLen = 0;
    }
  }

  if (bestLen < 2) {
    // No run worth compressing
    return groups.join(":");
  }

  const left = groups.slice(0, bestStart).join(":");
  const right = groups.slice(bestStart + bestLen).join(":");

  if (!left && !right) return "::";
  if (!left) return `::${right}`;
  if (!right) return `${left}::`;
  return `${left}::${right}`;
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
 *
 * The ``clientIp`` is anonymized before being included in the log entry so
 * that full IP addresses are never persisted in Cloudflare Worker logs.
 * IPv4: last octet zeroed (x.x.x.0).
 * IPv6: last 80 bits zeroed (keeps first 48-bit network prefix only).
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
    clientIp: anonymizeIp(params.clientIp),
    cacheStatus: params.cacheStatus,
    rateLimited: params.rateLimited,
    botScore: params.botScore,
  };
}
