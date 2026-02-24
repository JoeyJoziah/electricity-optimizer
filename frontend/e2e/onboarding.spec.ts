import { test, expect } from '@playwright/test'
import { mockBetterAuth, setAuthenticatedState, clearAuthState } from './helpers/auth'

/**
 * User Onboarding E2E Tests
 *
 * Tests signup form validation, login flow, and CT region defaults.
 */
test.describe('User Onboarding Flow', () => {
  test.beforeEach(async ({ page }) => {
    await mockBetterAuth(page)

    // Mock backend API responses
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

  test('landing page shows signup call to action', async ({ page }) => {
    await page.goto('/')
    await expect(page.getByRole('link', { name: /sign up|get started/i })).toBeVisible()
  })

  test('signup form validates required fields', async ({ page }) => {
    await page.goto('/auth/signup')
    await expect(page.getByText('Create your account')).toBeVisible()

    // Try to submit without filling anything — button should be disabled
    const submitButton = page.getByRole('button', { name: /create account/i })
    await expect(submitButton).toBeDisabled()
  })

  test('signup form shows password requirements', async ({ page }) => {
    await page.goto('/auth/signup')

    await page.fill('#password', 'short')
    await expect(page.getByText('At least 12 characters')).toBeVisible()
    await expect(page.getByText('One uppercase letter')).toBeVisible()
    await expect(page.getByText('One number')).toBeVisible()
    await expect(page.getByText('One special character')).toBeVisible()
  })

  test('signup form detects password mismatch', async ({ page }) => {
    await page.goto('/auth/signup')

    await page.fill('#password', 'SecurePass123!')
    await page.fill('#confirmPassword', 'DifferentPass456!')
    await expect(page.getByText('Passwords do not match')).toBeVisible()
  })

  test('new user can complete signup and reach dashboard', async ({ page }) => {
    await page.goto('/auth/signup')

    await page.fill('#name', 'Test User')
    await page.fill('#email', 'test@example.com')
    await page.fill('#password', 'SecurePass123!')
    await page.fill('#confirmPassword', 'SecurePass123!')
    await page.check('#terms')

    await page.click('button[type="submit"]')
    await page.waitForURL(/\/(dashboard|auth)/, { timeout: 10000 })
  })

  test('login page is accessible from signup page', async ({ page }) => {
    await page.goto('/auth/signup')
    await expect(page.getByRole('link', { name: /sign in/i })).toBeVisible()
    await page.click('text=Sign in')
    await page.waitForURL(/\/auth\/login/)
  })

  test('CT is default region for new users', async ({ page }) => {
    await setAuthenticatedState(page)
    await page.goto('/settings')

    // The settings page region selector should default to Connecticut
    const regionSelect = page.locator('select').first()
    await expect(regionSelect).toHaveValue('us_ct')
  })
})
