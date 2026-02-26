import { renderHook, act, waitFor } from '@testing-library/react'
import React, { ReactNode } from 'react'
import '@testing-library/jest-dom'

// --- Mocks ---

// Mock authClient with controllable return values
const mockGetSession = jest.fn()
const mockSignInEmail = jest.fn()
const mockSignUpEmail = jest.fn()
const mockSignOut = jest.fn()
const mockSignInSocial = jest.fn()

jest.mock('@/lib/auth/client', () => ({
  authClient: {
    getSession: (...args: unknown[]) => mockGetSession(...args),
    signIn: {
      email: (...args: unknown[]) => mockSignInEmail(...args),
      social: (...args: unknown[]) => mockSignInSocial(...args),
    },
    signUp: {
      email: (...args: unknown[]) => mockSignUpEmail(...args),
    },
    signOut: (...args: unknown[]) => mockSignOut(...args),
  },
}))

// Mock supplier API
const mockGetUserSupplier = jest.fn()
jest.mock('@/lib/api/suppliers', () => ({
  getUserSupplier: (...args: unknown[]) => mockGetUserSupplier(...args),
}))

// Mock settings store
const mockSetCurrentSupplier = jest.fn()
jest.mock('@/lib/store/settings', () => ({
  useSettingsStore: {
    getState: () => ({
      setCurrentSupplier: mockSetCurrentSupplier,
    }),
  },
}))

// Mock next/navigation
const mockPush = jest.fn()
const mockReplace = jest.fn()
jest.mock('next/navigation', () => ({
  useRouter: () => ({
    push: mockPush,
    replace: mockReplace,
  }),
  usePathname: () => '/dashboard',
}))

// Import after mocks are set up
import { AuthProvider, useAuth, useRequireAuth } from '@/lib/hooks/useAuth'

// Helpers
function createWrapper() {
  return function Wrapper({ children }: { children: ReactNode }) {
    return <AuthProvider>{children}</AuthProvider>
  }
}

// Save original location
const originalLocation = window.location

describe('useAuth hook', () => {
  beforeEach(() => {
    jest.clearAllMocks()

    // Default: no session, no supplier
    mockGetSession.mockResolvedValue({ data: null, error: null })
    mockGetUserSupplier.mockResolvedValue({ supplier: null })

    // Reset window.location for tests that check redirect
    // Use a writable descriptor so tests can assign window.location.href
    Object.defineProperty(window, 'location', {
      writable: true,
      value: {
        ...originalLocation,
        href: 'http://localhost:3000/auth/login',
        search: '',
        pathname: '/auth/login',
        origin: 'http://localhost:3000',
      },
    })

    // Reset fetch mock (used by signOut for backend cache invalidation)
    ;(global.fetch as jest.Mock).mockResolvedValue({ ok: true })
  })

  afterAll(() => {
    Object.defineProperty(window, 'location', {
      writable: true,
      value: originalLocation,
    })
  })

  // -------------------------------------------------------------------------
  // Context guard
  // -------------------------------------------------------------------------
  it('throws when useAuth is used outside AuthProvider', () => {
    // Suppress console.error for the expected error
    const spy = jest.spyOn(console, 'error').mockImplementation(() => {})

    expect(() => {
      renderHook(() => useAuth())
    }).toThrow('useAuth must be used within an AuthProvider')

    spy.mockRestore()
  })

  // -------------------------------------------------------------------------
  // Session initialization
  // -------------------------------------------------------------------------
  it('initializes with loading state then resolves to unauthenticated', async () => {
    const wrapper = createWrapper()
    const { result } = renderHook(() => useAuth(), { wrapper })

    // Initially loading
    expect(result.current.isLoading).toBe(true)

    await waitFor(() => {
      expect(result.current.isLoading).toBe(false)
    })

    expect(result.current.user).toBeNull()
    expect(result.current.isAuthenticated).toBe(false)
    expect(result.current.error).toBeNull()
  })

  it('initializes with authenticated user when session exists', async () => {
    mockGetSession.mockResolvedValue({
      data: {
        user: {
          id: 'user-123',
          email: 'test@example.com',
          name: 'Test User',
          emailVerified: true,
          createdAt: new Date('2026-01-01'),
        },
        session: { id: 'sess-1' },
      },
      error: null,
    })

    const wrapper = createWrapper()
    const { result } = renderHook(() => useAuth(), { wrapper })

    await waitFor(() => {
      expect(result.current.isLoading).toBe(false)
    })

    expect(result.current.isAuthenticated).toBe(true)
    expect(result.current.user).toEqual({
      id: 'user-123',
      email: 'test@example.com',
      name: 'Test User',
      emailVerified: true,
      createdAt: expect.any(String),
    })
  })

  it('syncs supplier to settings store when session and supplier both succeed', async () => {
    mockGetSession.mockResolvedValue({
      data: {
        user: {
          id: 'user-123',
          email: 'test@example.com',
          name: 'Test User',
          emailVerified: true,
          createdAt: new Date('2026-01-01'),
        },
      },
    })
    mockGetUserSupplier.mockResolvedValue({
      supplier: {
        supplier_id: 'sup-1',
        supplier_name: 'Eversource Energy',
        green_energy: true,
        rating: 4.2,
      },
    })

    const wrapper = createWrapper()
    renderHook(() => useAuth(), { wrapper })

    await waitFor(() => {
      expect(mockSetCurrentSupplier).toHaveBeenCalledWith(
        expect.objectContaining({
          id: 'sup-1',
          name: 'Eversource Energy',
          greenEnergy: true,
          rating: 4.2,
        })
      )
    })
  })

  it('handles getSession failure gracefully', async () => {
    mockGetSession.mockRejectedValue(new Error('Network failure'))

    const wrapper = createWrapper()
    const { result } = renderHook(() => useAuth(), { wrapper })

    await waitFor(() => {
      expect(result.current.isLoading).toBe(false)
    })

    // Should not crash -- just remain unauthenticated
    expect(result.current.user).toBeNull()
    expect(result.current.isAuthenticated).toBe(false)
  })

  // -------------------------------------------------------------------------
  // signIn
  // -------------------------------------------------------------------------
  it('signIn sets user on success and redirects', async () => {
    mockSignInEmail.mockResolvedValue({
      data: {
        user: {
          id: 'user-456',
          email: 'login@example.com',
          name: 'Login User',
          emailVerified: false,
          createdAt: new Date('2026-02-01'),
        },
      },
      error: null,
    })

    const wrapper = createWrapper()
    const { result } = renderHook(() => useAuth(), { wrapper })

    // Wait for init
    await waitFor(() => {
      expect(result.current.isLoading).toBe(false)
    })

    await act(async () => {
      await result.current.signIn('login@example.com', 'password123')
    })

    expect(mockSignInEmail).toHaveBeenCalledWith({
      email: 'login@example.com',
      password: 'password123',
    })

    expect(result.current.user?.email).toBe('login@example.com')
    // Redirects via window.location.href
    expect(window.location.href).toBe('/dashboard')
  })

  it('signIn uses callbackUrl from query params when safe', async () => {
    // Set search params with a callbackUrl
    Object.defineProperty(window, 'location', {
      writable: true,
      value: {
        ...window.location,
        href: 'http://localhost:3000/auth/login?callbackUrl=%2Fprices',
        search: '?callbackUrl=%2Fprices',
      },
    })

    mockSignInEmail.mockResolvedValue({
      data: {
        user: {
          id: 'u-1',
          email: 'a@b.com',
          name: '',
          emailVerified: false,
          createdAt: new Date(),
        },
      },
      error: null,
    })

    const wrapper = createWrapper()
    const { result } = renderHook(() => useAuth(), { wrapper })

    await waitFor(() => {
      expect(result.current.isLoading).toBe(false)
    })

    await act(async () => {
      await result.current.signIn('a@b.com', 'pass')
    })

    // Should redirect to /prices, not /dashboard
    expect(window.location.href).toBe('/prices')
  })

  it('signIn rejects unsafe callbackUrl (protocol-relative)', async () => {
    Object.defineProperty(window, 'location', {
      writable: true,
      value: {
        ...window.location,
        href: 'http://localhost:3000/auth/login?callbackUrl=%2F%2Fevil.com',
        search: '?callbackUrl=%2F%2Fevil.com',
      },
    })

    mockSignInEmail.mockResolvedValue({
      data: {
        user: {
          id: 'u-1',
          email: 'a@b.com',
          name: '',
          emailVerified: false,
          createdAt: new Date(),
        },
      },
      error: null,
    })

    const wrapper = createWrapper()
    const { result } = renderHook(() => useAuth(), { wrapper })

    await waitFor(() => {
      expect(result.current.isLoading).toBe(false)
    })

    await act(async () => {
      await result.current.signIn('a@b.com', 'pass')
    })

    // Protocol-relative //evil.com should be rejected, fallback to /dashboard
    expect(window.location.href).toBe('/dashboard')
  })

  it('signIn sets error on auth failure', async () => {
    mockSignInEmail.mockResolvedValue({
      data: null,
      error: { message: 'Invalid credentials' },
    })

    const wrapper = createWrapper()
    const { result } = renderHook(() => useAuth(), { wrapper })

    await waitFor(() => {
      expect(result.current.isLoading).toBe(false)
    })

    // The signIn method sets error state then re-throws.
    // We catch the rejection and then wait for the state update to flush.
    let caughtError: unknown
    await act(async () => {
      try {
        await result.current.signIn('bad@example.com', 'wrong')
      } catch (e) {
        caughtError = e
      }
    })

    expect(caughtError).toBeDefined()
    expect((caughtError as Error).message).toBe('Invalid credentials')

    await waitFor(() => {
      expect(result.current.error).toBe('Invalid credentials')
    })
    expect(result.current.user).toBeNull()
  })

  it('signIn sets generic error when auth throws non-Error', async () => {
    mockSignInEmail.mockRejectedValue('Network timeout')

    const wrapper = createWrapper()
    const { result } = renderHook(() => useAuth(), { wrapper })

    await waitFor(() => {
      expect(result.current.isLoading).toBe(false)
    })

    let caughtError: unknown
    await act(async () => {
      try {
        await result.current.signIn('a@b.com', 'pass')
      } catch (e) {
        caughtError = e
      }
    })

    expect(caughtError).toBeDefined()

    await waitFor(() => {
      expect(result.current.error).toBe('Failed to sign in')
    })
  })

  // -------------------------------------------------------------------------
  // signUp
  // -------------------------------------------------------------------------
  it('signUp sets user on success and redirects to dashboard', async () => {
    mockSignUpEmail.mockResolvedValue({
      data: {
        user: {
          id: 'user-new',
          email: 'new@example.com',
          name: 'New User',
          emailVerified: false,
          createdAt: new Date('2026-02-25'),
        },
      },
      error: null,
    })

    const wrapper = createWrapper()
    const { result } = renderHook(() => useAuth(), { wrapper })

    await waitFor(() => {
      expect(result.current.isLoading).toBe(false)
    })

    await act(async () => {
      await result.current.signUp('new@example.com', 'securepass', 'New User')
    })

    expect(mockSignUpEmail).toHaveBeenCalledWith({
      email: 'new@example.com',
      password: 'securepass',
      name: 'New User',
    })
    expect(result.current.user?.id).toBe('user-new')
    expect(window.location.href).toBe('/dashboard')
  })

  it('signUp sets error on failure', async () => {
    mockSignUpEmail.mockResolvedValue({
      data: null,
      error: { message: 'Email already registered' },
    })

    const wrapper = createWrapper()
    const { result } = renderHook(() => useAuth(), { wrapper })

    await waitFor(() => {
      expect(result.current.isLoading).toBe(false)
    })

    let caughtError: unknown
    await act(async () => {
      try {
        await result.current.signUp('existing@example.com', 'pass')
      } catch (e) {
        caughtError = e
      }
    })

    expect(caughtError).toBeDefined()
    expect((caughtError as Error).message).toBe('Email already registered')

    await waitFor(() => {
      expect(result.current.error).toBe('Email already registered')
    })
  })

  it('signUp sends empty name when name is not provided', async () => {
    mockSignUpEmail.mockResolvedValue({
      data: {
        user: {
          id: 'u-1',
          email: 'a@b.com',
          name: '',
          emailVerified: false,
          createdAt: new Date(),
        },
      },
      error: null,
    })

    const wrapper = createWrapper()
    const { result } = renderHook(() => useAuth(), { wrapper })

    await waitFor(() => {
      expect(result.current.isLoading).toBe(false)
    })

    await act(async () => {
      await result.current.signUp('a@b.com', 'pass')
    })

    expect(mockSignUpEmail).toHaveBeenCalledWith({
      email: 'a@b.com',
      password: 'pass',
      name: '',
    })
  })

  // -------------------------------------------------------------------------
  // signOut
  // -------------------------------------------------------------------------
  it('signOut clears user state and redirects to login', async () => {
    // Start with a valid session
    mockGetSession.mockResolvedValue({
      data: {
        user: {
          id: 'user-123',
          email: 'test@example.com',
          name: 'Test',
          emailVerified: true,
          createdAt: new Date(),
        },
      },
    })
    mockSignOut.mockResolvedValue({ data: null, error: null })

    const wrapper = createWrapper()
    const { result } = renderHook(() => useAuth(), { wrapper })

    await waitFor(() => {
      expect(result.current.isAuthenticated).toBe(true)
    })

    await act(async () => {
      await result.current.signOut()
    })

    expect(result.current.user).toBeNull()
    expect(result.current.isAuthenticated).toBe(false)
    expect(mockPush).toHaveBeenCalledWith('/auth/login')
  })

  it('signOut calls backend logout for cache invalidation', async () => {
    mockGetSession.mockResolvedValue({
      data: {
        user: {
          id: 'u-1',
          email: 'a@b.com',
          emailVerified: true,
          createdAt: new Date(),
        },
      },
    })
    mockSignOut.mockResolvedValue({})

    const wrapper = createWrapper()
    const { result } = renderHook(() => useAuth(), { wrapper })

    await waitFor(() => {
      expect(result.current.isAuthenticated).toBe(true)
    })

    await act(async () => {
      await result.current.signOut()
    })

    // Check that fetch was called for backend cache invalidation
    expect(global.fetch).toHaveBeenCalledWith(
      expect.stringContaining('/auth/logout'),
      expect.objectContaining({ method: 'POST', credentials: 'include' })
    )
  })

  it('signOut clears state even when authClient.signOut throws', async () => {
    mockGetSession.mockResolvedValue({
      data: {
        user: {
          id: 'u-1',
          email: 'a@b.com',
          emailVerified: true,
          createdAt: new Date(),
        },
      },
    })
    mockSignOut.mockRejectedValue(new Error('signOut exploded'))

    const wrapper = createWrapper()
    const { result } = renderHook(() => useAuth(), { wrapper })

    await waitFor(() => {
      expect(result.current.isAuthenticated).toBe(true)
    })

    await act(async () => {
      await result.current.signOut()
    })

    // User should still be cleared
    expect(result.current.user).toBeNull()
    expect(result.current.isAuthenticated).toBe(false)
    expect(mockPush).toHaveBeenCalledWith('/auth/login')
  })

  // -------------------------------------------------------------------------
  // Social sign-in
  // -------------------------------------------------------------------------
  it('signInWithGoogle calls social provider', async () => {
    mockSignInSocial.mockResolvedValue({ data: null, error: null })

    const wrapper = createWrapper()
    const { result } = renderHook(() => useAuth(), { wrapper })

    await waitFor(() => {
      expect(result.current.isLoading).toBe(false)
    })

    await act(async () => {
      await result.current.signInWithGoogle()
    })

    expect(mockSignInSocial).toHaveBeenCalledWith({
      provider: 'google',
      callbackURL: '/dashboard',
    })
  })

  it('signInWithGitHub calls social provider', async () => {
    mockSignInSocial.mockResolvedValue({ data: null, error: null })

    const wrapper = createWrapper()
    const { result } = renderHook(() => useAuth(), { wrapper })

    await waitFor(() => {
      expect(result.current.isLoading).toBe(false)
    })

    await act(async () => {
      await result.current.signInWithGitHub()
    })

    expect(mockSignInSocial).toHaveBeenCalledWith({
      provider: 'github',
      callbackURL: '/dashboard',
    })
  })

  it('signInWithGoogle sets error on failure', async () => {
    mockSignInSocial.mockRejectedValue(new Error('Google OAuth failed'))

    const wrapper = createWrapper()
    const { result } = renderHook(() => useAuth(), { wrapper })

    await waitFor(() => {
      expect(result.current.isLoading).toBe(false)
    })

    let caughtError: unknown
    await act(async () => {
      try {
        await result.current.signInWithGoogle()
      } catch (e) {
        caughtError = e
      }
    })

    expect(caughtError).toBeDefined()
    expect((caughtError as Error).message).toBe('Google OAuth failed')

    await waitFor(() => {
      expect(result.current.error).toBe('Google OAuth failed')
    })
  })

  it('signInWithGitHub sets error on failure', async () => {
    mockSignInSocial.mockRejectedValue(new Error('GitHub OAuth failed'))

    const wrapper = createWrapper()
    const { result } = renderHook(() => useAuth(), { wrapper })

    await waitFor(() => {
      expect(result.current.isLoading).toBe(false)
    })

    let caughtError: unknown
    await act(async () => {
      try {
        await result.current.signInWithGitHub()
      } catch (e) {
        caughtError = e
      }
    })

    expect(caughtError).toBeDefined()

    await waitFor(() => {
      expect(result.current.error).toBe('GitHub OAuth failed')
    })
  })

  // -------------------------------------------------------------------------
  // Magic link
  // -------------------------------------------------------------------------
  it('sendMagicLink sets unavailable message', async () => {
    const wrapper = createWrapper()
    const { result } = renderHook(() => useAuth(), { wrapper })

    await waitFor(() => {
      expect(result.current.isLoading).toBe(false)
    })

    await act(async () => {
      await result.current.sendMagicLink('test@example.com')
    })

    expect(result.current.error).toBe(
      'Magic link sign-in is not currently available. Please use email/password or social login.'
    )
  })

  // -------------------------------------------------------------------------
  // clearError
  // -------------------------------------------------------------------------
  it('clearError resets the error state', async () => {
    const wrapper = createWrapper()
    const { result } = renderHook(() => useAuth(), { wrapper })

    await waitFor(() => {
      expect(result.current.isLoading).toBe(false)
    })

    // Set an error via sendMagicLink (does not throw, simply sets error)
    await act(async () => {
      await result.current.sendMagicLink('test@example.com')
    })

    expect(result.current.error).toBe(
      'Magic link sign-in is not currently available. Please use email/password or social login.'
    )

    act(() => {
      result.current.clearError()
    })

    expect(result.current.error).toBeNull()
  })

  // -------------------------------------------------------------------------
  // isAuthenticated derived state
  // -------------------------------------------------------------------------
  it('isAuthenticated is derived from user presence', async () => {
    mockGetSession.mockResolvedValue({
      data: {
        user: {
          id: 'u-1',
          email: 'a@b.com',
          emailVerified: true,
          createdAt: new Date(),
        },
      },
    })

    const wrapper = createWrapper()
    const { result } = renderHook(() => useAuth(), { wrapper })

    // While loading, user is null so isAuthenticated is false
    expect(result.current.isAuthenticated).toBe(false)

    await waitFor(() => {
      expect(result.current.isLoading).toBe(false)
    })

    expect(result.current.isAuthenticated).toBe(true)
  })
})

// ---------------------------------------------------------------------------
// useRequireAuth
// ---------------------------------------------------------------------------
describe('useRequireAuth hook', () => {
  beforeEach(() => {
    jest.clearAllMocks()
    mockGetSession.mockResolvedValue({ data: null, error: null })
    mockGetUserSupplier.mockResolvedValue({ supplier: null })
    ;(global.fetch as jest.Mock).mockResolvedValue({ ok: true })
  })

  it('redirects to login when not authenticated', async () => {
    const wrapper = createWrapper()
    const { result } = renderHook(() => useRequireAuth(), { wrapper })

    await waitFor(() => {
      expect(result.current.isLoading).toBe(false)
    })

    expect(mockPush).toHaveBeenCalledWith('/auth/login')
  })

  it('does not redirect when authenticated', async () => {
    mockGetSession.mockResolvedValue({
      data: {
        user: {
          id: 'user-123',
          email: 'test@example.com',
          name: 'Test',
          emailVerified: true,
          createdAt: new Date(),
        },
      },
    })

    const wrapper = createWrapper()
    const { result } = renderHook(() => useRequireAuth(), { wrapper })

    await waitFor(() => {
      expect(result.current.isLoading).toBe(false)
    })

    expect(result.current.isAuthenticated).toBe(true)
    // push should NOT have been called for redirect to login
    expect(mockPush).not.toHaveBeenCalledWith('/auth/login')
  })

  it('does not redirect while loading', async () => {
    // Make getSession hang so isLoading stays true
    mockGetSession.mockReturnValue(new Promise(() => {}))

    const wrapper = createWrapper()
    const { result } = renderHook(() => useRequireAuth(), { wrapper })

    // Still loading
    expect(result.current.isLoading).toBe(true)

    // Should not redirect while loading
    expect(mockPush).not.toHaveBeenCalled()
  })
})
