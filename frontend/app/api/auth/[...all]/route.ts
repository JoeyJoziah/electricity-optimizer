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
    const response = await handlerFn(req)

    if (response.status >= 500) {
      let body: string | null = null
      try {
        body = await response.clone().text()
      } catch { /* empty */ }
      console.error(`[Auth ${method} ${response.status}]`, { body, url: req.url })
    }

    return response
  } catch (error) {
    console.error(`[Auth ${method} Exception]`, error)
    return NextResponse.json(
      { error: "Internal auth error" },
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
