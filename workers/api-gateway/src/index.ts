import type { Env, LogEntry } from "./types";
import { matchRoute } from "./router";
import { handleCorsPreflightOrNull, applyCorsHeaders } from "./middleware/cors";
import { checkRateLimit, rateLimitHeaders, rateLimitResponse } from "./middleware/rate-limiter";
import { tryCache, storeInCache, invalidatePriceCache } from "./middleware/cache";
import { calculateBotScore, shouldBlockBot, applySecurityHeaders } from "./middleware/security";
import { validateInternalAuth } from "./middleware/internal-auth";
import { logRequest, buildLogEntry } from "./middleware/observability";
import { proxyToOrigin } from "./handlers/proxy";

export default {
  async fetch(
    request: Request,
    env: Env,
    ctx: ExecutionContext
  ): Promise<Response> {
    const startTime = Date.now();
    const requestId = crypto.randomUUID();
    const clientIp =
      request.headers.get("CF-Connecting-IP") ??
      request.headers.get("X-Forwarded-For")?.split(",")[0]?.trim() ??
      "unknown";
    const colo = (request.cf?.colo as string) ?? "unknown";
    const url = new URL(request.url);

    let cacheStatus: LogEntry["cacheStatus"] = "BYPASS";
    let rateLimited = false;
    let botScore: number | undefined;

    try {
      // 1. CORS preflight fast path
      const corsResponse = handleCorsPreflightOrNull(request, env);
      if (corsResponse) {
        return applySecurityHeaders(corsResponse, requestId, colo);
      }

      // 2. Route matching
      const route = matchRoute(url.pathname);

      // 3. Bot detection (skip for internal endpoints — they use API keys)
      if (!route.requireApiKey) {
        botScore = calculateBotScore(request);
        if (shouldBlockBot(botScore)) {
          return applySecurityHeaders(
            new Response(JSON.stringify({ error: "Forbidden" }), {
              status: 403,
              headers: { "Content-Type": "application/json" },
            }),
            requestId,
            colo
          );
        }
      }

      // 4. Internal API key validation (early 401 rejection)
      if (route.requireApiKey) {
        const authError = validateInternalAuth(request, env);
        if (authError) {
          return applySecurityHeaders(authError, requestId, colo);
        }
      }

      // 5. Rate limiting
      const rlResult = await checkRateLimit(clientIp, route.rateLimit, request, env);
      if (!rlResult.allowed) {
        rateLimited = true;
        const rlResponse = rateLimitResponse(rlResult);
        return applySecurityHeaders(
          applyCorsHeaders(rlResponse, request, env),
          requestId,
          colo
        );
      }

      // 6. Cache check (only for GET requests with cache config)
      if (route.cache && !route.passthrough) {
        const [cachedResponse, status] = await tryCache(
          request,
          route.cache,
          url,
          env,
          ctx
        );
        cacheStatus = status;

        if (cachedResponse && status === "HIT") {
          let response = cachedResponse;
          // Add rate limit headers
          const rlHeaders = rateLimitHeaders(rlResult);
          response = new Response(response.body, response);
          for (const [key, value] of Object.entries(rlHeaders)) {
            response.headers.set(key, value);
          }
          return applySecurityHeaders(
            applyCorsHeaders(response, request, env),
            requestId,
            colo
          );
        }

        if (cachedResponse && status === "STALE") {
          // Serve stale immediately, refresh in background
          ctx.waitUntil(
            refreshCache(request, route.cache, url, env, ctx, requestId, clientIp)
          );
          let response = cachedResponse;
          const rlHeaders = rateLimitHeaders(rlResult);
          response = new Response(response.body, response);
          for (const [key, value] of Object.entries(rlHeaders)) {
            response.headers.set(key, value);
          }
          return applySecurityHeaders(
            applyCorsHeaders(response, request, env),
            requestId,
            colo
          );
        }

        // Cache miss — fall through to origin fetch
        cacheStatus = "MISS";
      }

      // 7. Proxy to origin
      let response = await proxyToOrigin(request, env, requestId, clientIp);

      // Cache the response if cacheable
      if (route.cache && !route.passthrough && response.status === 200) {
        ctx.waitUntil(storeInCache(response, route.cache, url, env, ctx));
      }

      // Handle cache invalidation on /prices/refresh success
      if (
        url.pathname === "/api/v1/prices/refresh" &&
        request.method === "POST" &&
        response.status === 200
      ) {
        ctx.waitUntil(invalidatePriceCache(env, ctx));
      }

      // Add cache status and rate limit headers
      response = new Response(response.body, response);
      response.headers.set("X-Cache", cacheStatus);
      const rlHeaders = rateLimitHeaders(rlResult);
      for (const [key, value] of Object.entries(rlHeaders)) {
        response.headers.set(key, value);
      }

      // 8. Security headers + CORS
      return applySecurityHeaders(
        applyCorsHeaders(response, request, env),
        requestId,
        colo
      );
    } catch (err) {
      const errorMessage = err instanceof Error ? err.message : "Internal error";
      console.error(`Worker error: ${errorMessage}`, err);

      return applySecurityHeaders(
        new Response(
          JSON.stringify({ error: "Gateway error", requestId }),
          {
            status: 502,
            headers: { "Content-Type": "application/json" },
          }
        ),
        requestId,
        colo
      );
    } finally {
      // 9. Non-blocking observability logging
      ctx.waitUntil(
        Promise.resolve().then(() =>
          logRequest(
            buildLogEntry({
              requestId,
              method: request.method,
              path: url.pathname,
              status: 0, // logged before we know — structured log enriched by CF
              startTime,
              colo,
              clientIp,
              cacheStatus,
              rateLimited,
              botScore,
            })
          )
        )
      );
    }
  },
} satisfies ExportedHandler<Env>;

/**
 * Background refresh: fetch from origin and update cache.
 */
async function refreshCache(
  request: Request,
  cacheConfig: NonNullable<import("./types").RouteConfig["cache"]>,
  url: URL,
  env: Env,
  ctx: ExecutionContext,
  requestId: string,
  clientIp: string
): Promise<void> {
  try {
    const response = await proxyToOrigin(request, env, requestId, clientIp);
    if (response.status === 200) {
      await storeInCache(response, cacheConfig, url, env, ctx);
    }
  } catch {
    // Background refresh failure is non-critical
  }
}
