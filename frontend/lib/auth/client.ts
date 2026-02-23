/**
 * Better Auth Client
 *
 * Client-side auth methods that talk to the /api/auth/* endpoints.
 * Uses httpOnly session cookies — no localStorage token management.
 */

import { createAuthClient } from "better-auth/react"

export const authClient = createAuthClient({
  baseURL: typeof window !== "undefined"
    ? window.location.origin
    : process.env.NEXT_PUBLIC_APP_URL || "http://localhost:3000",
})
