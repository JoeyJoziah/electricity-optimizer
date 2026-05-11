import type { Env } from "../types";

// Origin fetch timeout. Render Free tier cold-start + 30s app boot has been
// observed at 30-60s, so 25s is a calibrated middle ground: long enough that
// a healthy origin always answers, short enough to fail before CF's wall-time
// limit (30s Free / 50ms-30s+ Paid) kills the isolate with no error context.
const ORIGIN_FETCH_TIMEOUT_MS = 25_000;

/**
 * Proxy a request to the Render origin.
 * Preserves all headers including Cookie for session auth passthrough.
 *
 * Cancellation: forwards `request.signal` so the origin fetch aborts when
 * the client disconnects, saving CF CPU time and origin resources. Also
 * applies an explicit 25s timeout — if the origin hangs, returns 504 with
 * a useful error body instead of letting CF wall-time-kill the isolate.
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
  // Explicitly set Host to the origin hostname to prevent SSRF via
  // Host header manipulation. The client-supplied Host header must not
  // reach the origin — the origin should only see its own hostname.
  headers.set("Host", originUrl.hostname);
  // Remove CF-specific headers that shouldn't reach origin
  headers.delete("cf-connecting-ip");
  headers.delete("cf-ipcountry");
  headers.delete("cf-ray");
  headers.delete("cf-visitor");

  // Forward body for methods that support it
  const hasBody = ["POST", "PUT", "PATCH"].includes(request.method);

  // Compose two cancellation signals: client disconnect + explicit timeout.
  // AbortSignal.any short-circuits the origin fetch if either fires.
  const timeoutSignal = AbortSignal.timeout(ORIGIN_FETCH_TIMEOUT_MS);
  const signal = AbortSignal.any([request.signal, timeoutSignal]);

  let originResponse: Response;
  try {
    originResponse = await fetch(originUrl.toString(), {
      method: request.method,
      headers,
      body: hasBody ? request.body : undefined,
      redirect: "manual", // pass through redirects as-is
      signal,
    });
  } catch (err) {
    // AbortSignal.timeout throws TimeoutError; client disconnect throws AbortError.
    const isTimeout = err instanceof Error && err.name === "TimeoutError";
    const isClientAbort = err instanceof Error && err.name === "AbortError";
    if (isTimeout) {
      console.warn(`Origin fetch timed out after ${ORIGIN_FETCH_TIMEOUT_MS}ms: ${originUrl}`);
      return new Response(
        JSON.stringify({
          error: "Gateway Timeout",
          requestId,
          detail: "Origin server did not respond within 25 seconds",
        }),
        {
          status: 504,
          headers: {
            "Content-Type": "application/json",
            "Retry-After": "10",
          },
        }
      );
    }
    if (isClientAbort) {
      // Client disconnected before origin responded. Return 499 (nginx
      // convention) so observability counts these distinctly from 5xx.
      return new Response(null, { status: 499 });
    }
    throw err;
  }

  // Clone response headers so we can modify them
  const responseHeaders = new Headers(originResponse.headers);

  // Rewrite Location headers on redirects to prevent leaking the origin URL.
  // FastAPI's trailing-slash redirects (307) include the raw Render hostname
  // which causes CORS failures when browsers follow the redirect.
  //
  // Use a RELATIVE URL (path only) so the browser resolves the redirect
  // against its current origin. This handles both direct requests (browser →
  // api.rateshift.app) and proxied requests (browser → rateshift.app →
  // Vercel rewrite → api.rateshift.app). With a relative Location, the
  // redirect stays on the browser's original origin and session cookies
  // are preserved.
  const location = responseHeaders.get("Location");
  if (location && env.ORIGIN_URL) {
    const originHost = new URL(env.ORIGIN_URL).origin;
    if (location.startsWith(originHost)) {
      const relativePath = location.slice(originHost.length);
      responseHeaders.set("Location", relativePath);
    }
  }

  const response = new Response(originResponse.body, {
    status: originResponse.status,
    statusText: originResponse.statusText,
    headers: responseHeaders,
  });

  return response;
}
