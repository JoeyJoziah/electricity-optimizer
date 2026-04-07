"use client";

import Script from "next/script";
import { GA_MEASUREMENT_ID } from "@/lib/config/env";

/**
 * Sanitize a GA4 Measurement ID to prevent XSS.
 *
 * GA4 Measurement IDs follow the format "G-XXXXXXXXXX" — letters, digits,
 * and a single hyphen separator. Strip everything else before embedding the
 * ID in a script src URL or inline JS string.
 *
 * Returns an empty string if the result contains no alphanumeric characters
 * (e.g. an input of "---" or "!!!" is treated as invalid and rejected).
 */
function sanitizeGAId(id: string): string {
  const sanitized = id.replace(/[^a-zA-Z0-9-]/g, "");
  // Require at least one letter or digit — hyphens alone are not a valid ID
  return /[a-zA-Z0-9]/.test(sanitized) ? sanitized : "";
}

/**
 * GA4Analytics — lazy-loads the Google Analytics 4 gtag.js snippet.
 *
 * Uses `strategy="lazyOnload"` so it never blocks LCP or TTI.
 * Renders nothing (no-op) when NEXT_PUBLIC_GA_MEASUREMENT_ID is unset,
 * making local development and test environments GA-free by default.
 *
 * @see https://developers.google.com/tag-platform/gtagjs/install
 */
export function GA4Analytics({ nonce }: { nonce?: string }) {
  if (!GA_MEASUREMENT_ID) return null;

  const safeId = sanitizeGAId(GA_MEASUREMENT_ID);
  if (!safeId) return null;

  return (
    <>
      {/* Load the gtag.js library */}
      <Script
        id="ga4-loader"
        strategy="lazyOnload"
        nonce={nonce}
        src={`https://www.googletagmanager.com/gtag/js?id=${safeId}`}
      />

      {/* Initialise dataLayer and configure the measurement ID */}
      <Script
        id="ga4-config"
        strategy="lazyOnload"
        nonce={nonce}
        dangerouslySetInnerHTML={{
          __html: `
window.dataLayer = window.dataLayer || [];
function gtag(){dataLayer.push(arguments);}
gtag('js', new Date());
gtag('config', '${safeId}');
`.trim(),
        }}
      />
    </>
  );
}
