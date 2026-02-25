/**
 * Better Auth Server Configuration
 *
 * Initializes the auth server that handles sign-up, sign-in, sessions,
 * and OAuth flows. Uses the neon_auth schema provisioned by Neon Auth.
 *
 * IMPORTANT: The auth object is lazily initialized on first use to avoid
 * capturing empty env vars during the Next.js build (standalone output
 * evaluates module-level code at build time when env vars aren't present).
 */

import { betterAuth } from "better-auth"
import { Pool } from "@neondatabase/serverless"

function buildConnectionString(): string {
  const baseUrl = process.env.DATABASE_URL || ""
  if (!baseUrl) {
    console.error("[Auth] DATABASE_URL is empty at initialization time")
  }
  return baseUrl.includes("options=")
    ? baseUrl
    : `${baseUrl}${baseUrl.includes("?") ? "&" : "?"}options=-csearch_path%3Dneon_auth,public`
}

function createAuth() {
  const connectionString = buildConnectionString()
  console.log("[Auth] Initializing Better Auth", {
    dbUrlLen: (process.env.DATABASE_URL || "").length,
    hasSecret: !!process.env.BETTER_AUTH_SECRET,
    hasAuthUrl: !!process.env.BETTER_AUTH_URL,
  })

  return betterAuth({
    database: new Pool({ connectionString }),

    // Email + password authentication
    emailAndPassword: {
      enabled: true,
      minPasswordLength: 12,
      requireEmailVerification: false,
    },

    // Social providers — enabled when env vars are present
    socialProviders: {
      ...(process.env.GOOGLE_CLIENT_ID && process.env.GOOGLE_CLIENT_SECRET
        ? {
            google: {
              clientId: process.env.GOOGLE_CLIENT_ID,
              clientSecret: process.env.GOOGLE_CLIENT_SECRET,
            },
          }
        : {}),
      ...(process.env.GITHUB_CLIENT_ID && process.env.GITHUB_CLIENT_SECRET
        ? {
            github: {
              clientId: process.env.GITHUB_CLIENT_ID,
              clientSecret: process.env.GITHUB_CLIENT_SECRET,
            },
          }
        : {}),
    },

    // Session configuration
    session: {
      expiresIn: 60 * 60 * 24 * 7, // 7 days
      updateAge: 60 * 60 * 24, // Update session every 24 hours
      cookieCache: {
        enabled: true,
        maxAge: 5 * 60, // Cache for 5 minutes
      },
    },

    // Trusted origins for CORS
    trustedOrigins: [
      "http://localhost:3000",
      "http://localhost:3001",
      ...(process.env.NEXT_PUBLIC_APP_URL ? [process.env.NEXT_PUBLIC_APP_URL] : []),
    ],

    // Tell Better Auth the DB uses UUID columns (neon_auth schema)
    advanced: {
      database: {
        generateId: "uuid",
      },
    },

    // Re-throw API errors so our wrapper catches them with full detail
    // (Better Auth's default onError silently swallows DB schema errors)
    onAPIError: {
      throw: true,
    },

    // Enable verbose logging to diagnose internal errors
    logger: {
      level: "debug" as const,
    },
  })
}

// Lazy singleton — created on first access, when runtime env vars are available
let _auth: ReturnType<typeof createAuth> | null = null

export function getAuth() {
  if (!_auth) {
    _auth = createAuth()
  }
  return _auth
}

// Type helper — extract Session type from Better Auth
export type Session = ReturnType<typeof createAuth>["$Infer"]["Session"]
