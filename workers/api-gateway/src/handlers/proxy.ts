import type { Env } from "../types";

/**
 * Proxy a request to the Render origin.
 * Preserves all headers including Cookie for session auth passthrough.
 */
export async function proxyToOrigin(
  request: Request,
  env: Env,
  requestId: string,
  clientIp: string
): Promise<Response> {
  const url = new URL(request.url);
  const originUrl = new URL(url.pathname + url.search, env.ORIGIN_URL);

  // Build forwarded headers
  const headers = new Headers(request.headers);
  headers.set("X-Forwarded-For", clientIp);
  headers.set("X-Real-IP", clientIp);
  headers.set("X-Request-ID", requestId);
  headers.set("X-Forwarded-Host", url.hostname);
  headers.set("X-Forwarded-Proto", "https");
  // Remove CF-specific headers that shouldn't reach origin
  headers.delete("cf-connecting-ip");
  headers.delete("cf-ipcountry");
  headers.delete("cf-ray");
  headers.delete("cf-visitor");

  // Forward body for methods that support it
  const hasBody = ["POST", "PUT", "PATCH"].includes(request.method);

  const originResponse = await fetch(originUrl.toString(), {
    method: request.method,
    headers,
    body: hasBody ? request.body : undefined,
    redirect: "manual", // pass through redirects as-is
  });

  // Clone response so we can modify headers
  const response = new Response(originResponse.body, {
    status: originResponse.status,
    statusText: originResponse.statusText,
    headers: originResponse.headers,
  });

  return response;
}
