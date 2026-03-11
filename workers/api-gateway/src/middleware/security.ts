/**
 * Heuristic bot detection scoring.
 * Returns a score 0-100: < 20 = block, 20-50 = suspicious, > 50 = allow.
 */
export function calculateBotScore(request: Request): number {
  let score = 50; // baseline

  const ua = request.headers.get("User-Agent") ?? "";
  const accept = request.headers.get("Accept") ?? "";

  // No User-Agent is highly suspicious
  if (!ua) {
    score -= 30;
  } else {
    // Known bot patterns
    const botPatterns = /bot|crawler|spider|scraper|curl|wget|httpie|python-requests|go-http|java\//i;
    if (botPatterns.test(ua)) {
      score -= 20;
    }
    // Browser-like UAs get a bonus
    if (/Mozilla\/5\.0/.test(ua) && /Chrome|Firefox|Safari|Edge/.test(ua)) {
      score += 20;
    }
  }

  // No Accept header is suspicious
  if (!accept) {
    score -= 15;
  } else if (accept.includes("text/html") || accept.includes("application/json")) {
    score += 10;
  }

  // Check for common browser headers
  if (request.headers.get("Accept-Language")) {
    score += 5;
  }
  if (request.headers.get("Accept-Encoding")) {
    score += 5;
  }

  return Math.max(0, Math.min(100, score));
}

/**
 * Check if request should be blocked based on bot score.
 */
export function shouldBlockBot(score: number): boolean {
  return score < 20;
}

/**
 * Security headers to inject into every response.
 */
export function getSecurityHeaders(requestId: string, colo: string): Record<string, string> {
  return {
    "X-Content-Type-Options": "nosniff",
    "X-Frame-Options": "DENY",
    "Strict-Transport-Security": "max-age=31536000; includeSubDomains",
    "Referrer-Policy": "strict-origin-when-cross-origin",
    "X-Request-ID": requestId,
    "X-Edge-Colo": colo,
  };
}

/**
 * Apply security headers to a response.
 */
export function applySecurityHeaders(
  response: Response,
  requestId: string,
  colo: string
): Response {
  const newResponse = new Response(response.body, response);
  const headers = getSecurityHeaders(requestId, colo);
  for (const [key, value] of Object.entries(headers)) {
    newResponse.headers.set(key, value);
  }
  return newResponse;
}
