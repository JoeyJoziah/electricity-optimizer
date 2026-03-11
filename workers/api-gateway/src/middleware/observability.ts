import type { LogEntry } from "../types";

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
