/**
 * E2E Auth Helpers for Better Auth
 *
 * Provides route mocking for Better Auth's /api/auth/* endpoints
 * and session cookie management for authenticated test scenarios.
 */

import { Page } from '@playwright/test'

const SESSION_COOKIE_NAME = 'better-auth.session_token'
const MOCK_SESSION_TOKEN = 'mock-session-token-e2e-test'

const MOCK_USER = {
  id: 'user_e2e_123',
  email: 'test@example.com',
  name: 'Test User',
  emailVerified: true,
  createdAt: '2026-01-01T00:00:00.000Z',
  updatedAt: '2026-01-01T00:00:00.000Z',
}

const MOCK_SESSION = {
  id: 'session_e2e_123',
  userId: MOCK_USER.id,
  token: MOCK_SESSION_TOKEN,
  expiresAt: new Date(Date.now() + 7 * 24 * 60 * 60 * 1000).toISOString(),
}

/**
 * Mock Better Auth API routes on the page.
 *
 * Intercepts /api/auth/* routes that the Better Auth client calls:
 * - POST /api/auth/sign-in/email — email/password sign-in
 * - GET  /api/auth/get-session — session validation
 * - POST /api/auth/sign-out — sign out (clears cookie)
 * - POST /api/auth/sign-up/email — email/password sign-up
 */
export async function mockBetterAuth(page: Page, options?: {
  signInShouldFail?: boolean
  sessionExpired?: boolean
  rateLimited?: boolean
  rateLimitAfter?: number
}) {
  let signInAttempts = 0

  // Mock sign-in
  await page.route('**/api/auth/sign-in/email', async (route) => {
    signInAttempts++

    if (options?.rateLimited || (options?.rateLimitAfter && signInAttempts > options.rateLimitAfter)) {
      return route.fulfill({
        status: 429,
        contentType: 'application/json',
        body: JSON.stringify({
          message: 'Too many login attempts. Please try again later.',
        }),
      })
    }

    const body = JSON.parse(route.request().postData() || '{}')

    if (options?.signInShouldFail || body.email !== 'test@example.com' || body.password !== 'TestPass123!') {
      return route.fulfill({
        status: 401,
        contentType: 'application/json',
        body: JSON.stringify({
          message: 'Invalid email or password',
        }),
      })
    }

    return route.fulfill({
      status: 200,
      contentType: 'application/json',
      headers: {
        'Set-Cookie': `${SESSION_COOKIE_NAME}=${MOCK_SESSION_TOKEN}; Path=/; HttpOnly; SameSite=Lax`,
      },
      body: JSON.stringify({
        user: MOCK_USER,
        session: MOCK_SESSION,
      }),
    })
  })

  // Mock get-session
  await page.route('**/api/auth/get-session', async (route) => {
    const cookies = route.request().headers()['cookie'] || ''
    const hasSession = cookies.includes(SESSION_COOKIE_NAME)

    if (options?.sessionExpired || !hasSession) {
      return route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify(null),
      })
    }

    return route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify({
        user: MOCK_USER,
        session: MOCK_SESSION,
      }),
    })
  })

  // Mock sign-out
  await page.route('**/api/auth/sign-out', async (route) => {
    return route.fulfill({
      status: 200,
      contentType: 'application/json',
      headers: {
        'Set-Cookie': `${SESSION_COOKIE_NAME}=; Path=/; HttpOnly; Max-Age=0`,
      },
      body: JSON.stringify({ success: true }),
    })
  })

  // Mock sign-up
  await page.route('**/api/auth/sign-up/email', async (route) => {
    return route.fulfill({
      status: 200,
      contentType: 'application/json',
      headers: {
        'Set-Cookie': `${SESSION_COOKIE_NAME}=${MOCK_SESSION_TOKEN}; Path=/; HttpOnly; SameSite=Lax`,
      },
      body: JSON.stringify({
        user: MOCK_USER,
        session: MOCK_SESSION,
      }),
    })
  })

  // Mock OAuth callback
  await page.route('**/api/auth/callback/**', async (route) => {
    return route.fulfill({
      status: 200,
      contentType: 'application/json',
      headers: {
        'Set-Cookie': `${SESSION_COOKIE_NAME}=${MOCK_SESSION_TOKEN}; Path=/; HttpOnly; SameSite=Lax`,
      },
      body: JSON.stringify({
        user: { ...MOCK_USER, email: 'oauth@example.com' },
        session: MOCK_SESSION,
      }),
    })
  })

  // Mock social sign-in (redirects to OAuth provider)
  await page.route('**/api/auth/sign-in/social', async (route) => {
    return route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify({
        url: 'https://accounts.google.com/mock-oauth',
        redirect: true,
      }),
    })
  })
}

/**
 * Set an authenticated session by injecting the Better Auth session cookie.
 * Call this before navigating to protected pages.
 */
export async function setAuthenticatedState(page: Page) {
  const url = new URL('http://localhost:3000')
  await page.context().addCookies([
    {
      name: SESSION_COOKIE_NAME,
      value: MOCK_SESSION_TOKEN,
      domain: url.hostname,
      path: '/',
      httpOnly: true,
      sameSite: 'Lax',
    },
  ])
}

/**
 * Clear the session cookie to simulate logged-out state.
 */
export async function clearAuthState(page: Page) {
  await page.context().clearCookies({ name: SESSION_COOKIE_NAME })
}
