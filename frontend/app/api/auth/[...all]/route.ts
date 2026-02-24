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

async function wrapHandler(
  method: "GET" | "POST",
  handlerFn: (req: NextRequest) => Promise<Response>,
  req: NextRequest
): Promise<Response> {
  try {
    const response = await handlerFn(req)
    // On 500 errors, intercept and add debug info
    if (response.status >= 500) {
      const body = await response.text()
      console.error(`[Auth ${method} ${response.status}]`, body || "(empty body)")
      // During debugging: return error details in response
      return NextResponse.json(
        {
          error: "Better Auth internal error",
          status: response.status,
          body: body || null,
          headers: Object.fromEntries(response.headers.entries()),
        },
        { status: response.status }
      )
    }
    return response
  } catch (error) {
    console.error(`[Auth ${method} Exception]`, error)
    return NextResponse.json(
      {
        error: "Auth handler exception",
        message: String(error),
        stack: (error as Error)?.stack?.split("\n").slice(0, 5),
      },
      { status: 500 }
    )
  }
}

export async function GET(req: NextRequest) {
  return wrapHandler("GET", handler.GET, req)
}

export async function POST(req: NextRequest) {
  return wrapHandler("POST", handler.POST, req)
}
