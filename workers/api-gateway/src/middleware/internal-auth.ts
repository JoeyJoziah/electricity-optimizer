import type { Env } from "../types";

/**
 * Validate X-API-Key header for internal endpoints.
 * Uses constant-time comparison to prevent timing attacks.
 * Returns null if valid, or a 401 Response if invalid.
 */
export function validateInternalAuth(
  request: Request,
  env: Env
): Response | null {
  // Fail-open if edge key is not configured (let backend handle it)
  if (!env.INTERNAL_API_KEY) {
    return null;
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

  if (!constantTimeEqual(apiKey, env.INTERNAL_API_KEY)) {
    return new Response(
      JSON.stringify({ error: "Invalid API key" }),
      {
        status: 401,
        headers: { "Content-Type": "application/json" },
      }
    );
  }

  return null; // valid
}

/**
 * Constant-time string comparison to prevent timing attacks.
 */
function constantTimeEqual(a: string, b: string): boolean {
  if (a.length !== b.length) {
    // Still do a comparison to keep timing more consistent
    const dummy = new Uint8Array(a.length);
    const dummyB = new Uint8Array(a.length);
    for (let i = 0; i < a.length; i++) {
      dummy[i] = a.charCodeAt(i);
      dummyB[i] = a.charCodeAt(i);
    }
    let result = 0;
    for (let i = 0; i < dummy.length; i++) {
      result |= dummy[i] ^ dummyB[i];
    }
    return false;
  }

  const encoder = new TextEncoder();
  const aBytes = encoder.encode(a);
  const bBytes = encoder.encode(b);
  let result = 0;
  for (let i = 0; i < aBytes.length; i++) {
    result |= aBytes[i] ^ bBytes[i];
  }
  return result === 0;
}
