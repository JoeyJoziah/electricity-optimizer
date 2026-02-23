'use client'

/**
 * OAuth Callback Page
 *
 * Better Auth handles callbacks via /api/auth/callback/*.
 * This page handles any leftover redirects by sending users to the dashboard.
 */

import { useEffect } from 'react'
import { useRouter } from 'next/navigation'

export const dynamic = 'force-dynamic'

export default function AuthCallbackPage() {
  const router = useRouter()

  useEffect(() => {
    // Better Auth handles OAuth callbacks server-side via /api/auth/callback/*
    // If a user lands here, redirect them to dashboard
    router.replace('/dashboard')
  }, [router])

  return (
    <div className="min-h-screen bg-gray-50 flex items-center justify-center">
      <div className="animate-spin h-8 w-8 border-4 border-blue-600 border-t-transparent rounded-full" />
    </div>
  )
}
