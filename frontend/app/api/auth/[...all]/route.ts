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
import { NextRequest, NextResponse } from "next/server"

// Force dynamic — prevent Next.js from evaluating at build time
export const dynamic = "force-dynamic"

const handler = toNextJsHandler(auth)

export async function GET(req: NextRequest) {
  try {
    return await handler.GET(req)
  } catch (error) {
    console.error("[Auth GET Error]", error)
    return NextResponse.json(
      { error: "Internal auth error", message: String(error) },
      { status: 500 }
    )
  }
}

export async function POST(req: NextRequest) {
  try {
    return await handler.POST(req)
  } catch (error) {
    console.error("[Auth POST Error]", error)
    return NextResponse.json(
      { error: "Internal auth error", message: String(error) },
      { status: 500 }
    )
  }
}
