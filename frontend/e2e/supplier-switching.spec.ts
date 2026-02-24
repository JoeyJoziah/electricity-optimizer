import { test, expect } from '@playwright/test'
import { mockBetterAuth, setAuthenticatedState } from './helpers/auth'

/**
 * Supplier Switching E2E Tests
 *
 * Tests the full supplier switching wizard flow:
 * - Supplier comparison (grid/table views)
 * - Savings calculation
 * - GDPR consent step
 * - Switch confirmation and status tracking
 * - Exit fee warnings
 * - Cooling off period info
 *
 * Tracked in GitHub Project #4 — unskip as features are built.
 */
test.describe('Full Supplier Switching Flow', () => {
  // Skip entire suite — switching wizard UI not yet fully implemented
  test.skip()

  test.beforeEach(async ({ page }) => {
    await mockBetterAuth(page)
    await setAuthenticatedState(page)

    await page.route('**/api/v1/suppliers**', async (route) => {
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({
          suppliers: [
            {
              id: 'eversource',
              name: 'Eversource Energy',
              avgPricePerKwh: 0.26,
              greenEnergy: false,
              rating: 3.5,
              tariffType: 'variable',
            },
            {
              id: 'nextera',
              name: 'NextEra Energy',
              avgPricePerKwh: 0.22,
              greenEnergy: true,
              rating: 4.2,
              tariffType: 'fixed',
            },
          ],
          total: 2,
        }),
      })
    })
  })

  test('displays supplier list', async ({ page }) => {
    await page.goto('/suppliers')
    await expect(page.getByText('Eversource Energy')).toBeVisible()
    await expect(page.getByText('NextEra Energy')).toBeVisible()
  })

  test('can initiate supplier switch', async ({ page }) => {
    await page.goto('/suppliers')
    await page.click('text=NextEra Energy')
    await expect(page.getByText(/switch/i)).toBeVisible()
  })
})
