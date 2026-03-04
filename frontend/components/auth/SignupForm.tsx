'use client'

/**
 * Signup Form Component
 *
 * Provides email/password registration with password strength indicator.
 * Uses shared Input component for consistent styling and validation.
 */

import { useState, FormEvent, useMemo } from 'react'
import Link from 'next/link'
import { useAuth } from '@/lib/hooks/useAuth'
import { Input } from '@/components/ui/input'

interface SignupFormProps {
  onSuccess?: () => void
}

interface PasswordStrength {
  score: number
  label: string
  color: string
}

const isValidEmail = (email: string) => /^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(email)

const GOOGLE_ENABLED = process.env.NEXT_PUBLIC_OAUTH_GOOGLE_ENABLED === 'true'
const GITHUB_ENABLED = process.env.NEXT_PUBLIC_OAUTH_GITHUB_ENABLED === 'true'
const OAUTH_ENABLED = GOOGLE_ENABLED || GITHUB_ENABLED

function checkPasswordStrength(password: string): PasswordStrength {
  let score = 0

  if (password.length >= 12) score += 1
  if (password.length >= 16) score += 1
  if (/[A-Z]/.test(password)) score += 1
  if (/[a-z]/.test(password)) score += 1
  if (/[0-9]/.test(password)) score += 1
  if (/[^A-Za-z0-9]/.test(password)) score += 1

  if (score <= 2) return { score, label: 'Weak', color: 'bg-danger-500' }
  if (score <= 4) return { score, label: 'Medium', color: 'bg-warning-500' }
  if (score <= 5) return { score, label: 'Strong', color: 'bg-success-500' }
  return { score, label: 'Very Strong', color: 'bg-success-600' }
}

export function SignupForm({ onSuccess }: SignupFormProps) {
  const { signUp, signInWithGoogle, signInWithGitHub, isLoading, error, clearError } = useAuth()

  const [name, setName] = useState('')
  const [email, setEmail] = useState('')
  const [password, setPassword] = useState('')
  const [confirmPassword, setConfirmPassword] = useState('')
  const [acceptTerms, setAcceptTerms] = useState(false)
  const [localError, setLocalError] = useState<string | null>(null)
  const [emailError, setEmailError] = useState<string | null>(null)

  const passwordStrength = useMemo(() => checkPasswordStrength(password), [password])

  const passwordRequirements = useMemo(() => ({
    length: password.length >= 12,
    uppercase: /[A-Z]/.test(password),
    lowercase: /[a-z]/.test(password),
    number: /[0-9]/.test(password),
    special: /[^A-Za-z0-9]/.test(password),
  }), [password])

  const isPasswordValid = Object.values(passwordRequirements).every(Boolean)

  const confirmPasswordHasError = Boolean(confirmPassword && password !== confirmPassword)
  const confirmPasswordMatch = Boolean(confirmPassword && password === confirmPassword)

  const handleEmailChange = (value: string) => {
    setEmail(value)
    if (emailError) setEmailError(null)
  }

  const handleEmailBlur = () => {
    if (email && !isValidEmail(email)) {
      setEmailError('Please enter a valid email address')
    }
  }

  const handleSubmit = async (e: FormEvent) => {
    e.preventDefault()
    setLocalError(null)
    setEmailError(null)
    clearError()

    if (email && !isValidEmail(email)) {
      setEmailError('Please enter a valid email address')
      return
    }

    if (password !== confirmPassword) {
      setLocalError('Passwords do not match')
      return
    }

    if (!isPasswordValid) {
      setLocalError('Password does not meet requirements')
      return
    }

    if (!acceptTerms) {
      setLocalError('You must accept the terms and conditions')
      return
    }

    try {
      await signUp(email, password, name || undefined)
      onSuccess?.()
    } catch {
      // Error is already set in auth context
    }
  }

  const handleGoogleSignIn = async () => {
    setLocalError(null)
    clearError()
    try {
      await signInWithGoogle()
    } catch {
      // Error is already set in auth context
    }
  }

  const handleGitHubSignIn = async () => {
    setLocalError(null)
    clearError()
    try {
      await signInWithGitHub()
    } catch {
      // Error is already set in auth context
    }
  }

  return (
    <div className="w-full max-w-md mx-auto animate-fadeIn">
      <div className="bg-white rounded-xl shadow-card p-8">
        <h2 className="text-2xl font-bold text-gray-900 mb-6 text-center">Create your account</h2>

        {/* Error display */}
        {(error || localError) && (
          <div
            role="alert"
            aria-live="polite"
            className="mb-5 p-4 bg-danger-50 border border-danger-200 rounded-lg flex items-start gap-3 animate-slideDown"
          >
            <svg className="w-5 h-5 text-danger-500 shrink-0 mt-0.5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 8v4m0 4h.01M21 12a9 9 0 11-18 0 9 9 0 0118 0z" />
            </svg>
            <p className="text-sm text-danger-700">{error || localError}</p>
          </div>
        )}

        {/* OAuth buttons — only shown when env vars enable them */}
        {OAUTH_ENABLED && (
          <>
            <div className="space-y-3 mb-6">
              {GOOGLE_ENABLED && (
                <button
                  type="button"
                  onClick={handleGoogleSignIn}
                  disabled={isLoading}
                  className="w-full flex items-center justify-center gap-3 px-4 py-3 bg-white border border-gray-300 rounded-lg hover:bg-gray-50 hover:border-gray-400 active:bg-gray-100 transition-all duration-200 disabled:opacity-50 disabled:cursor-not-allowed"
                >
                  <svg className="w-5 h-5" viewBox="0 0 24 24">
                    <path fill="#4285F4" d="M22.56 12.25c0-.78-.07-1.53-.2-2.25H12v4.26h5.92c-.26 1.37-1.04 2.53-2.21 3.31v2.77h3.57c2.08-1.92 3.28-4.74 3.28-8.09z" />
                    <path fill="#34A853" d="M12 23c2.97 0 5.46-.98 7.28-2.66l-3.57-2.77c-.98.66-2.23 1.06-3.71 1.06-2.86 0-5.29-1.93-6.16-4.53H2.18v2.84C3.99 20.53 7.7 23 12 23z" />
                    <path fill="#FBBC05" d="M5.84 14.09c-.22-.66-.35-1.36-.35-2.09s.13-1.43.35-2.09V7.07H2.18C1.43 8.55 1 10.22 1 12s.43 3.45 1.18 4.93l2.85-2.22.81-.62z" />
                    <path fill="#EA4335" d="M12 5.38c1.62 0 3.06.56 4.21 1.64l3.15-3.15C17.45 2.09 14.97 1 12 1 7.7 1 3.99 3.47 2.18 7.07l3.66 2.84c.87-2.6 3.3-4.53 6.16-4.53z" />
                  </svg>
                  <span className="text-gray-700 font-medium">Continue with Google</span>
                </button>
              )}

              {GITHUB_ENABLED && (
                <button
                  type="button"
                  onClick={handleGitHubSignIn}
                  disabled={isLoading}
                  className="w-full flex items-center justify-center gap-3 px-4 py-3 bg-white border border-gray-300 rounded-lg hover:bg-gray-50 hover:border-gray-400 active:bg-gray-100 transition-all duration-200 disabled:opacity-50 disabled:cursor-not-allowed"
                >
                  <svg className="w-5 h-5 text-gray-900" fill="currentColor" viewBox="0 0 24 24">
                    <path d="M12 0c-6.626 0-12 5.373-12 12 0 5.302 3.438 9.8 8.207 11.387.599.111.793-.261.793-.577v-2.234c-3.338.726-4.033-1.416-4.033-1.416-.546-1.387-1.333-1.756-1.333-1.756-1.089-.745.083-.729.083-.729 1.205.084 1.839 1.237 1.839 1.237 1.07 1.834 2.807 1.304 3.492.997.107-.775.418-1.305.762-1.604-2.665-.305-5.467-1.334-5.467-5.931 0-1.311.469-2.381 1.236-3.221-.124-.303-.535-1.524.117-3.176 0 0 1.008-.322 3.301 1.23.957-.266 1.983-.399 3.003-.404 1.02.005 2.047.138 3.006.404 2.291-1.552 3.297-1.23 3.297-1.23.653 1.653.242 2.874.118 3.176.77.84 1.235 1.911 1.235 3.221 0 4.609-2.807 5.624-5.479 5.921.43.372.823 1.102.823 2.222v3.293c0 .319.192.694.801.576 4.765-1.589 8.199-6.086 8.199-11.386 0-6.627-5.373-12-12-12z" />
                  </svg>
                  <span className="text-gray-700 font-medium">Continue with GitHub</span>
                </button>
              )}
            </div>

            {/* Divider */}
            <div className="relative mb-6">
              <div className="absolute inset-0 flex items-center">
                <div className="w-full border-t border-gray-200" />
              </div>
              <div className="relative flex justify-center text-sm">
                <span className="px-3 bg-white text-gray-500">Or create with email</span>
              </div>
            </div>
          </>
        )}

        {/* Email/Password form */}
        <form onSubmit={handleSubmit} className="space-y-4">
          <Input
            id="name"
            label="Name"
            labelSuffix="(optional)"
            type="text"
            value={name}
            onChange={(e) => setName(e.target.value)}
            placeholder="Your name"
            autoComplete="name"
          />

          <Input
            id="email"
            label="Email address"
            type="email"
            value={email}
            onChange={(e) => handleEmailChange(e.target.value)}
            onBlur={handleEmailBlur}
            error={emailError || undefined}
            required
            placeholder="you@example.com"
            autoComplete="email"
          />

          <div>
            <Input
              id="password"
              label="Password"
              type="password"
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              required
              placeholder="Create a strong password"
              autoComplete="new-password"
            />

            {/* Password strength indicator */}
            {password && (
              <div className="mt-2.5">
                <div className="flex gap-1 mb-1.5">
                  {[1, 2, 3, 4, 5, 6].map((i) => (
                    <div
                      key={i}
                      className={`h-1.5 flex-1 rounded-full transition-colors duration-300 ${
                        i <= passwordStrength.score ? passwordStrength.color : 'bg-gray-200'
                      }`}
                    />
                  ))}
                </div>
                <p className="text-xs font-medium text-gray-600">{passwordStrength.label}</p>
              </div>
            )}

            {/* Password requirements */}
            {password && (
              <div className="mt-3 space-y-1.5">
                {[
                  { key: 'length', label: 'At least 12 characters' },
                  { key: 'uppercase', label: 'One uppercase letter' },
                  { key: 'lowercase', label: 'One lowercase letter' },
                  { key: 'number', label: 'One number' },
                  { key: 'special', label: 'One special character' },
                ].map(({ key, label }) => {
                  const met = passwordRequirements[key as keyof typeof passwordRequirements]
                  return (
                    <div key={key} className="flex items-center gap-2 text-xs">
                      {met ? (
                        <svg className="w-4 h-4 text-success-500" fill="currentColor" viewBox="0 0 20 20">
                          <path
                            fillRule="evenodd"
                            d="M10 18a8 8 0 100-16 8 8 0 000 16zm3.707-9.293a1 1 0 00-1.414-1.414L9 10.586 7.707 9.293a1 1 0 00-1.414 1.414l2 2a1 1 0 001.414 0l4-4z"
                            clipRule="evenodd"
                          />
                        </svg>
                      ) : (
                        <div className="w-4 h-4 rounded-full border-2 border-gray-300" />
                      )}
                      <span className={met ? 'text-success-700' : 'text-gray-500'}>
                        {label}
                      </span>
                    </div>
                  )
                })}
              </div>
            )}
          </div>

          <Input
            id="confirmPassword"
            label="Confirm password"
            type="password"
            value={confirmPassword}
            onChange={(e) => setConfirmPassword(e.target.value)}
            required
            error={confirmPasswordHasError ? 'Passwords do not match' : undefined}
            success={confirmPasswordMatch}
            successText={confirmPasswordMatch ? 'Passwords match' : undefined}
            placeholder="Confirm your password"
            autoComplete="new-password"
          />

          {/* Terms acceptance */}
          <div className="flex items-start gap-3">
            <input
              id="terms"
              type="checkbox"
              checked={acceptTerms}
              onChange={(e) => setAcceptTerms(e.target.checked)}
              className="mt-1 h-4 w-4 text-primary-600 border-gray-300 rounded focus:ring-primary-500 cursor-pointer"
            />
            <label htmlFor="terms" className="text-sm text-gray-600 cursor-pointer">
              I agree to the{' '}
              <Link href="/terms" className="text-primary-600 hover:text-primary-700 font-medium transition-colors">
                Terms of Service
              </Link>{' '}
              and{' '}
              <Link href="/privacy" className="text-primary-600 hover:text-primary-700 font-medium transition-colors">
                Privacy Policy
              </Link>
            </label>
          </div>

          <button
            type="submit"
            disabled={isLoading || !isPasswordValid || password !== confirmPassword || !acceptTerms}
            className="w-full bg-primary-600 text-white py-2.5 px-4 rounded-lg hover:bg-primary-700 active:bg-primary-800 transition-all duration-200 font-medium disabled:opacity-50 disabled:cursor-not-allowed flex items-center justify-center gap-2"
          >
            {isLoading && (
              <svg className="animate-spin h-4 w-4" xmlns="http://www.w3.org/2000/svg" fill="none" viewBox="0 0 24 24">
                <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" />
                <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4zm2 5.291A7.962 7.962 0 014 12H0c0 3.042 1.135 5.824 3 7.938l3-2.647z" />
              </svg>
            )}
            {isLoading ? 'Creating account...' : 'Create account'}
          </button>
        </form>

        {/* Sign in link */}
        <div className="mt-6 text-center text-sm text-gray-600">
          Already have an account?{' '}
          <Link href="/auth/login" className="text-primary-600 hover:text-primary-700 font-medium transition-colors duration-200">
            Sign in
          </Link>
        </div>
      </div>
    </div>
  )
}
