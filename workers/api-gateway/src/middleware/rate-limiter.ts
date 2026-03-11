import type { Env, RateLimitResult, RateLimitTier } from "../types";

/**
 * Fixed-window rate limiter using KV.
 * Each window is keyed by IP + tier + window start timestamp.
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

  // Check bypass header for GHA cron workflows
  const bypassKey = request.headers.get("X-RateLimit-Bypass");
  if (bypassKey && env.RATE_LIMIT_BYPASS_KEY && bypassKey === env.RATE_LIMIT_BYPASS_KEY) {
    return { allowed: true, remaining: Infinity, limit: Infinity, resetAt: 0 };
  }

  const limit = getTierLimit(tier, env);
  const windowSeconds = parseInt(env.RATE_LIMIT_WINDOW_SECONDS, 10) || 60;
  const now = Math.floor(Date.now() / 1000);
  const windowStart = now - (now % windowSeconds);
  const windowEnd = windowStart + windowSeconds;

  const key = `rl:${clientIp}:${tier}:${windowStart}`;

  // Read current count
  const currentStr = await env.RATE_LIMIT.get(key);
  const current = currentStr ? parseInt(currentStr, 10) : 0;

  if (current >= limit) {
    return {
      allowed: false,
      remaining: 0,
      limit,
      resetAt: windowEnd,
    };
  }

  // Increment counter (fire-and-forget is fine for rate limiting)
  const ttl = windowSeconds + 10; // slight buffer past window end
  await env.RATE_LIMIT.put(key, String(current + 1), {
    expirationTtl: ttl,
  });

  return {
    allowed: true,
    remaining: limit - current - 1,
    limit,
    resetAt: windowEnd,
  };
}

function getTierLimit(tier: RateLimitTier, env: Env): number {
  switch (tier) {
    case "standard":
      return parseInt(env.RATE_LIMIT_STANDARD, 10) || 120;
    case "strict":
      return parseInt(env.RATE_LIMIT_STRICT, 10) || 30;
    case "internal":
      return parseInt(env.RATE_LIMIT_INTERNAL, 10) || 600;
    default:
      return 120;
  }
}

/**
 * Build rate limit headers for the response.
 */
export function rateLimitHeaders(result: RateLimitResult): Record<string, string> {
  if (result.limit === Infinity) return {};
  return {
    "X-RateLimit-Limit": String(result.limit),
    "X-RateLimit-Remaining": String(Math.max(0, result.remaining)),
    "X-RateLimit-Reset": String(result.resetAt),
  };
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
