import { test, expect } from '@playwright/test'
import { mockBetterAuth, setAuthenticatedState } from './helpers/auth'

/**
 * User Onboarding E2E Tests
 *
 * Tests the multi-step onboarding wizard:
 * - Signup form with validation
 * - Password requirements
 * - Terms acceptance
 * - Region/supplier selection
 * - Usage input
 * - Progress indicator and back navigation
 *
 * Tracked in GitHub Project #4 — unskip as features are built.
 */
test.describe('User Onboarding Flow', () => {
  // Skip entire suite — onboarding wizard not yet implemented
  test.skip()

  test.beforeEach(async ({ page }) => {
    await mockBetterAuth(page)

    await page.route('**/api/v1/prices/current**', async (route) => {
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({
          prices: [{ region: 'US_CT', price: 0.25, timestamp: new Date().toISOString() }],
        }),
      })
    })
  })

  test('landing page shows signup call to action', async ({ page }) => {
    await page.goto('/')
    await expect(page.getByRole('link', { name: /sign up|get started/i })).toBeVisible()
  })

  test('new user can complete signup form', async ({ page }) => {
    await page.goto('/auth/signup')
    await page.fill('#name', 'New User')
    await page.fill('#email', 'new@example.com')
    await page.fill('#password', 'SecurePass123!')
    await page.click('button[type="submit"]')
    await page.waitForURL(/\/(dashboard|onboarding)/)
  })
})
