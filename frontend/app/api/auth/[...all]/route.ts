/**
 * Better Auth API Route Handler
 *
 * Handler is lazily created on first request to ensure runtime env vars
 * are available (Next.js standalone evaluates module-level code at build).
 */

import { getAuth } from "@/lib/auth/server"
import { toNextJsHandler } from "better-auth/next-js"
import { NextRequest, NextResponse } from "next/server"

// Force dynamic — prevent Next.js from evaluating at build time
export const dynamic = "force-dynamic"

// Lazy handler — created on first request
let _handler: ReturnType<typeof toNextJsHandler> | null = null
function getHandler() {
  if (!_handler) {
    _handler = toNextJsHandler(getAuth())
  }
  return _handler
}

async function wrapHandler(
  method: "GET" | "POST",
  req: NextRequest
): Promise<Response> {
  try {
    const handler = getHandler()
    const handlerFn = method === "GET" ? handler.GET : handler.POST

    // Log request details for debugging
    const url = new URL(req.url)
    console.log(`[Auth ${method}] ${url.pathname}`, {
      hasDb: !!process.env.DATABASE_URL,
      hasSecret: !!process.env.BETTER_AUTH_SECRET,
    })

    const response = await handlerFn(req)

    // Collect all response headers
    const headers: Record<string, string> = {}
    response.headers.forEach((v, k) => { headers[k] = v })

    if (response.status >= 400) {
      let body: string | null = null
      try {
        body = await response.clone().text()
      } catch { /* empty */ }
      console.error(`[Auth ${method} ${response.status}]`, {
        body,
        headers,
        url: req.url,
      })
      // For 4xx, return the original response with extra debug info
      if (response.status < 500) {
        return NextResponse.json(
          {
            error: "Better Auth client error",
            status: response.status,
            body,
            headers,
          },
          { status: response.status }
        )
      }
      return NextResponse.json(
        {
          error: "Better Auth internal error",
          status: response.status,
          body,
          headers,
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
  return wrapHandler("GET", req)
}

export async function POST(req: NextRequest) {
  return wrapHandler("POST", req)
}
