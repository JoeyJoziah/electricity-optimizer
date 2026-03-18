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

import { betterAuth } from "better-auth";
import { magicLink } from "better-auth/plugins/magic-link";
import { Pool } from "@neondatabase/serverless";
import { APP_URL } from "@/lib/config/env";
import { sendEmail } from "@/lib/email/send";

function buildConnectionString(): string {
  const baseUrl = process.env.DATABASE_URL || "";
  if (!baseUrl) {
    console.error("[Auth] DATABASE_URL is empty at initialization time");
  }
  return baseUrl.includes("options=")
    ? baseUrl
    : `${baseUrl}${baseUrl.includes("?") ? "&" : "?"}options=-csearch_path%3Dneon_auth,public`;
}

function createAuth() {
  const connectionString = buildConnectionString();

  return betterAuth({
    database: new Pool({ connectionString, max: 2 }),

    // Explicit secret for token signing (Better Auth reads BETTER_AUTH_SECRET by default)
    secret: process.env.BETTER_AUTH_SECRET,

    // Email + password authentication
    emailAndPassword: {
      enabled: true,
      minPasswordLength: 12,
      requireEmailVerification: true,
      sendResetPassword: async ({ user, url }) => {
        await sendEmail({
          to: user.email,
          subject: "Reset your password — RateShift",
          html: `<p>Hi${user.name ? ` ${user.name}` : ""},</p><p>Click the link below to reset your password:</p><p><a href="${url}">Reset password</a></p><p>If you didn&apos;t request this, you can safely ignore this email.</p>`,
        });
      },
    },

    // Email verification — sends on signup and re-sends on sign-in attempt
    emailVerification: {
      sendOnSignUp: true,
      sendOnSignIn: true,
      autoSignInAfterVerification: true,
      sendVerificationEmail: async ({ user, url }) => {
        console.log(
          `[Auth] sendVerificationEmail called for user=${user.email}`,
        );
        await sendEmail({
          to: user.email,
          subject: "Verify your email — RateShift",
          html: `<p>Hi${user.name ? ` ${user.name}` : ""},</p><p>Welcome to RateShift! Please verify your email by clicking the link below:</p><p><a href="${url}">Verify email</a></p><p>This link will expire in 24 hours.</p>`,
        });
      },
    },

    // Plugins
    plugins: [
      magicLink({
        sendMagicLink: async ({ email, url }) => {
          await sendEmail({
            to: email,
            subject: "Your sign-in link — RateShift",
            html: `<p>Click the link below to sign in to RateShift:</p><p><a href="${url}">Sign in</a></p><p>This link expires in 5 minutes. If you didn&apos;t request this, you can safely ignore this email.</p>`,
          });
        },
        expiresIn: 300, // 5 minutes
      }),
    ],

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

    // Trusted origins for CORS — localhost only in development
    trustedOrigins: [
      ...(process.env.NODE_ENV === "development"
        ? ["http://localhost:3000", "http://localhost:3001"]
        : []),
      ...(APP_URL && APP_URL !== "http://localhost:3000" ? [APP_URL] : []),
      "https://rateshift.app",
      "https://www.rateshift.app",
    ],

    // Tell Better Auth the DB uses UUID columns (neon_auth schema)
    advanced: {
      database: {
        generateId: "uuid",
      },
      // Explicit CSRF-safe cookie attributes.
      // SameSite=lax blocks cross-site POST/PUT/DELETE requests (CSRF) while
      // still allowing navigations from external links (e.g. magic-link emails).
      // secure=true is enforced in production so the cookie is only sent over
      // HTTPS. Both attributes are set explicitly rather than relying on
      // Better Auth's defaults so they survive future library upgrades.
      cookieOptions: {
        sameSite: "lax" as const,
        secure: process.env.NODE_ENV === "production",
        httpOnly: true,
        path: "/",
      },
    },

    // Re-throw API errors so our wrapper catches them with full detail
    // (Better Auth's default onError silently swallows DB schema errors)
    onAPIError: {
      throw: true,
    },

    // Log warnings and errors (debug logging removed after auth fix)
    logger: {
      level: "warn" as const,
    },
  });
}

// Lazy singleton — created on first access, when runtime env vars are available
let _auth: ReturnType<typeof createAuth> | null = null;

export function getAuth() {
  if (!_auth) {
    _auth = createAuth();
  }
  return _auth;
}

// Type helper — extract Session type from Better Auth
export type Session = ReturnType<typeof createAuth>["$Infer"]["Session"];
