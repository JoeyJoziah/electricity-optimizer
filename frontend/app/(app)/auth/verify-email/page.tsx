'use client'

/**
 * Email Verification Page
 *
 * Two modes:
 * 1. With a `token` query param: verifies the email via Better Auth, shows result.
 * 2. Without a token: shows a "check your email" prompt with a resend button.
 *
 * The `email` query param (optional) is used to pre-fill the resend form.
 */

import React, { useState, useEffect, useRef, Suspense } from 'react'
import { useSearchParams } from 'next/navigation'
import Link from 'next/link'
import { Button } from '@/components/ui/button'
import { Card, CardContent } from '@/components/ui/card'
import { authClient } from '@/lib/auth/client'

export const dynamic = 'force-dynamic'

function VerifyEmailContent() {
  const searchParams = useSearchParams()
  const token = searchParams.get('token')
  const emailParam = searchParams.get('email') || ''

  const [verifying, setVerifying] = useState(!!token)
  const [verified, setVerified] = useState(false)
  const [verifyError, setVerifyError] = useState('')
  const [resending, setResending] = useState(false)
  const [resent, setResent] = useState(false)
  const [resendEmail, setResendEmail] = useState(emailParam)

  // Verify the token automatically on mount (only once)
  const verifiedRef = useRef(false)
  useEffect(() => {
    if (!token || verifiedRef.current) return
    verifiedRef.current = true

    const verify = async () => {
      try {
        // Better Auth verifyEmail is a GET with query params
        // Maps to GET /api/auth/verify-email?token=...
        await authClient.verifyEmail({ query: { token } })
        setVerified(true)
      } catch (err: unknown) {
        const message =
          err instanceof Error
            ? err.message
            : 'Verification failed. The link may have expired.'
        setVerifyError(message)
      } finally {
        setVerifying(false)
      }
    }

    verify()
  }, [token])

  const handleResend = async () => {
    if (!resendEmail) return
    setResending(true)
    try {
      // Maps to POST /api/auth/send-verification-email
      await authClient.sendVerificationEmail({ email: resendEmail })
      setResent(true)
    } catch {
      // Silent fail -- don't reveal whether the email exists
    } finally {
      setResending(false)
    }
  }

  // Token present: show verification state
  if (token) {
    if (verifying) {
      return (
        <div className="flex min-h-screen items-center justify-center bg-gray-50 p-4">
          <Card className="w-full max-w-md">
            <CardContent className="p-6 text-center">
              <div className="mx-auto mb-4 h-8 w-8 animate-spin rounded-full border-4 border-gray-200 border-t-blue-600" />
              <h2 className="text-lg font-semibold text-gray-900">Verifying your email...</h2>
              <p className="mt-2 text-sm text-gray-600">Please wait a moment.</p>
            </CardContent>
          </Card>
        </div>
      )
    }

    if (verified) {
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
                    d="M5 13l4 4L19 7"
                  />
                </svg>
              </div>
              <h2 className="text-lg font-semibold text-gray-900">Email verified</h2>
              <p className="mt-2 text-sm text-gray-600">
                Your email has been verified successfully. You can now sign in.
              </p>
              <Link
                href="/auth/login"
                className="mt-4 inline-block text-sm text-blue-600 hover:text-blue-800 font-medium"
              >
                Go to sign in
              </Link>
            </CardContent>
          </Card>
        </div>
      )
    }

    // Verification failed
    return (
      <div className="flex min-h-screen items-center justify-center bg-gray-50 p-4">
        <Card className="w-full max-w-md">
          <CardContent className="p-6 text-center">
            <div className="mx-auto mb-4 flex h-12 w-12 items-center justify-center rounded-full bg-red-100">
              <svg
                className="h-6 w-6 text-red-600"
                fill="none"
                stroke="currentColor"
                viewBox="0 0 24 24"
              >
                <path
                  strokeLinecap="round"
                  strokeLinejoin="round"
                  strokeWidth={2}
                  d="M6 18L18 6M6 6l12 12"
                />
              </svg>
            </div>
            <h2 className="text-lg font-semibold text-gray-900">Verification failed</h2>
            <p className="mt-2 text-sm text-gray-600">{verifyError}</p>
            <div className="mt-4 space-y-2">
              <Link
                href="/auth/verify-email"
                className="block text-sm text-blue-600 hover:text-blue-800 font-medium"
              >
                Request a new verification email
              </Link>
              <Link
                href="/auth/login"
                className="block text-sm text-gray-500 hover:underline"
              >
                Back to sign in
              </Link>
            </div>
          </CardContent>
        </Card>
      </div>
    )
  }

  // No token: show "check your email" screen with resend option
  return (
    <div className="flex min-h-screen items-center justify-center bg-gray-50 p-4">
      <Card className="w-full max-w-md" padding="none">
        <div className="p-8">
          <CardContent className="text-center">
            <div className="mx-auto mb-4 flex h-12 w-12 items-center justify-center rounded-full bg-blue-100">
              <svg
                className="h-6 w-6 text-blue-600"
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
              We&apos;ve sent a verification link to{' '}
              <strong>{emailParam || 'your email'}</strong>. Click the link to verify your
              account.
            </p>

            <div className="mt-6 space-y-3">
              {/* Resend section */}
              {!resent ? (
                <>
                  {!emailParam && (
                    <div className="mb-2">
                      <label htmlFor="resend-email" className="sr-only">
                        Email address
                      </label>
                      <input
                        id="resend-email"
                        type="email"
                        value={resendEmail}
                        onChange={(e) => setResendEmail(e.target.value)}
                        className="w-full px-4 py-3 border border-gray-300 rounded-md focus:ring-2 focus:ring-blue-500 focus:border-transparent text-sm"
                        placeholder="Enter your email to resend"
                      />
                    </div>
                  )}
                  <Button
                    onClick={handleResend}
                    variant="outline"
                    disabled={resending || !resendEmail}
                    loading={resending}
                    className="w-full"
                  >
                    {resending ? 'Sending...' : 'Resend verification email'}
                  </Button>
                </>
              ) : (
                <div className="p-3 bg-green-50 border border-green-200 rounded-md">
                  <p className="text-sm text-green-700">
                    Verification email sent! Check your inbox.
                  </p>
                </div>
              )}

              <Link
                href="/auth/login"
                className="block text-sm text-gray-500 hover:underline"
              >
                Back to sign in
              </Link>
            </div>
          </CardContent>
        </div>
      </Card>
    </div>
  )
}

export default function VerifyEmailPage() {
  return (
    <Suspense
      fallback={
        <div className="flex min-h-screen items-center justify-center bg-gray-50 p-4">
          <Card className="w-full max-w-md">
            <CardContent className="p-6 text-center">
              <p className="text-sm text-gray-500">Loading...</p>
            </CardContent>
          </Card>
        </div>
      }
    >
      <VerifyEmailContent />
    </Suspense>
  )
}
