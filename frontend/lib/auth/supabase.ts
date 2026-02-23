/**
 * Authentication Client
 *
 * Auth utility functions using the custom backend JWT endpoints.
 */

// Auth helper types
export interface AuthUser {
  id: string
  email: string
  name?: string
  emailVerified: boolean
  createdAt: string
}

export interface AuthSession {
  accessToken: string
  refreshToken: string
  expiresAt: number
}

export interface SignUpData {
  email: string
  password: string
  name?: string
}

export interface SignInData {
  email: string
  password: string
}

// Auth error types
export class AuthError extends Error {
  constructor(
    message: string,
    public code?: string
  ) {
    super(message)
    this.name = 'AuthError'
  }
}

// Auth API functions using the backend
const API_URL = process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000/api/v1'

export async function signUp(data: SignUpData): Promise<{ accessToken: string; refreshToken: string }> {
  const response = await fetch(`${API_URL}/auth/signup`, {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
    },
    body: JSON.stringify(data),
  })

  if (!response.ok) {
    const error = await response.json()
    throw new AuthError(error.detail || 'Failed to sign up', response.status.toString())
  }

  return response.json()
}

export async function signIn(data: SignInData): Promise<{ accessToken: string; refreshToken: string }> {
  const response = await fetch(`${API_URL}/auth/signin`, {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
    },
    credentials: 'include', // Include cookies for refresh token
    body: JSON.stringify(data),
  })

  if (!response.ok) {
    const error = await response.json()
    throw new AuthError(error.detail || 'Invalid email or password', response.status.toString())
  }

  return response.json()
}

export async function signInWithOAuth(
  provider: 'google' | 'github',
  redirectUrl: string
): Promise<{ url: string }> {
  const response = await fetch(`${API_URL}/auth/signin/oauth`, {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
    },
    body: JSON.stringify({
      provider,
      redirect_url: redirectUrl,
    }),
  })

  if (!response.ok) {
    const error = await response.json()
    throw new AuthError(error.detail || 'Failed to initiate OAuth', response.status.toString())
  }

  return response.json()
}

export async function signInWithMagicLink(email: string, redirectUrl: string): Promise<{ message: string }> {
  const response = await fetch(`${API_URL}/auth/signin/magic-link`, {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
    },
    body: JSON.stringify({
      email,
      redirect_url: redirectUrl,
    }),
  })

  if (!response.ok) {
    const error = await response.json()
    throw new AuthError(error.detail || 'Failed to send magic link', response.status.toString())
  }

  return response.json()
}

export async function signOut(): Promise<void> {
  const token = getStoredAccessToken()

  const response = await fetch(`${API_URL}/auth/signout`, {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
      ...(token ? { Authorization: `Bearer ${token}` } : {}),
    },
    credentials: 'include',
  })

  // Clear local storage regardless of response
  clearStoredTokens()

  if (!response.ok) {
    console.error('Sign out failed on server')
  }
}

export async function refreshAccessToken(refreshToken?: string): Promise<{ accessToken: string; refreshToken: string }> {
  const response = await fetch(`${API_URL}/auth/refresh`, {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
    },
    credentials: 'include',
    body: refreshToken ? JSON.stringify({ refresh_token: refreshToken }) : undefined,
  })

  if (!response.ok) {
    throw new AuthError('Failed to refresh token', response.status.toString())
  }

  return response.json()
}

export async function getCurrentUser(token: string): Promise<AuthUser> {
  const response = await fetch(`${API_URL}/auth/me`, {
    method: 'GET',
    headers: {
      'Content-Type': 'application/json',
      Authorization: `Bearer ${token}`,
    },
  })

  if (!response.ok) {
    throw new AuthError('Failed to get user', response.status.toString())
  }

  const data = await response.json()
  return {
    id: data.id,
    email: data.email,
    name: data.name,
    emailVerified: data.email_verified,
    createdAt: data.created_at,
  }
}

// Token storage utilities
const ACCESS_TOKEN_KEY = 'auth_access_token'
const REFRESH_TOKEN_KEY = 'auth_refresh_token'

export function storeTokens(accessToken: string, refreshToken: string): void {
  if (typeof window !== 'undefined') {
    localStorage.setItem(ACCESS_TOKEN_KEY, accessToken)
    localStorage.setItem(REFRESH_TOKEN_KEY, refreshToken)
  }
}

export function getStoredAccessToken(): string | null {
  if (typeof window !== 'undefined') {
    return localStorage.getItem(ACCESS_TOKEN_KEY)
  }
  return null
}

export function getStoredRefreshToken(): string | null {
  if (typeof window !== 'undefined') {
    return localStorage.getItem(REFRESH_TOKEN_KEY)
  }
  return null
}

export function clearStoredTokens(): void {
  if (typeof window !== 'undefined') {
    localStorage.removeItem(ACCESS_TOKEN_KEY)
    localStorage.removeItem(REFRESH_TOKEN_KEY)
  }
}
