import type { Env, CacheConfig, CacheEntry } from "../types";
import { buildCacheKey } from "../router";
import { CACHE_KEY_PREFIX, PRICE_CACHE_PATTERNS } from "../config";

/**
 * Try to serve a cached response.
 * Returns [Response, cacheStatus] or [null, "MISS"].
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
  const cache = caches.default;
  const cacheUrl = new URL(`https://cache.internal/${cacheKey}`);
  const cachedResponse = await cache.match(new Request(cacheUrl));
  if (cachedResponse) {
    return [cachedResponse, "HIT"];
  }

  // Tier 2: KV (global, consistent)
  const kvEntry = await env.CACHE.get(cacheKey, "text");
  if (kvEntry) {
    try {
      const entry: CacheEntry = JSON.parse(kvEntry);
      const age = Math.floor(Date.now() / 1000) - entry.storedAt;

      if (age <= entry.ttlSeconds) {
        // Fresh — serve from KV and populate Cache API in background
        const response = buildCachedResponse(entry, "HIT");
        ctx.waitUntil(populateCacheApi(cache, cacheUrl, entry));
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

  return [null, "MISS"];
}

/**
 * Store a response in both cache tiers.
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

  const entry: CacheEntry = {
    body,
    headers: Object.fromEntries(response.headers.entries()),
    status: response.status,
    storedAt: Math.floor(Date.now() / 1000),
    ttlSeconds: cacheConfig.ttlSeconds,
  };

  // Store in KV (global) — TTL includes SWR window
  const kvTtl = cacheConfig.ttlSeconds + (cacheConfig.staleWhileRevalidateSeconds ?? 0) + 60;
  ctx.waitUntil(
    env.CACHE.put(cacheKey, JSON.stringify(entry), { expirationTtl: kvTtl })
  );

  // Store in Cache API (per-colo)
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
}

/**
 * Invalidate all price-related cache entries.
 * Called after a successful POST /prices/refresh.
 */
export async function invalidatePriceCache(
  env: Env,
  ctx: ExecutionContext
): Promise<void> {
  const cache = caches.default;

  // KV: list and delete keys with price prefixes
  // Note: KV list is eventually consistent, but good enough for cache invalidation
  const deletePromises: Promise<void>[] = [];

  for (const prefix of PRICE_CACHE_PATTERNS) {
    const list = await env.CACHE.list({ prefix });
    for (const key of list.keys) {
      deletePromises.push(env.CACHE.delete(key.name));
      const cacheUrl = new URL(`https://cache.internal/${key.name}`);
      deletePromises.push(cache.delete(new Request(cacheUrl)).then(() => {}));
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
  cache: Cache,
  cacheUrl: URL,
  entry: CacheEntry
): Promise<void> {
  const remainingTtl = entry.ttlSeconds - (Math.floor(Date.now() / 1000) - entry.storedAt);
  if (remainingTtl <= 0) return;

  const response = new Response(entry.body, {
    status: entry.status,
    headers: {
      ...entry.headers,
      "Cache-Control": `public, max-age=${remainingTtl}`,
      "X-Cache": "HIT",
    },
  });
  await cache.put(new Request(cacheUrl), response);
}
