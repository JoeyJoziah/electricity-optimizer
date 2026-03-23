import type { Env, RateLimitBinding, RateLimitResult, RateLimitTier } from "../types";
import { timingSafeEqual } from "./internal-auth";

/**
 * Rate limiter using Cloudflare's native rate limiting bindings.
 * Zero KV operations — counters maintained in-memory at each edge PoP.
 *
 * Graceful degradation: if the native binding call fails, the rate limiter
 * fails OPEN — requests are allowed through without rate limiting rather
 * than returning 502 errors.
 */
export async function checkRateLimit(
  clientIp: string,
  tier: RateLimitTier,
  request: Request,
  env: Env
): Promise<RateLimitResult> {
  // Bypass tier skips rate limiting entirely
  if (tier === "bypass") {
    return { allowed: true, remaining: Infinity, limit: Infinity, resetAt: 0 };
  }

  // Check bypass header for GHA cron workflows — only allowed for internal
  // tier (requireApiKey routes). NEVER bypass strict (auth) or standard tiers.
  if (tier === "internal") {
    const bypassKey = request.headers.get("X-RateLimit-Bypass");
    if (bypassKey && env.RATE_LIMIT_BYPASS_KEY) {
      const match = await timingSafeEqual(bypassKey, env.RATE_LIMIT_BYPASS_KEY);
      if (match) {
        return { allowed: true, remaining: Infinity, limit: Infinity, resetAt: 0 };
      }
    }
  }

  const binding = getTierBinding(tier, env);
  const limit = getTierLimit(tier);

  // Calculate window reset time (60s windows to match binding config)
  const now = Math.floor(Date.now() / 1000);
  const windowStart = now - (now % 60);
  const windowEnd = windowStart + 60;

  // Call native rate limiter — fail open on error
  try {
    const { success } = await binding.limit({ key: clientIp });

    if (!success) {
      return {
        allowed: false,
        remaining: 0,
        limit,
        resetAt: windowEnd,
      };
    }

    return {
      allowed: true,
      remaining: -1, // native binding doesn't expose remaining count
      limit,
      resetAt: windowEnd,
    };
  } catch (err) {
    console.warn(`Rate limiter binding failed (fail-open): ${err}`);
    return { allowed: true, remaining: -1, limit, resetAt: 0, degraded: true };
  }
}

function getTierBinding(tier: RateLimitTier, env: Env): RateLimitBinding {
  switch (tier) {
    case "standard":
      return env.RATE_LIMITER_STANDARD;
    case "strict":
      return env.RATE_LIMITER_STRICT;
    case "internal":
      return env.RATE_LIMITER_INTERNAL;
    default:
      return env.RATE_LIMITER_STANDARD;
  }
}

function getTierLimit(tier: RateLimitTier): number {
  switch (tier) {
    case "standard":
      return 120;
    case "strict":
      return 30;
    case "internal":
      return 600;
    default:
      return 120;
  }
}

/**
 * Build rate limit headers for the response.
 */
export function rateLimitHeaders(result: RateLimitResult): Record<string, string> {
  if (result.limit === Infinity) return {};
  const headers: Record<string, string> = {
    "X-RateLimit-Limit": String(result.limit),
    "X-RateLimit-Reset": String(result.resetAt),
  };
  // Only include remaining if we have a meaningful value
  if (result.remaining >= 0) {
    headers["X-RateLimit-Remaining"] = String(result.remaining);
  }
  return headers;
}

/**
 * Build a 429 Too Many Requests response.
 */
export function rateLimitResponse(result: RateLimitResult): Response {
  const retryAfter = Math.max(1, result.resetAt - Math.floor(Date.now() / 1000));
  return new Response(
    JSON.stringify({
      error: "Too Many Requests",
      retryAfter,
    }),
    {
      status: 429,
      headers: {
        "Content-Type": "application/json",
        "Retry-After": String(retryAfter),
        ...rateLimitHeaders(result),
      },
    }
  );
}
