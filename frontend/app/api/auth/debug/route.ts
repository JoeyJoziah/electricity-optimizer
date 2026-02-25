/**
 * Debug endpoint to test Better Auth DB connectivity.
 * Remove after debugging.
 */

import { Pool } from "@neondatabase/serverless"
import { Kysely, PostgresDialect } from "kysely"
import { NextResponse } from "next/server"

// Force dynamic rendering — prevent Next.js from caching build-time response
export const dynamic = "force-dynamic"

export async function GET() {
  const baseUrl = process.env.DATABASE_URL || ""
  const connectionString = baseUrl.includes("options=")
    ? baseUrl
    : `${baseUrl}${baseUrl.includes("?") ? "&" : "?"}options=-csearch_path%3Dneon_auth,public`

  const diagnostics: Record<string, unknown> = {
    hasDbUrl: !!baseUrl,
    dbUrlLength: baseUrl.length,
    hasBetterAuthSecret: !!process.env.BETTER_AUTH_SECRET,
    hasBetterAuthUrl: !!process.env.BETTER_AUTH_URL,
    betterAuthUrl: process.env.BETTER_AUTH_URL,
    nodeEnv: process.env.NODE_ENV,
  }

  const pool = new Pool({ connectionString })

  try {
    const client = await pool.connect()
    try {
      // Test basic query
      const res = await client.query("SELECT current_schema(), current_setting('search_path') as search_path")
      diagnostics.schema = res.rows[0]?.current_schema
      diagnostics.searchPath = res.rows[0]?.search_path

      // Show actual column names in neon_auth.user
      const cols = await client.query(`
        SELECT column_name, data_type, is_nullable
        FROM information_schema.columns
        WHERE table_schema = 'neon_auth' AND table_name = 'user'
        ORDER BY ordinal_position
      `)
      diagnostics.userColumns = cols.rows

      // Show actual column names in neon_auth.account
      const acctCols = await client.query(`
        SELECT column_name, data_type, is_nullable
        FROM information_schema.columns
        WHERE table_schema = 'neon_auth' AND table_name = 'account'
        ORDER BY ordinal_position
      `)
      diagnostics.accountColumns = acctCols.rows

      // Show actual column names in neon_auth.session
      const sessCols = await client.query(`
        SELECT column_name, data_type, is_nullable
        FROM information_schema.columns
        WHERE table_schema = 'neon_auth' AND table_name = 'session'
        ORDER BY ordinal_position
      `)
      diagnostics.sessionColumns = sessCols.rows

      diagnostics.rawDbStatus = "ok"
    } finally {
      client.release()
    }

    // Test Kysely with same Pool (how Better Auth uses it)
    try {
      // eslint-disable-next-line @typescript-eslint/no-explicit-any
      const db = new Kysely<any>({ dialect: new PostgresDialect({ pool }) })
      // Try a simple SELECT through Kysely (matches Better Auth's access pattern)
      const result = await db.selectFrom("user").selectAll().limit(1).execute()
      diagnostics.kyselySelectStatus = "ok"
      diagnostics.kyselySelectResult = result
    } catch (error) {
      diagnostics.kyselySelectStatus = "error"
      diagnostics.kyselySelectError = String(error)
    }

    // Test Kysely INSERT (what signup does)
    try {
      // eslint-disable-next-line @typescript-eslint/no-explicit-any
      const db = new Kysely<any>({ dialect: new PostgresDialect({ pool }) })
      const testId = crypto.randomUUID()
      // Try insert then immediately delete — same pattern as Better Auth signup
      await db.insertInto("user")
        .values({
          id: testId,
          name: "test-debug-user",
          email: `debug-${testId}@test.local`,
          emailVerified: false,
          createdAt: new Date(),
          updatedAt: new Date(),
        })
        .execute()
      // Clean up
      await db.deleteFrom("user").where("id", "=", testId).execute()
      diagnostics.kyselyInsertStatus = "ok"
    } catch (error) {
      diagnostics.kyselyInsertStatus = "error"
      diagnostics.kyselyInsertError = String(error)
      diagnostics.kyselyInsertStack = (error as Error)?.stack?.split("\n").slice(0, 5)
    }

    diagnostics.status = "ok"
  } catch (error) {
    diagnostics.status = "error"
    diagnostics.error = String(error)
    diagnostics.errorStack = (error as Error)?.stack?.split("\n").slice(0, 5)
  } finally {
    await pool.end()
  }

  return NextResponse.json(diagnostics)
}
