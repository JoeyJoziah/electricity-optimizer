/**
 * Cloudflare Turnstile server-side verifier.
 *
 * Audit ref: P1-7. Frontend widget (`TurnstileWidget.tsx`) emits an
 * `X-Turnstile-Token` header on signup; this module validates that token
 * against `https://challenges.cloudflare.com/turnstile/v0/siteverify` so a
 * `curl` bypass of the frontend gate cannot create accounts.
 *
 * Engages only when `TURNSTILE_SECRET_KEY` is set. When unset (dev/test),
 * verification is skipped — the widget's dev sentinel passes through.
 * When the secret IS set, the dev sentinel is rejected outright (defense
 * against a misconfigured frontend leaking the sentinel into prod traffic).
 */

const SITEVERIFY_URL =
  "https://challenges.cloudflare.com/turnstile/v0/siteverify";

const DEV_SENTINEL = "turnstile-not-configured-dev-only";

export interface TurnstileResult {
  ok: boolean;
  /** Reason code for logging; not exposed to clients. */
  reason?: string;
}

interface SiteverifyResponse {
  success: boolean;
  "error-codes"?: string[];
  hostname?: string;
  action?: string;
}

/**
 * Verify a Turnstile token. Returns `{ ok: true }` when validation is
 * disabled (no secret configured) or when CF accepts the token.
 *
 * `remoteIp` is optional — Cloudflare uses it as a soft signal but doesn't
 * require it.
 */
export async function verifyTurnstileToken(
  token: string | null | undefined,
  remoteIp?: string | null,
): Promise<TurnstileResult> {
  const secret = process.env.TURNSTILE_SECRET_KEY;

  if (!secret) {
    return { ok: true, reason: "validator_disabled" };
  }

  if (!token) {
    return { ok: false, reason: "missing_token" };
  }

  if (token === DEV_SENTINEL) {
    return { ok: false, reason: "dev_sentinel_in_production" };
  }

  const body = new URLSearchParams({ secret, response: token });
  if (remoteIp) body.set("remoteip", remoteIp);

  let response: Response;
  try {
    response = await fetch(SITEVERIFY_URL, {
      method: "POST",
      headers: { "content-type": "application/x-www-form-urlencoded" },
      body,
    });
  } catch {
    return { ok: false, reason: "siteverify_unreachable" };
  }

  if (!response.ok) {
    return { ok: false, reason: `siteverify_http_${response.status}` };
  }

  let data: SiteverifyResponse;
  try {
    data = (await response.json()) as SiteverifyResponse;
  } catch {
    return { ok: false, reason: "siteverify_invalid_json" };
  }

  if (!data.success) {
    return {
      ok: false,
      reason: `siteverify_rejected:${(data["error-codes"] ?? []).join(",")}`,
    };
  }

  return { ok: true };
}

/**
 * Whether a Better Auth request path requires Turnstile validation.
 *
 * Better Auth routes signup at `/api/auth/sign-up/email`. We match on the
 * suffix so a hosted-domain prefix doesn't break the check.
 */
export function requiresTurnstile(method: string, pathname: string): boolean {
  if (method !== "POST") return false;
  return pathname.endsWith("/sign-up/email");
}
