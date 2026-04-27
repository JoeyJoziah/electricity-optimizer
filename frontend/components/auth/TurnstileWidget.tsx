/**
 * Cloudflare Turnstile widget — invisible / managed CAPTCHA alternative
 * for high-abuse-risk forms (signup, billing checkout).
 *
 * Audit ref: security M-2 / P1-7. Replaces the homegrown user-agent
 * heuristic in workers/api-gateway/src/middleware/security.ts which can
 * be defeated with `curl -H "User-Agent: Mozilla/5.0"`.
 *
 * Usage:
 *   <TurnstileWidget onTokenChange={setToken} />
 *
 * Wiring needed by user (NOT codeable from here):
 *   1. Create a Turnstile site at https://dash.cloudflare.com/?to=/:account/turnstile
 *   2. Set NEXT_PUBLIC_TURNSTILE_SITE_KEY in Vercel env vars (frontend)
 *   3. Set TURNSTILE_SECRET_KEY in Render / backend env vars (validation)
 *   4. Backend signup endpoint must verify the token via
 *      https://challenges.cloudflare.com/turnstile/v0/siteverify
 *
 * When NEXT_PUBLIC_TURNSTILE_SITE_KEY is unset, the widget renders nothing
 * and onTokenChange is called with a sentinel "disabled" value so submit
 * buttons stay enabled in dev/test.
 */

"use client";

import { useEffect, useRef, useState } from "react";

declare global {
  interface Window {
    turnstile?: {
      render: (
        el: HTMLElement,
        opts: {
          sitekey: string;
          callback: (token: string) => void;
          "error-callback"?: () => void;
          "expired-callback"?: () => void;
          theme?: "auto" | "light" | "dark";
          size?: "normal" | "compact";
          appearance?: "always" | "execute" | "interaction-only";
        },
      ) => string;
      remove: (widgetId: string) => void;
      reset: (widgetId: string) => void;
    };
  }
}

const SCRIPT_URL =
  "https://challenges.cloudflare.com/turnstile/v0/api.js?render=explicit";

const SITE_KEY = process.env.NEXT_PUBLIC_TURNSTILE_SITE_KEY ?? "";

// When Turnstile is not configured, signup forms still need to know they
// can submit — they treat any non-empty token as "challenge passed". This
// sentinel keeps dev / test green without leaking into production behavior:
// the backend validator rejects this exact value if TURNSTILE_SECRET_KEY is
// configured.
const DEV_SENTINEL = "turnstile-not-configured-dev-only";

export interface TurnstileWidgetProps {
  /** Called whenever the challenge token changes. Empty string means challenge in progress / failed. */
  onTokenChange: (token: string) => void;
  /** Optional theme override; defaults to auto (matches user OS preference). */
  theme?: "auto" | "light" | "dark";
  /** Optional className for layout integration. */
  className?: string;
}

export function TurnstileWidget({
  onTokenChange,
  theme = "auto",
  className,
}: TurnstileWidgetProps) {
  const containerRef = useRef<HTMLDivElement | null>(null);
  const widgetIdRef = useRef<string | null>(null);
  const [scriptLoaded, setScriptLoaded] = useState(false);

  // Inject the Turnstile script once per page lifetime. Idempotent — checks
  // for an existing script tag before injecting.
  useEffect(() => {
    if (!SITE_KEY) {
      // No site key — emit dev sentinel so consumers see a non-empty token
      onTokenChange(DEV_SENTINEL);
      return;
    }

    if (window.turnstile) {
      setScriptLoaded(true);
      return;
    }

    const existing = document.querySelector<HTMLScriptElement>(
      `script[src="${SCRIPT_URL}"]`,
    );
    if (existing) {
      existing.addEventListener("load", () => setScriptLoaded(true), {
        once: true,
      });
      return;
    }

    const script = document.createElement("script");
    script.src = SCRIPT_URL;
    script.async = true;
    script.defer = true;
    script.onload = () => setScriptLoaded(true);
    document.head.appendChild(script);
  }, [onTokenChange]);

  // Render the widget once both the script is loaded and the container is
  // mounted. Track the widget id so we can remove on unmount.
  useEffect(() => {
    if (!SITE_KEY || !scriptLoaded || !containerRef.current) return;
    if (widgetIdRef.current) return; // already rendered

    const ts = window.turnstile;
    if (!ts) return;

    widgetIdRef.current = ts.render(containerRef.current, {
      sitekey: SITE_KEY,
      theme,
      callback: (token: string) => onTokenChange(token),
      "error-callback": () => onTokenChange(""),
      "expired-callback": () => onTokenChange(""),
    });

    return () => {
      const id = widgetIdRef.current;
      if (id && window.turnstile) {
        try {
          window.turnstile.remove(id);
        } catch {
          // Best-effort cleanup; widget may already be gone if the script
          // failed mid-render.
        }
      }
      widgetIdRef.current = null;
    };
  }, [scriptLoaded, theme, onTokenChange]);

  // No site key → render nothing (dev sentinel was already emitted in effect 1)
  if (!SITE_KEY) return null;

  return (
    <div
      ref={containerRef}
      className={className}
      aria-label="Security challenge"
    />
  );
}

export const TURNSTILE_DEV_SENTINEL = DEV_SENTINEL;
