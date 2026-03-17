'use client'

/**
 * Authentication Hook
 *
 * Provides authentication state and methods using Better Auth client.
 * Session management uses httpOnly cookies (no localStorage tokens).
 */

import { useState, useEffect, useCallback, useMemo, useRef, createContext, useContext, ReactNode } from 'react'
import { useRouter } from 'next/navigation'
import { authClient } from '@/lib/auth/client'
import { getUserSupplier } from '@/lib/api/suppliers'
import { getUserProfile, updateUserProfile } from '@/lib/api/profile'
import { useSettingsStore } from '@/lib/store/settings'
import { API_URL } from '@/lib/config/env'
import { isSafeRedirect } from '@/lib/utils/url'
import { loginOneSignal, logoutOneSignal } from '@/lib/notifications/onesignal'

// Auth user type
export interface AuthUser {
  id: string
  email: string
  name?: string
  emailVerified: boolean
  createdAt: string
}

// Auth context type
interface AuthContextType {
  user: AuthUser | null
  isLoading: boolean
  isAuthenticated: boolean
  error: string | null
  signIn: (email: string, password: string) => Promise<void>
  signUp: (email: string, password: string, name?: string) => Promise<void>
  signOut: () => Promise<void>
  signInWithGoogle: () => Promise<void>
  signInWithGitHub: () => Promise<void>
  sendMagicLink: (email: string) => Promise<void>
  clearError: () => void
}

// Create context
const AuthContext = createContext<AuthContextType | undefined>(undefined)

// Auth provider props
interface AuthProviderProps {
  children: ReactNode
}

// ---------------------------------------------------------------------------
// Profile redirect helpers
//
// Extracted as pure functions so the two concerns — onboarding completion
// and region selection — are independently testable and clearly separated
// from the auth init flow.
// ---------------------------------------------------------------------------

/** App routes that require a fully-completed profile */
const PROFILE_REQUIRED_PREFIXES = [
  '/dashboard',
  '/prices',
  '/suppliers',
  '/optimize',
  '/connections',
  '/settings',
  '/alerts',
  '/assistant',
  '/community',
  '/water',
  '/propane',
  '/heating-oil',
  '/natural-gas',
  '/solar',
  '/forecast',
]

/**
 * Determine whether the current path requires a completed user profile.
 */
function isProfileRequiredPath(pathname: string): boolean {
  return PROFILE_REQUIRED_PREFIXES.some(
    (prefix) => pathname === prefix || pathname.startsWith(prefix + '/')
  )
}

/**
 * Check whether the user still needs to complete onboarding.
 * Returns true when `onboarding_completed` is falsy.
 */
export function checkNeedsOnboarding(profile: { onboarding_completed?: boolean }): boolean {
  return !profile.onboarding_completed
}

/**
 * Check whether the user is missing a region selection.
 *
 * This is a separate concern from onboarding — a user may have completed
 * the wizard in a previous version that did not require region, or the
 * region could have been cleared by a profile reset.
 */
export function checkNeedsRegion(profile: { region?: string | null }): boolean {
  return !profile.region
}

/**
 * Authentication Provider
 *
 * Wraps the application and provides auth state and methods via Better Auth.
 */
export function AuthProvider({ children }: AuthProviderProps) {
  const [user, setUser] = useState<AuthUser | null>(null)
  const [isLoading, setIsLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const router = useRouter()

  // Keep a ref to the latest router so the mount-only initAuth effect always
  // uses the current router instance rather than a stale closure capture.
  // Next.js may return a new router object on navigation; without the ref
  // the effect would call replace() on the original (stale) instance.
  const routerRef = useRef(router)
  useEffect(() => {
    routerRef.current = router
  }, [router])

  // Initialize auth state from session cookie
  // Fetch session, supplier, and profile data in parallel to avoid waterfall
  // On auth pages, skip profile/supplier calls to prevent 401 redirect loops
  useEffect(() => {
    const initAuth = async () => {
      try {
        const pathname = typeof window !== 'undefined' ? window.location.pathname : '/'
        const isAuthPage = pathname.startsWith('/auth/')
        const isPublicPage = isAuthPage || pathname === '/' || pathname === '/pricing' || pathname === '/privacy' || pathname === '/terms'

        const [sessionResult, supplierResult, profileResult] = await Promise.allSettled([
          authClient.getSession(),
          isPublicPage ? Promise.resolve({ supplier: null }) : getUserSupplier(),
          isPublicPage ? Promise.resolve({ region: null, onboarding_completed: false }) : getUserProfile(),
        ])

        if (sessionResult.status === 'fulfilled' && sessionResult.value.data?.user) {
          const session = sessionResult.value.data
          setUser({
            id: session.user.id,
            email: session.user.email,
            name: session.user.name || undefined,
            emailVerified: session.user.emailVerified,
            createdAt: session.user.createdAt?.toString() || '',
          })

          // Bind OneSignal push subscription to this user
          loginOneSignal(session.user.id)

          // Ensure the public.users profile exists for this authenticated user.
          // GET /auth/me calls ensure_user_profile on the backend, which upserts
          // the row if it is missing. This covers OAuth and magic-link sign-in
          // where signIn() is never called client-side (the redirect bypasses it).
          // Fire-and-forget: auth init must not block on this.
          fetch(`${API_URL}/auth/me`, { credentials: 'include' }).catch(() => {/* non-fatal */})

          // Sync supplier if fetched successfully
          if (supplierResult.status === 'fulfilled' && supplierResult.value.supplier) {
            const supplier = supplierResult.value.supplier
            const setCurrentSupplier = useSettingsStore.getState().setCurrentSupplier
            setCurrentSupplier({
              id: supplier.supplier_id,
              name: supplier.supplier_name,
              avgPricePerKwh: 0,
              standingCharge: 0,
              greenEnergy: supplier.green_energy,
              rating: supplier.rating ?? 0,
              estimatedAnnualCost: 0,
              tariffType: 'variable',
            })
          }

          // Sync region from profile if available.
          // useProfile hook is the primary sync source; this is a fallback for
          // pages that don't call useProfile (e.g. first load before dashboard).
          if (profileResult.status === 'fulfilled' && profileResult.value.region) {
            const store = useSettingsStore.getState()
            if (!store.region) {
              store.setRegion(profileResult.value.region)
            }
          }

          // ------------------------------------------------------------------
          // Profile completeness redirects
          //
          // Two independent checks, evaluated in order:
          //   1. Onboarding incomplete  -- user never finished the wizard
          //   2. Region missing         -- region cleared or legacy account
          //
          // Both redirect to /onboarding where the wizard shows the right
          // step. Only fires on app pages that require a completed profile.
          // ------------------------------------------------------------------
          if (profileResult.status === 'fulfilled') {
            const profile = profileResult.value
            const path = window.location.pathname

            if (isProfileRequiredPath(path)) {
              // Only redirect when the user genuinely has no region set.
              // Previously we also redirected on !onboarding_completed, which
              // caused a redirect loop for users who already had a region but
              // whose onboarding_completed flag was false.
              if (checkNeedsRegion(profile)) {
                routerRef.current.replace('/onboarding')
                return
              }

              // If region exists but onboarding_completed is false, auto-fix
              // the flag in the background (fire-and-forget).
              if (checkNeedsOnboarding(profile)) {
                updateUserProfile({ onboarding_completed: true }).catch(() => {})
              }
            }
          }
        }
      } catch {
        // No valid session — user is not authenticated
      } finally {
        setIsLoading(false)
      }
    }

    initAuth()
  }, [])

  // Sign in with email/password
  const signIn = useCallback(async (email: string, password: string) => {
    setIsLoading(true)
    setError(null)

    try {
      const { data, error: authError } = await authClient.signIn.email({
        email,
        password,
      })

      if (authError) {
        throw new Error(authError.message || 'Failed to sign in')
      }

      if (data?.user) {
        setUser({
          id: data.user.id,
          email: data.user.email,
          name: data.user.name || undefined,
          emailVerified: data.user.emailVerified,
          createdAt: data.user.createdAt?.toString() || '',
        })

        // Bind OneSignal push subscription to this user
        loginOneSignal(data.user.id)

        // Eagerly sync the public.users profile record.
        // The backend's GET /auth/me calls ensure_user_profile, which creates
        // the record if it doesn't exist yet (ON CONFLICT DO NOTHING).
        // This is a best-effort fire-and-forget call — sign-in succeeds
        // regardless of whether the sync request completes.
        fetch(`${API_URL}/auth/me`, { credentials: 'include' }).catch(() => {/* non-fatal */})
      }

      // Honor callbackUrl if the middleware set one, otherwise go to dashboard.
      // Validate via shared isSafeRedirect (blocks //evil.com, /\evil.com, javascript:, etc).
      const params = new URLSearchParams(window.location.search)
      const callback = params.get('callbackUrl') || '/dashboard'
      const destination = isSafeRedirect(callback) ? callback : '/dashboard'

      // Full-page navigation ensures middleware evaluates with the fresh
      // session cookie (router.push uses cached prefetch that may predate
      // the cookie being set).
      window.location.href = destination
    } catch (err) {
      const message = err instanceof Error ? err.message : 'Failed to sign in'
      setError(message)
      throw err
    } finally {
      setIsLoading(false)
    }
  }, [])

  // Sign up with email/password
  const signUp = useCallback(async (email: string, password: string, name?: string) => {
    setIsLoading(true)
    setError(null)

    try {
      const { error: authError } = await authClient.signUp.email({
        email,
        password,
        name: name || '',
      })

      if (authError) {
        throw new Error(authError.message || 'Failed to sign up')
      }

      // With requireEmailVerification, no session is created yet.
      // Redirect to verify-email page instead of onboarding.
      window.location.href = `/auth/verify-email?email=${encodeURIComponent(email)}`
    } catch (err) {
      const message = err instanceof Error ? err.message : 'Failed to sign up'
      setError(message)
      throw err
    } finally {
      setIsLoading(false)
    }
  }, [])

  // Sign out
  const signOut = useCallback(async () => {
    setIsLoading(true)

    // Unbind OneSignal push subscription from this user
    logoutOneSignal()

    // Invalidate backend Redis session cache first (best-effort).
    // Without this, the cached session remains valid for up to 30s
    // after Better Auth deletes it from the neon_auth.session table.
    try {
      await fetch(`${API_URL}/auth/logout`, {
        method: 'POST',
        credentials: 'include',
      })
    } catch {
      // Best-effort — frontend logout proceeds regardless
    }

    try {
      await authClient.signOut()
    } catch {
      // Swallow signOut errors — always clear local state
    } finally {
      // Clear persisted Zustand settings (region, supplier, appliances, etc.)
      // so the next user who signs in starts with a clean slate.
      useSettingsStore.getState().resetSettings()

      setUser(null)
      setIsLoading(false)
      router.push('/auth/login')
    }
  }, [router])

  // Sign in with Google
  const signInWithGoogle = useCallback(async () => {
    setIsLoading(true)
    setError(null)

    try {
      await authClient.signIn.social({
        provider: 'google',
        callbackURL: '/onboarding',
      })
    } catch (err) {
      const message = err instanceof Error ? err.message : 'Failed to sign in with Google'
      setError(message)
      throw err
    } finally {
      setIsLoading(false)
    }
  }, [])

  // Sign in with GitHub
  const signInWithGitHub = useCallback(async () => {
    setIsLoading(true)
    setError(null)

    try {
      await authClient.signIn.social({
        provider: 'github',
        callbackURL: '/onboarding',
      })
    } catch (err) {
      const message = err instanceof Error ? err.message : 'Failed to sign in with GitHub'
      setError(message)
      throw err
    } finally {
      setIsLoading(false)
    }
  }, [])

  // Send magic link via Better Auth magic-link plugin
  const sendMagicLink = useCallback(async (email: string) => {
    setIsLoading(true)
    setError(null)

    try {
      const { error: authError } = await authClient.signIn.magicLink({
        email,
        callbackURL: '/dashboard',
      })

      if (authError) {
        throw new Error(authError.message || 'Failed to send magic link')
      }
    } catch (err) {
      const message = err instanceof Error ? err.message : 'Failed to send magic link'
      setError(message)
      throw err
    } finally {
      setIsLoading(false)
    }
  }, [])

  // Clear error
  const clearError = useCallback(() => {
    setError(null)
  }, [])

  const value = useMemo<AuthContextType>(() => ({
    user,
    isLoading,
    isAuthenticated: !!user,
    error,
    signIn,
    signUp,
    signOut,
    signInWithGoogle,
    signInWithGitHub,
    sendMagicLink,
    clearError,
  }), [user, isLoading, error, signIn, signUp, signOut, signInWithGoogle, signInWithGitHub, sendMagicLink, clearError])

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>
}

/**
 * Hook to use authentication
 */
export function useAuth(): AuthContextType {
  const context = useContext(AuthContext)

  if (context === undefined) {
    throw new Error('useAuth must be used within an AuthProvider')
  }

  return context
}

/**
 * Hook to require authentication
 *
 * Redirects to login if not authenticated.
 */
export function useRequireAuth(): AuthContextType {
  const auth = useAuth()
  const router = useRouter()

  useEffect(() => {
    if (!auth.isLoading && !auth.isAuthenticated) {
      router.push('/auth/login')
    }
  }, [auth.isLoading, auth.isAuthenticated, router])

  return auth
}
