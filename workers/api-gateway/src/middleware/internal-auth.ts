import type { Env } from "../types";

/**
 * Validate X-API-Key header for internal endpoints.
 * Uses crypto.subtle.timingSafeEqual for constant-time comparison to
 * prevent timing attacks.
 *
 * Returns null if the request is authenticated, or a Response (401/503)
 * if it should be rejected.
 */
export async function validateInternalAuth(
  request: Request,
  env: Env
): Promise<Response | null> {
  // Fail-closed: if the secret is not configured, refuse all requests rather
  // than allowing unauthenticated access to internal endpoints.
  if (!env.INTERNAL_API_KEY) {
    return new Response(
      JSON.stringify({ error: "Internal auth not configured" }),
      {
        status: 503,
        headers: { "Content-Type": "application/json" },
      }
    );
  }

  const apiKey = request.headers.get("X-API-Key");
  if (!apiKey) {
    return new Response(
      JSON.stringify({ error: "Missing X-API-Key header" }),
      {
        status: 401,
        headers: { "Content-Type": "application/json" },
      }
    );
  }

  const isValid = await timingSafeEqual(apiKey, env.INTERNAL_API_KEY);
  if (!isValid) {
    return new Response(
      JSON.stringify({ error: "Invalid API key" }),
      {
        status: 401,
        headers: { "Content-Type": "application/json" },
      }
    );
  }

  return null; // authenticated
}

/**
 * Constant-time string comparison.
 *
 * Uses crypto.subtle.timingSafeEqual when available (Cloudflare Workers runtime).
 * Falls back to a constant-time XOR accumulator for Node.js test environments.
 */
async function timingSafeEqual(a: string, b: string): Promise<boolean> {
  const encoder = new TextEncoder();
  const aBytes = encoder.encode(a);
  const bBytes = encoder.encode(b);

  // Use crypto.subtle.timingSafeEqual if available (Cloudflare Workers runtime)
  const subtle = crypto?.subtle as any;
  if (subtle && typeof subtle.timingSafeEqual === "function") {
    if (aBytes.byteLength !== bBytes.byteLength) {
      const dummy = new Uint8Array(bBytes.byteLength);
      await subtle.timingSafeEqual(dummy, bBytes);
      return false;
    }
    return subtle.timingSafeEqual(aBytes, bBytes);
  }

  // Fallback: constant-time XOR accumulator (processes max-length to avoid
  // timing leak on length difference)
  const maxLen = Math.max(aBytes.byteLength, bBytes.byteLength);
  let result = aBytes.byteLength ^ bBytes.byteLength; // non-zero if lengths differ
  for (let i = 0; i < maxLen; i++) {
    result |= (aBytes[i] ?? 0) ^ (bBytes[i] ?? 0);
  }
  return result === 0;
}
