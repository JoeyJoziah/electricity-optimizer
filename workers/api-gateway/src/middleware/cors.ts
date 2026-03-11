import type { Env } from "../types";

const CORS_MAX_AGE = "86400"; // 24 hours

/**
 * Handle CORS preflight (OPTIONS) requests.
 * Returns a Response if this is an OPTIONS request, null otherwise.
 */
export function handleCorsPreflightOrNull(
  request: Request,
  env: Env
): Response | null {
  if (request.method !== "OPTIONS") return null;

  const origin = request.headers.get("Origin");
  if (!origin) {
    return new Response(null, { status: 204 });
  }

  const allowedOrigins = env.ALLOWED_ORIGINS.split(",");
  if (!allowedOrigins.includes(origin)) {
    return new Response(null, { status: 403 });
  }

  return new Response(null, {
    status: 204,
    headers: {
      "Access-Control-Allow-Origin": origin,
      "Access-Control-Allow-Methods": "GET, POST, PUT, PATCH, DELETE, OPTIONS",
      "Access-Control-Allow-Headers":
        "Content-Type, Authorization, X-API-Key, X-Request-ID",
      "Access-Control-Allow-Credentials": "true",
      "Access-Control-Max-Age": CORS_MAX_AGE,
    },
  });
}

/**
 * Apply CORS headers to a response.
 */
export function applyCorsHeaders(
  response: Response,
  request: Request,
  env: Env
): Response {
  const origin = request.headers.get("Origin");
  if (!origin) return response;

  const allowedOrigins = env.ALLOWED_ORIGINS.split(",");
  if (!allowedOrigins.includes(origin)) return response;

  const newResponse = new Response(response.body, response);
  newResponse.headers.set("Access-Control-Allow-Origin", origin);
  newResponse.headers.set("Access-Control-Allow-Credentials", "true");
  newResponse.headers.set(
    "Access-Control-Expose-Headers",
    "X-Request-ID, X-Cache, X-Edge-Colo, X-RateLimit-Remaining"
  );
  return newResponse;
}
