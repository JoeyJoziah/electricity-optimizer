/**
 * Better Auth Server Configuration
 *
 * Initializes the auth server that handles sign-up, sign-in, sessions,
 * and OAuth flows. Uses the neon_auth schema provisioned by Neon Auth.
 */

import { betterAuth } from "better-auth"
import { Pool } from "@neondatabase/serverless"
import { randomUUID } from "crypto"

// Connection to Neon PostgreSQL, using the neon_auth schema
// Set search_path so better-auth finds its tables in the neon_auth schema
const baseUrl = process.env.DATABASE_URL || ""
const connectionString = baseUrl.includes("options=")
  ? baseUrl
  : `${baseUrl}${baseUrl.includes("?") ? "&" : "?"}options=-csearch_path%3Dneon_auth,public`

export const auth = betterAuth({
  database: new Pool({
    connectionString,
  }),

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

  // Generate UUID IDs to match neon_auth schema (uuid columns, not text)
  advanced: {
    // @ts-expect-error - generateId exists at runtime but missing from types in v1.4.x
    generateId: () => randomUUID(),
  },
})

export type Session = typeof auth.$Infer.Session
