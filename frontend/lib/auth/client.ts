/**
 * Better Auth Client
 *
 * Client-side auth methods that talk to the /api/auth/* endpoints.
 * Uses httpOnly session cookies — no localStorage token management.
 */

import { createAuthClient } from "better-auth/react"
import { APP_URL } from "@/lib/config/env"

export const authClient = createAuthClient({
  baseURL: typeof window !== "undefined"
    ? window.location.origin
    : APP_URL,
})
