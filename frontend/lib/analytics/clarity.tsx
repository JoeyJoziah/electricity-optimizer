"use client";

import Script from "next/script";
import { CLARITY_PROJECT_ID } from "@/lib/config/env";

/**
 * Sanitize Clarity project ID to prevent XSS.
 * Clarity project IDs are strictly alphanumeric (e.g. "abc123def").
 * Strip anything that is not a letter or digit.
 */
function sanitizeClarityId(id: string): string {
  return id.replace(/[^a-zA-Z0-9]/g, "");
}

export function ClarityScript({ nonce }: { nonce?: string }) {
  if (!CLARITY_PROJECT_ID) return null;

  const safeId = sanitizeClarityId(CLARITY_PROJECT_ID);
  if (!safeId) return null;

  return (
    <Script
      id="microsoft-clarity"
      strategy="afterInteractive"
      nonce={nonce}
      src={`https://www.clarity.ms/tag/${safeId}`}
    />
  );
}
