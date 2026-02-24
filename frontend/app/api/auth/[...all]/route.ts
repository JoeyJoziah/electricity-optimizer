/**
 * Better Auth API Route Handler
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
    if (response.status >= 500) {
      let body: string | null = null
      try {
        body = await response.text()
      } catch { /* empty */ }
      console.error(`[Auth ${method} ${response.status}]`, {
        body,
        url: req.url,
        hasDb: !!process.env.DATABASE_URL,
        hasSecret: !!process.env.BETTER_AUTH_SECRET,
      })
      return NextResponse.json(
        {
          error: "Better Auth internal error",
          status: response.status,
          body,
          dbUrlLen: (process.env.DATABASE_URL || "").length,
          hasSecret: !!process.env.BETTER_AUTH_SECRET,
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
        stack: (error as Error)?.stack?.split("\n").slice(0, 8),
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
