'use client'

/**
 * Authentication Hook
 *
 * Provides authentication state and methods using Better Auth client.
 * Session management uses httpOnly cookies (no localStorage tokens).
 */

import { useState, useEffect, useCallback, createContext, useContext, ReactNode } from 'react'
import { useRouter } from 'next/navigation'
import { authClient } from '@/lib/auth/client'

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

  // Initialize auth state from session cookie
  useEffect(() => {
    const initAuth = async () => {
      try {
        const { data: session } = await authClient.getSession()
        if (session?.user) {
          setUser({
            id: session.user.id,
            email: session.user.email,
            name: session.user.name || undefined,
            emailVerified: session.user.emailVerified,
            createdAt: session.user.createdAt?.toString() || '',
          })
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
      }

      // Honor callbackUrl if the middleware set one, otherwise go to dashboard.
      // Validate that it's a safe relative path (not //evil.com or javascript:).
      const params = new URLSearchParams(window.location.search)
      const callback = params.get('callbackUrl') || '/dashboard'
      const destination =
        callback.startsWith('/') && !callback.startsWith('//') ? callback : '/dashboard'

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
      const { data, error: authError } = await authClient.signUp.email({
        email,
        password,
        name: name || '',
      })

      if (authError) {
        throw new Error(authError.message || 'Failed to sign up')
      }

      if (data?.user) {
        setUser({
          id: data.user.id,
          email: data.user.email,
          name: data.user.name || undefined,
          emailVerified: data.user.emailVerified,
          createdAt: data.user.createdAt?.toString() || '',
        })
      }

      // Full-page navigation ensures middleware evaluates with the fresh
      // session cookie (router.push uses cached prefetch that may predate
      // the cookie being set).
      window.location.href = '/dashboard'
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

    // Invalidate backend Redis session cache first (best-effort).
    // Without this, the cached session remains valid for up to 30s
    // after Better Auth deletes it from the neon_auth.session table.
    try {
      const baseUrl = process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000/api/v1'
      await fetch(`${baseUrl}/auth/logout`, {
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
        callbackURL: '/dashboard',
      })
    } catch (err) {
      const message = err instanceof Error ? err.message : 'Failed to sign in with Google'
      setError(message)
      setIsLoading(false)
      throw err
    }
  }, [])

  // Sign in with GitHub
  const signInWithGitHub = useCallback(async () => {
    setIsLoading(true)
    setError(null)

    try {
      await authClient.signIn.social({
        provider: 'github',
        callbackURL: '/dashboard',
      })
    } catch (err) {
      const message = err instanceof Error ? err.message : 'Failed to sign in with GitHub'
      setError(message)
      setIsLoading(false)
      throw err
    }
  }, [])

  // Send magic link (not natively supported by better-auth — show message)
  const sendMagicLink = useCallback(async (_email: string) => {
    setError('Magic link sign-in is not currently available. Please use email/password or social login.')
  }, [])

  // Clear error
  const clearError = useCallback(() => {
    setError(null)
  }, [])

  const value: AuthContextType = {
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
  }

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
