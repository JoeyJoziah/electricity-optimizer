'use client'

/**
 * Authentication Hook
 *
 * Provides authentication state and methods for React components.
 */

import { useState, useEffect, useCallback, createContext, useContext, ReactNode } from 'react'
import { useRouter } from 'next/navigation'
import {
  AuthUser,
  signIn as apiSignIn,
  signUp as apiSignUp,
  signOut as apiSignOut,
  signInWithOAuth,
  signInWithMagicLink,
  refreshAccessToken,
  getCurrentUser,
  storeTokens,
  getStoredAccessToken,
  getStoredRefreshToken,
  clearStoredTokens,
  AuthError,
} from '@/lib/auth/supabase'

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
 * Wraps the application and provides auth state and methods.
 */
export function AuthProvider({ children }: AuthProviderProps) {
  const [user, setUser] = useState<AuthUser | null>(null)
  const [isLoading, setIsLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const router = useRouter()

  // Initialize auth state from stored token
  useEffect(() => {
    const initAuth = async () => {
      const token = getStoredAccessToken()

      if (token) {
        try {
          const currentUser = await getCurrentUser(token)
          setUser(currentUser)
        } catch {
          // Token expired or invalid, try to refresh
          const refreshToken = getStoredRefreshToken()
          if (refreshToken) {
            try {
              const { accessToken, refreshToken: newRefreshToken } = await refreshAccessToken(refreshToken)
              storeTokens(accessToken, newRefreshToken)
              const currentUser = await getCurrentUser(accessToken)
              setUser(currentUser)
            } catch {
              // Refresh failed, clear tokens
              clearStoredTokens()
            }
          }
        }
      }

      setIsLoading(false)
    }

    initAuth()
  }, [])

  // Sign in with email/password
  const signIn = useCallback(async (email: string, password: string) => {
    setIsLoading(true)
    setError(null)

    try {
      const { accessToken, refreshToken } = await apiSignIn({ email, password })
      storeTokens(accessToken, refreshToken)

      const currentUser = await getCurrentUser(accessToken)
      setUser(currentUser)

      router.push('/dashboard')
    } catch (err) {
      const message = err instanceof AuthError ? err.message : 'Failed to sign in'
      setError(message)
      throw err
    } finally {
      setIsLoading(false)
    }
  }, [router])

  // Sign up with email/password
  const signUp = useCallback(async (email: string, password: string, name?: string) => {
    setIsLoading(true)
    setError(null)

    try {
      const { accessToken, refreshToken } = await apiSignUp({ email, password, name })
      storeTokens(accessToken, refreshToken)

      const currentUser = await getCurrentUser(accessToken)
      setUser(currentUser)

      router.push('/dashboard')
    } catch (err) {
      const message = err instanceof AuthError ? err.message : 'Failed to sign up'
      setError(message)
      throw err
    } finally {
      setIsLoading(false)
    }
  }, [router])

  // Sign out
  const signOut = useCallback(async () => {
    setIsLoading(true)

    try {
      await apiSignOut()
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
      const redirectUrl = `${window.location.origin}/auth/callback`
      const { url } = await signInWithOAuth('google', redirectUrl)
      window.location.href = url
    } catch (err) {
      const message = err instanceof AuthError ? err.message : 'Failed to sign in with Google'
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
      const redirectUrl = `${window.location.origin}/auth/callback`
      const { url } = await signInWithOAuth('github', redirectUrl)
      window.location.href = url
    } catch (err) {
      const message = err instanceof AuthError ? err.message : 'Failed to sign in with GitHub'
      setError(message)
      setIsLoading(false)
      throw err
    }
  }, [])

  // Send magic link
  const sendMagicLink = useCallback(async (email: string) => {
    setIsLoading(true)
    setError(null)

    try {
      const redirectUrl = `${window.location.origin}/auth/callback`
      await signInWithMagicLink(email, redirectUrl)
    } catch (err) {
      const message = err instanceof AuthError ? err.message : 'Failed to send magic link'
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

/**
 * Hook to get the current access token
 */
export function useAccessToken(): string | null {
  const [token, setToken] = useState<string | null>(null)

  useEffect(() => {
    setToken(getStoredAccessToken())
  }, [])

  return token
}
