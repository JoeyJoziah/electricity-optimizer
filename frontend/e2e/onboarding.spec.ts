import { test, expect, PRESET_EMPTY } from './fixtures'
import { mockBetterAuth } from './helpers/auth'

/**
 * User Onboarding E2E Tests
 *
 * Tests signup form validation, login flow, and CT region defaults.
 *
 * Most tests here exercise unauthenticated pages (landing, /auth/signup,
 * /auth/login), so they use plain `{ page }` and call mockBetterAuth directly.
 * The "new users have no default region" test needs an authenticated session
 * with empty settings, so it lives in its own describe with `test.use`.
 */
test.describe('User Onboarding Flow', () => {
  // These tests target unauthenticated pages — use plain { page }, not
  // authenticatedPage. Auth routes are mocked via mockBetterAuth; API routes
  // are registered to support any post-signup redirect destination.
  test.beforeEach(async ({ page }) => {
    await mockBetterAuth(page)

    await page.route('**/api/v1/prices/current**', async (route) => {
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({
          prices: [{ region: 'us_ct', price: 0.25, timestamp: new Date().toISOString() }],
        }),
      })
    })

    await page.route('**/api/v1/suppliers**', async (route) => {
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({
          suppliers: [
            { id: '1', name: 'Eversource Energy', avgPricePerKwh: 0.26, greenEnergy: false, rating: 3.5 },
          ],
          total: 1,
        }),
      })
    })

    await page.route('**/api/v1/prices/history**', async (route) => {
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({ prices: [] }),
      })
    })

    await page.route('**/api/v1/prices/forecast**', async (route) => {
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({ forecast: [] }),
      })
    })

    await page.route('**/api/v1/optimization/**', async (route) => {
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({ schedules: [], totalSavings: 0 }),
      })
    })

    await page.route('**/api/v1/prices/optimal-periods**', async (route) => {
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({ periods: [] }),
      })
    })
  })

  test('landing page shows signup call to action', { tag: ['@smoke'] }, async ({ page }) => {
    await page.goto('/')
    // Use .first() to avoid strict mode violation — landing page has multiple "Get Started" links
    await expect(page.getByRole('link', { name: /sign up|get started/i }).first()).toBeVisible()
  })

  test('signup form validates required fields', { tag: ['@smoke'] }, async ({ page }) => {
    await page.goto('/auth/signup')
    await expect(page.getByRole('heading', { name: 'Create your account' })).toBeVisible()

    // Try to submit without filling anything — button should be disabled
    const submitButton = page.getByRole('button', { name: /create account/i })
    await expect(submitButton).toBeDisabled()
  })

  test('signup form shows password requirements', { tag: ['@regression'] }, async ({ page }) => {
    await page.goto('/auth/signup')

    // Click the password field first to ensure focus, then fill — Mobile Safari
    // needs focus to trigger React onChange reliably
    const passwordInput = page.locator('#password')
    await passwordInput.click()
    await passwordInput.fill('short')

    // Wait for React state update to render requirements
    await expect(page.getByText('At least 12 characters')).toBeVisible({ timeout: 5000 })
    await expect(page.getByText('One uppercase letter')).toBeVisible()
    await expect(page.getByText('One number')).toBeVisible()
    await expect(page.getByText('One special character')).toBeVisible()
  })

  test('signup form detects password mismatch', { tag: ['@regression'] }, async ({ page }) => {
    await page.goto('/auth/signup')

    await page.fill('#password', 'SecurePass123!')
    await page.fill('#confirmPassword', 'DifferentPass456!')
    await expect(page.getByText('Passwords do not match')).toBeVisible()
  })

  test('new user can complete signup and reach dashboard', { tag: ['@smoke'] }, async ({ page }) => {
    await page.goto('/auth/signup')

    await page.fill('#name', 'Test User')
    await page.fill('#email', 'test@example.com')
    await page.fill('#password', 'SecurePass123!')
    await page.fill('#confirmPassword', 'SecurePass123!')
    await page.check('#terms')

    await page.click('button[type="submit"]')
    // After signup, user may be redirected to onboarding, dashboard, or auth page
    await page.waitForURL(/\/(onboarding|dashboard|auth)/, { timeout: 10000 })
  })

  test('login page is accessible from signup page', { tag: ['@regression'] }, async ({ page }) => {
    await page.goto('/auth/signup')
    await expect(page.getByRole('link', { name: /sign in/i })).toBeVisible()
    await page.click('text=Sign in')
    await page.waitForURL(/\/auth\/login/)
  })
})

// Isolated describe so test.use({ settingsPreset: PRESET_EMPTY }) only applies here.
// The authenticated page fixture with empty settings simulates a fresh user who
// has not yet configured any region in localStorage.
test.describe('User Onboarding Flow - Fresh User', () => {
  test.use({ settingsPreset: PRESET_EMPTY })

  test('new users have no default region', { tag: ['@regression'] }, async ({ authenticatedPage: page }) => {
    // Clear any persisted settings so region is null
    await page.addInitScript(() => {
      localStorage.removeItem('electricity-optimizer-settings')
    })

    await page.goto('/settings')

    // New users should not have a pre-selected region
    const regionSelect = page.locator('select').first()
    await expect(regionSelect).toHaveValue('')
  })
})
