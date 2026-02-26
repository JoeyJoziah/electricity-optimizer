'use client'

/**
 * Forgot Password Page
 *
 * Accepts an email address and triggers a password reset email via Better Auth.
 * Intentionally does not reveal whether the email exists (security best practice).
 */

import React, { useState } from 'react'
import Link from 'next/link'
import { Button } from '@/components/ui/button'
import { Card, CardHeader, CardTitle, CardContent } from '@/components/ui/card'
import { authClient } from '@/lib/auth/client'

export const dynamic = 'force-dynamic'

export default function ForgotPasswordPage() {
  const [email, setEmail] = useState('')
  const [submitted, setSubmitted] = useState(false)
  const [error, setError] = useState('')
  const [loading, setLoading] = useState(false)

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault()
    setError('')
    setLoading(true)
    try {
      // Better Auth client method: requestPasswordReset
      // Maps to POST /api/auth/request-password-reset
      await authClient.requestPasswordReset({
        email,
        redirectTo: '/auth/reset-password',
      })
      setSubmitted(true)
    } catch (err: unknown) {
      const message =
        err instanceof Error ? err.message : 'Failed to send reset email. Please try again.'
      setError(message)
    } finally {
      setLoading(false)
    }
  }

  if (submitted) {
    return (
      <div className="flex min-h-screen items-center justify-center bg-gray-50 p-4">
        <Card className="w-full max-w-md">
          <CardContent className="p-6 text-center">
            <div className="mx-auto mb-4 flex h-12 w-12 items-center justify-center rounded-full bg-green-100">
              <svg
                className="h-6 w-6 text-green-600"
                fill="none"
                stroke="currentColor"
                viewBox="0 0 24 24"
              >
                <path
                  strokeLinecap="round"
                  strokeLinejoin="round"
                  strokeWidth={2}
                  d="M3 8l7.89 5.26a2 2 0 002.22 0L21 8M5 19h14a2 2 0 002-2V7a2 2 0 00-2-2H5a2 2 0 00-2 2v10a2 2 0 002 2z"
                />
              </svg>
            </div>
            <h2 className="text-lg font-semibold text-gray-900">Check your email</h2>
            <p className="mt-2 text-sm text-gray-600">
              If an account exists for <strong>{email}</strong>, we&apos;ve sent password reset
              instructions.
            </p>
            <Link
              href="/auth/login"
              className="mt-4 inline-block text-sm text-blue-600 hover:text-blue-800 font-medium"
            >
              Back to sign in
            </Link>
          </CardContent>
        </Card>
      </div>
    )
  }

  return (
    <div className="flex min-h-screen items-center justify-center bg-gray-50 p-4">
      <Card className="w-full max-w-md" padding="none">
        <div className="p-8">
          <CardHeader>
            <CardTitle as="h2">Reset your password</CardTitle>
          </CardHeader>
          <p className="mb-6 text-sm text-gray-600">
            Enter the email address associated with your account and we&apos;ll send you a link to
            reset your password.
          </p>
          <CardContent>
            <form onSubmit={handleSubmit} className="space-y-4">
              <div>
                <label htmlFor="email" className="block text-sm font-medium text-gray-700 mb-1">
                  Email address
                </label>
                <input
                  id="email"
                  type="email"
                  required
                  value={email}
                  onChange={(e) => setEmail(e.target.value)}
                  className="w-full px-4 py-3 border border-gray-300 rounded-md focus:ring-2 focus:ring-blue-500 focus:border-transparent"
                  placeholder="you@example.com"
                  autoComplete="email"
                  autoFocus
                />
              </div>
              {error && (
                <div className="p-3 bg-red-50 border border-red-200 rounded-md">
                  <p className="text-sm text-red-600">{error}</p>
                </div>
              )}
              <Button type="submit" className="w-full" disabled={loading} loading={loading}>
                {loading ? 'Sending...' : 'Send reset link'}
              </Button>
              <p className="text-center text-sm text-gray-500">
                <Link
                  href="/auth/login"
                  className="text-blue-600 hover:text-blue-800 font-medium"
                >
                  Back to sign in
                </Link>
              </p>
            </form>
          </CardContent>
        </div>
      </Card>
    </div>
  )
}
