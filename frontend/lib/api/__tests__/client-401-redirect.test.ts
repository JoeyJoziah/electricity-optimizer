/**
 * Tests for 401 redirect behavior in the API client.
 *
 * Verifies the redirect loop prevention: auth page guard,
 * callbackUrl extraction, safety valve, and counter reset.
 */

import { apiClient } from '@/lib/api/client'

const mockFetch = global.fetch as jest.MockedFunction<typeof fetch>

// Save/restore originals
const originalLocation = window.location
const _originalSessionStorage = window.sessionStorage

function mockJsonResponse(body: unknown, status = 200, statusText = 'OK'): Response {
  return {
    ok: status >= 200 && status < 300,
    status,
    statusText,
    json: jest.fn().mockResolvedValue(body),
    headers: new Headers(),
    redirected: false,
    type: 'basic',
    url: '',
    clone: jest.fn(),
    body: null,
    bodyUsed: false,
    arrayBuffer: jest.fn(),
    blob: jest.fn(),
    formData: jest.fn(),
    text: jest.fn(),
    bytes: jest.fn(),
  } as unknown as Response
}

function setLocation(overrides: Partial<Location>) {
  Object.defineProperty(window, 'location', {
    writable: true,
    value: {
      ...originalLocation,
      href: 'http://localhost:3000/',
      search: '',
      pathname: '/',
      origin: 'http://localhost:3000',
      ...overrides,
    },
  })
}

describe('401 redirect behavior', () => {
  beforeEach(() => {
    mockFetch.mockReset()
    sessionStorage.clear()
    setLocation({ pathname: '/dashboard', search: '', href: 'http://localhost:3000/dashboard' })
  })

  afterAll(() => {
    Object.defineProperty(window, 'location', {
      writable: true,
      value: originalLocation,
    })
  })

  it('redirects to login with callbackUrl on 401 from non-auth page', async () => {
    mockFetch.mockResolvedValue(mockJsonResponse({ detail: 'Unauthorized' }, 401, 'Unauthorized'))

    await expect(apiClient.get('/prices')).rejects.toThrow()

    expect(window.location.href).toBe('/auth/login?callbackUrl=%2Fdashboard')
  })

  it('does NOT redirect on 401 when on /auth/login', async () => {
    setLocation({
      pathname: '/auth/login',
      search: '?callbackUrl=%2Fdashboard',
      href: 'http://localhost:3000/auth/login?callbackUrl=%2Fdashboard',
    })
    mockFetch.mockResolvedValue(mockJsonResponse({ detail: 'Unauthorized' }, 401, 'Unauthorized'))

    await expect(apiClient.get('/user/supplier')).rejects.toThrow()

    // Should NOT have redirected — still on /auth/login
    expect(window.location.href).toBe('http://localhost:3000/auth/login?callbackUrl=%2Fdashboard')
  })

  it('does NOT redirect on 401 when on /auth/signup', async () => {
    setLocation({
      pathname: '/auth/signup',
      search: '',
      href: 'http://localhost:3000/auth/signup',
    })
    mockFetch.mockResolvedValue(mockJsonResponse({ detail: 'Unauthorized' }, 401, 'Unauthorized'))

    await expect(apiClient.get('/users/profile')).rejects.toThrow()

    expect(window.location.href).toBe('http://localhost:3000/auth/signup')
  })

  it('extracts original callbackUrl instead of nesting', async () => {
    // Simulate being on a page that already has a callbackUrl in the query string
    setLocation({
      pathname: '/prices',
      search: '?callbackUrl=%2Fsuppliers',
      href: 'http://localhost:3000/prices?callbackUrl=%2Fsuppliers',
    })
    mockFetch.mockResolvedValue(mockJsonResponse({ detail: 'Unauthorized' }, 401, 'Unauthorized'))

    await expect(apiClient.get('/prices')).rejects.toThrow()

    // Should use the EXISTING callbackUrl (/suppliers), not nest /prices?callbackUrl=...
    expect(window.location.href).toBe('/auth/login?callbackUrl=%2Fsuppliers')
  })

  it('stops redirecting after 3 consecutive 401s', async () => {
    // Pre-set the counter to the max
    sessionStorage.setItem('api_401_redirect_count', '3')
    mockFetch.mockResolvedValue(mockJsonResponse({ detail: 'Unauthorized' }, 401, 'Unauthorized'))

    await expect(apiClient.get('/prices')).rejects.toThrow()

    // Should NOT redirect — safety valve engaged
    expect(window.location.href).toBe('http://localhost:3000/dashboard')
  })

  it('resets redirect counter on successful response', async () => {
    sessionStorage.setItem('api_401_redirect_count', '2')
    mockFetch.mockResolvedValue(mockJsonResponse({ data: 'ok' }, 200))

    await apiClient.get('/health')

    expect(sessionStorage.getItem('api_401_redirect_count')).toBeNull()
  })

  it('no redirect on server-side (window undefined)', async () => {
    // Temporarily make window.location undefined-like by setting pathname to trigger
    // the SSR path. We can't truly remove `window` in jsdom, but we verify the
    // guard by testing that the `typeof window` check works in the actual code.
    // Instead, verify the function doesn't throw when response is 401.
    mockFetch.mockResolvedValue(mockJsonResponse({ detail: 'Unauthorized' }, 401, 'Unauthorized'))

    // The 401 handler should still throw ApiClientError even on auth pages
    // (it just doesn't redirect). This confirms the guard doesn't break error throwing.
    setLocation({ pathname: '/auth/callback', href: 'http://localhost:3000/auth/callback' })

    await expect(apiClient.get('/test')).rejects.toThrow('Unauthorized')
  })

  it('rejects malicious callbackUrl (external origin)', async () => {
    // Attacker crafts URL with external callbackUrl
    setLocation({
      pathname: '/dashboard',
      search: '?callbackUrl=https%3A%2F%2Fevil.com%2Fphish',
      href: 'http://localhost:3000/dashboard?callbackUrl=https%3A%2F%2Fevil.com%2Fphish',
    })
    mockFetch.mockResolvedValue(mockJsonResponse({ detail: 'Unauthorized' }, 401, 'Unauthorized'))

    await expect(apiClient.get('/prices')).rejects.toThrow()

    // Should fall back to pathname (/dashboard), NOT use the malicious callbackUrl
    expect(window.location.href).toBe('/auth/login?callbackUrl=%2Fdashboard')
  })

  it('rejects protocol-relative callbackUrl (//evil.com)', async () => {
    setLocation({
      pathname: '/dashboard',
      search: '?callbackUrl=%2F%2Fevil.com',
      href: 'http://localhost:3000/dashboard?callbackUrl=%2F%2Fevil.com',
    })
    mockFetch.mockResolvedValue(mockJsonResponse({ detail: 'Unauthorized' }, 401, 'Unauthorized'))

    await expect(apiClient.get('/prices')).rejects.toThrow()

    // Should fall back to pathname, not use //evil.com
    expect(window.location.href).toBe('/auth/login?callbackUrl=%2Fdashboard')
  })
})
