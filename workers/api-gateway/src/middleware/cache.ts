import type { Env, CacheConfig, CacheEntry } from "../types";
import { buildCacheKey } from "../router";
import { CACHE_KEY_PREFIX, PRICE_CACHE_PATTERNS } from "../config";

/**
 * Try to serve a cached response.
 * Returns [Response, cacheStatus] or [null, "MISS"].
 *
 * Graceful degradation: if KV read fails, returns MISS (falls through to origin).
 */
export async function tryCache(
  request: Request,
  cacheConfig: CacheConfig,
  url: URL,
  env: Env,
  ctx: ExecutionContext
): Promise<[Response | null, "HIT" | "MISS" | "STALE"]> {
  if (request.method !== "GET") {
    return [null, "MISS"];
  }

  const cacheKey = buildCacheKey(url.pathname, url.searchParams, cacheConfig.varyOn);

  // Tier 1: Cloudflare Cache API (per-colo, sub-ms)
  try {
    const cache = caches.default;
    const cacheUrl = new URL(`https://cache.internal/${cacheKey}`);
    const cachedResponse = await cache.match(new Request(cacheUrl));
    if (cachedResponse) {
      return [cachedResponse, "HIT"];
    }
  } catch (err) {
    console.warn(`Cache API read failed (non-fatal): ${err}`);
  }

  // Tier 2: KV (global, consistent) — fail open on error
  try {
    const kvEntry = await env.CACHE.get(cacheKey, { type: "text", cacheTtl: 30 });
    if (kvEntry) {
      try {
        const entry: CacheEntry = JSON.parse(kvEntry);
        const age = Math.floor(Date.now() / 1000) - entry.storedAt;

        if (age <= entry.ttlSeconds) {
          // Fresh — serve from KV and populate Cache API in background
          const response = buildCachedResponse(entry, "HIT");
          ctx.waitUntil(populateCacheApi(cacheKey, entry));
          return [response, "HIT"];
        }

        // Stale but within SWR window — serve stale, refresh in background
        const swrSeconds = cacheConfig.staleWhileRevalidateSeconds ?? 0;
        if (swrSeconds > 0 && age <= entry.ttlSeconds + swrSeconds) {
          const response = buildCachedResponse(entry, "STALE");
          return [response, "STALE"];
        }
      } catch {
        // Corrupted KV entry — treat as miss
      }
    }
  } catch (err) {
    console.warn(`Cache KV read failed (fall through to origin): ${err}`);
  }

  return [null, "MISS"];
}

/**
 * Store a response in both cache tiers.
 *
 * Graceful degradation: if KV write fails, logs warning and continues.
 * The response has already been served to the client.
 */
export async function storeInCache(
  response: Response,
  cacheConfig: CacheConfig,
  url: URL,
  env: Env,
  ctx: ExecutionContext
): Promise<void> {
  if (response.status !== 200) return;

  const cacheKey = buildCacheKey(url.pathname, url.searchParams, cacheConfig.varyOn);
  const body = await response.clone().text();

  // Build stored headers, adding Vary for proper downstream cache discrimination
  const storedHeaders = Object.fromEntries(response.headers.entries());
  if (cacheConfig.varyOn && cacheConfig.varyOn.length > 0) {
    storedHeaders["Vary"] = cacheConfig.varyOn.join(", ");
  }

  const entry: CacheEntry = {
    body,
    headers: storedHeaders,
    status: response.status,
    storedAt: Math.floor(Date.now() / 1000),
    ttlSeconds: cacheConfig.ttlSeconds,
  };

  // Store in KV (global) — TTL includes SWR window. Fail silently.
  const kvTtl = cacheConfig.ttlSeconds + (cacheConfig.staleWhileRevalidateSeconds ?? 0) + 60;
  try {
    ctx.waitUntil(
      env.CACHE.put(cacheKey, JSON.stringify(entry), { expirationTtl: kvTtl })
    );
  } catch (err) {
    console.warn(`Cache KV write failed (non-fatal): ${err}`);
  }

  // Store in Cache API (per-colo). Fail silently.
  try {
    const cache = caches.default;
    const cacheUrl = new URL(`https://cache.internal/${cacheKey}`);
    const cacheResponse = new Response(body, {
      status: response.status,
      headers: {
        ...Object.fromEntries(response.headers.entries()),
        "Cache-Control": `public, max-age=${cacheConfig.ttlSeconds}`,
        "X-Cache": "HIT",
      },
    });
    ctx.waitUntil(cache.put(new Request(cacheUrl), cacheResponse));
  } catch (err) {
    console.warn(`Cache API write failed (non-fatal): ${err}`);
  }
}

/**
 * Invalidate all price-related cache entries.
 * Called after a successful POST /prices/refresh.
 *
 * Graceful degradation: if KV list/delete fails, logs warning.
 * Stale price data is better than a 502 error.
 */
export async function invalidatePriceCache(
  env: Env,
  ctx: ExecutionContext
): Promise<void> {
  let cache: Cache | undefined;
  try {
    cache = caches.default;
  } catch (err) {
    console.warn(`Cache API unavailable for invalidation (non-fatal): ${err}`);
  }

  const deletePromises: Promise<void>[] = [];

  for (const prefix of PRICE_CACHE_PATTERNS) {
    try {
      const list = await env.CACHE.list({ prefix });
      for (const key of list.keys) {
        deletePromises.push(
          env.CACHE.delete(key.name).catch((err) => {
            console.warn(`Cache KV delete failed for ${key.name} (non-fatal): ${err}`);
          })
        );
        if (cache) {
          const cacheUrl = new URL(`https://cache.internal/${key.name}`);
          deletePromises.push(
            cache.delete(new Request(cacheUrl)).then(() => {}).catch((err) => {
              console.warn(`Cache API delete failed for ${key.name} (non-fatal): ${err}`);
            })
          );
        }
      }
    } catch (err) {
      console.warn(`Cache KV list failed for prefix ${prefix} (non-fatal): ${err}`);
    }
  }

  if (deletePromises.length > 0) {
    ctx.waitUntil(Promise.allSettled(deletePromises));
  }
}

function buildCachedResponse(entry: CacheEntry, cacheStatus: "HIT" | "STALE"): Response {
  const headers = new Headers(entry.headers);
  headers.set("X-Cache", cacheStatus);
  return new Response(entry.body, {
    status: entry.status,
    headers,
  });
}

async function populateCacheApi(
  cacheKey: string,
  entry: CacheEntry
): Promise<void> {
  const remainingTtl = entry.ttlSeconds - (Math.floor(Date.now() / 1000) - entry.storedAt);
  if (remainingTtl <= 0) return;

  try {
    const cache = caches.default;
    const cacheUrl = new URL(`https://cache.internal/${cacheKey}`);
    const response = new Response(entry.body, {
      status: entry.status,
      headers: {
        ...entry.headers,
        "Cache-Control": `public, max-age=${remainingTtl}`,
        "X-Cache": "HIT",
      },
    });
    await cache.put(new Request(cacheUrl), response);
  } catch (err) {
    console.warn(`Cache API population failed (non-fatal): ${err}`);
  }
}
