/**
 * Debug endpoint to test Better Auth DB connectivity.
 * Remove after debugging.
 */

import { Pool } from "@neondatabase/serverless"
import { NextResponse } from "next/server"

export async function GET() {
  const baseUrl = process.env.DATABASE_URL || ""
  const connectionString = baseUrl.includes("options=")
    ? baseUrl
    : `${baseUrl}${baseUrl.includes("?") ? "&" : "?"}options=-csearch_path%3Dneon_auth,public`

  // Dump all available env var keys (not values) to diagnose injection
  const allEnvKeys = Object.keys(process.env).sort()

  const diagnostics: Record<string, unknown> = {
    hasDbUrl: !!baseUrl,
    dbUrlLength: baseUrl.length,
    hasBetterAuthSecret: !!process.env.BETTER_AUTH_SECRET,
    hasBetterAuthUrl: !!process.env.BETTER_AUTH_URL,
    betterAuthUrl: process.env.BETTER_AUTH_URL,
    connectionStringLength: connectionString.length,
    allEnvKeyCount: allEnvKeys.length,
    allEnvKeys,
    nodeEnv: process.env.NODE_ENV,
    port: process.env.PORT,
    hostname: process.env.HOSTNAME,
  }

  try {
    const pool = new Pool({ connectionString })
    const client = await pool.connect()
    try {
      // Test basic query
      const res = await client.query("SELECT current_schema(), current_setting('search_path') as search_path")
      diagnostics.schema = res.rows[0]?.current_schema
      diagnostics.searchPath = res.rows[0]?.search_path

      // Test neon_auth.user table
      const userCount = await client.query('SELECT count(*) FROM neon_auth."user"')
      diagnostics.userCount = userCount.rows[0]?.count

      // Test table existence in search_path
      const tables = await client.query(`
        SELECT table_schema, table_name
        FROM information_schema.tables
        WHERE table_name IN ('user', 'session', 'account', 'verification')
        AND table_schema IN ('neon_auth', 'public')
        ORDER BY table_schema, table_name
      `)
      diagnostics.tables = tables.rows

      diagnostics.status = "ok"
    } finally {
      client.release()
      await pool.end()
    }
  } catch (error) {
    diagnostics.status = "error"
    diagnostics.error = String(error)
    diagnostics.errorName = (error as Error)?.name
    diagnostics.errorStack = (error as Error)?.stack?.split("\n").slice(0, 5)
  }

  return NextResponse.json(diagnostics)
}
