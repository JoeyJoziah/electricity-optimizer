/**
 * Better Auth API Route Handler
 *
 * Handles all auth endpoints:
 * - /api/auth/sign-in/email
 * - /api/auth/sign-up/email
 * - /api/auth/sign-out
 * - /api/auth/get-session
 * - /api/auth/sign-in/social
 * - /api/auth/forget-password
 * - /api/auth/reset-password
 * - /api/auth/callback/*
 */

import { auth } from "@/lib/auth/server"
import { toNextJsHandler } from "better-auth/next-js"

export const { GET, POST } = toNextJsHandler(auth)
