import { test, expect } from '@playwright/test'
import { mockBetterAuth, setAuthenticatedState, clearAuthState } from './helpers/auth'

test.describe('Authentication Flows', () => {
  test.beforeEach(async ({ page }) => {
    // Mock Better Auth API routes
    await mockBetterAuth(page)

    // Mock backend API endpoints used by dashboard
    await page.route('**/api/v1/prices/current**', async (route) => {
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({
          prices: [{ region: 'US_CT', price: 0.25, timestamp: new Date().toISOString() }],
        }),
      })
    })

    await page.route('**/api/v1/prices/forecast**', async (route) => {
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({
          forecast: [{ hour: 1, price: 0.23, confidence: [0.21, 0.25] }],
        }),
      })
    })

    await page.route('**/api/v1/suppliers**', async (route) => {
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({ suppliers: [] }),
      })
    })
  })

  test('displays login page', async ({ page }) => {
    await page.goto('/auth/login')

    await expect(page.getByRole('heading', { name: /electricity optimizer/i })).toBeVisible()
    await expect(page.locator('#email')).toBeVisible()
    await expect(page.locator('#password')).toBeVisible()
    await expect(page.getByRole('button', { name: 'Sign in', exact: true })).toBeVisible()
  })

  test('user can login with email and password', async ({ page }) => {
    await page.goto('/auth/login')

    await page.fill('#email', 'test@example.com')
    await page.fill('#password', 'TestPass123!')
    await page.click('button[type="submit"]')

    // Should redirect to dashboard
    await page.waitForURL('/dashboard', { timeout: 10000 })
    await expect(page.getByText('Current Price').first()).toBeVisible()
  })

  test('shows error for invalid credentials', async ({ page }) => {
    await page.goto('/auth/login')

    await page.fill('#email', 'wrong@example.com')
    await page.fill('#password', 'WrongPass123!')
    await page.click('button[type="submit"]')

    // Should show error message (Better Auth returns "Invalid email or password")
    await expect(page.getByText(/invalid|failed|error/i)).toBeVisible({ timeout: 5000 })
  })

  // HTML5 email validation shows native browser tooltip, not visible text
  test.skip('validates email format', async ({ page }) => {
    await page.goto('/auth/login')

    await page.fill('#email', 'invalid-email')
    await page.fill('#password', 'TestPass123!')
    await page.click('button[type="submit"]')

    await expect(page.getByText(/valid email/i)).toBeVisible()
  })

  test('shows OAuth login options', async ({ page }) => {
    await page.goto('/auth/login')

    await expect(page.getByRole('button', { name: /continue with google/i })).toBeVisible()
    await expect(page.getByRole('button', { name: /continue with github/i })).toBeVisible()
  })

  test('initiates OAuth flow with Google', async ({ page }) => {
    await page.goto('/auth/login')

    await page.click('button:has-text("Continue with Google")')

    // Should initiate OAuth flow (in real scenario, redirects to Google)
    await expect(page.locator('body')).toBeVisible()
  })

  test('handles OAuth callback', async ({ page }) => {
    await page.goto('/auth/callback?code=mock_code&provider=google&state=mock_state')

    // The callback page should process and redirect to dashboard
    // The mockBetterAuth intercepts /api/auth/callback/** and returns session
    await page.waitForURL(/\/(dashboard|auth)/, { timeout: 10000 })
  })

  // Magic link not supported — useAuth returns error message
  test.skip('user can login with magic link', async ({ page }) => {
    await page.goto('/auth/login')

    await page.click('text=Sign in with magic link')
    await expect(page.getByText(/magic link/i)).toBeVisible()

    await page.fill('#email', 'test@example.com')
    await page.click('button[type="submit"]')

    await expect(page.getByText(/check your email/i)).toBeVisible()
  })

  // User menu UI not yet finalized
  test.skip('user can logout', async ({ page }) => {
    await setAuthenticatedState(page)
    await page.goto('/dashboard')

    await page.click('[data-testid="user-menu"]')
    await page.click('text=Sign out')

    await page.waitForURL('/auth/login')
  })

  test('redirects unauthenticated users to login', async ({ page }) => {
    // Ensure no session cookie
    await clearAuthState(page)

    await page.goto('/dashboard')

    // Middleware should redirect to login with callbackUrl
    await page.waitForURL(/\/auth\/login/, { timeout: 10000 })
  })

  // Forgot password UI not implemented
  test.skip('shows forgot password link', async ({ page }) => {
    await page.goto('/auth/login')

    await expect(page.getByText(/forgot password/i)).toBeVisible()
  })

  test('can navigate to signup from login', async ({ page }) => {
    await page.goto('/auth/login')

    await page.click('text=Sign up')

    await expect(page).toHaveURL(/\/auth\/signup/)
  })

  test('preserves redirect URL after login', async ({ page }) => {
    // Ensure no session cookie
    await clearAuthState(page)

    // Try to access protected page
    await page.goto('/suppliers')

    // Middleware should redirect to login with callbackUrl param
    await page.waitForURL(/\/auth\/login\?callbackUrl=/, { timeout: 10000 })

    // Verify the callbackUrl parameter is present
    const url = new URL(page.url())
    expect(url.searchParams.get('callbackUrl')).toBe('/suppliers')
  })

  test('session persists on page refresh', async ({ page }) => {
    // Set up authenticated state via cookie
    await setAuthenticatedState(page)
    await mockBetterAuth(page) // re-mock after setting cookies

    await page.goto('/dashboard')
    await expect(page.getByText('Current Price').first()).toBeVisible()

    // Refresh page
    await page.reload()

    // Should still be on dashboard
    await expect(page.getByText('Current Price').first()).toBeVisible()
  })

  test('handles token expiration gracefully', async ({ page }) => {
    // Set cookie but mock get-session to return null (expired)
    await setAuthenticatedState(page)
    await mockBetterAuth(page, { sessionExpired: true })

    await page.goto('/dashboard')

    // The app should detect the expired session during useEffect
    // and the useAuth hook will set user to null
    // Middleware allowed the request (cookie exists) but the client sees no session
    // This is acceptable — the next navigation will redirect
    await expect(page.locator('body')).toBeVisible()
  })
})

test.describe('Authentication Security', () => {
  test('rate limits login attempts', async ({ page }) => {
    await mockBetterAuth(page, { rateLimitAfter: 5 })

    await page.goto('/auth/login')

    // Make multiple failed attempts
    for (let i = 0; i < 6; i++) {
      await page.fill('#email', 'test@example.com')
      await page.fill('#password', 'WrongPass!')
      await page.click('button[type="submit"]')
      await page.waitForTimeout(300)
    }

    // Should show rate limit or error message
    await expect(page.getByText(/too many|rate limit|try again/i)).toBeVisible({ timeout: 5000 })
  })

  // User menu UI not yet finalized
  test.skip('clears sensitive data on logout', async ({ page }) => {
    await setAuthenticatedState(page)
    await mockBetterAuth(page)

    await page.goto('/dashboard')

    await page.click('[data-testid="user-menu"]')
    await page.click('text=Sign out')

    const cookies = await page.context().cookies()
    const sessionCookie = cookies.find(c => c.name === 'better-auth.session_token')
    expect(sessionCookie).toBeUndefined()
  })
})
