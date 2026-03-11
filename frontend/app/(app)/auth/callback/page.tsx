'use client'

/**
 * OAuth Callback Page
 *
 * Better Auth handles callbacks via /api/auth/callback/*.
 * This page handles any leftover redirects by sending users to the dashboard.
 * Includes a timeout fallback in case router.replace fails silently.
 */

import { useEffect, useState } from 'react'
import { useRouter } from 'next/navigation'

export const dynamic = 'force-dynamic'

export default function AuthCallbackPage() {
  const router = useRouter()
  const [showFallback, setShowFallback] = useState(false)

  useEffect(() => {
    // Better Auth handles OAuth callbacks server-side via /api/auth/callback/*
    // If a user lands here, redirect them to dashboard
    try {
      router.replace('/dashboard')
    } catch {
      // If router.replace fails, show fallback link
      setShowFallback(true)
    }

    // If still on this page after 5 seconds, show a manual link
    const timer = setTimeout(() => setShowFallback(true), 5000)
    return () => clearTimeout(timer)
  }, [router])

  return (
    <div className="min-h-screen bg-gray-50 flex flex-col items-center justify-center gap-4">
      <div role="status" aria-label="Completing authentication">
        <div className="animate-spin h-8 w-8 border-4 border-blue-600 border-t-transparent rounded-full" />
        <span className="sr-only">Completing authentication</span>
      </div>
      {showFallback && (
        <div className="text-center">
          <p className="text-sm text-gray-500 mb-2">Taking longer than expected?</p>
          <a href="/dashboard" className="text-sm font-medium text-primary-600 hover:text-primary-700 underline">
            Go to Dashboard
          </a>
        </div>
      )}
    </div>
  )
}
