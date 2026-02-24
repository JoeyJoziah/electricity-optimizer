import { test, expect } from '@playwright/test'
import { mockBetterAuth, setAuthenticatedState } from './helpers/auth'

/**
 * Load Optimization E2E Tests
 *
 * Tests the appliance scheduling and load optimization wizard.
 * Features not yet implemented:
 * - Appliance management (add/edit/remove)
 * - Optimization engine integration
 * - Schedule timeline visualization
 * - Recurring schedules
 * - Smart notifications
 *
 * Tracked in GitHub Project #4 — unskip as features are built.
 */
test.describe('Load Optimization Flow', () => {
  // Skip entire suite — optimization wizard UI not yet implemented
  test.skip()

  test.beforeEach(async ({ page }) => {
    await mockBetterAuth(page)
    await setAuthenticatedState(page)

    await page.route('**/api/v1/optimization/schedule', async (route) => {
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({
          schedules: [
            {
              applianceId: 'dishwasher_1',
              applianceName: 'Dishwasher',
              scheduledStart: '2024-01-16T02:00:00Z',
              scheduledEnd: '2024-01-16T04:00:00Z',
              estimatedCost: 0.30,
              savings: 0.15,
              reason: 'Lowest overnight rate',
            },
          ],
          totalSavings: 0.15,
          totalCost: 0.30,
        }),
      })
    })
  })

  test('navigates to optimization page', async ({ page }) => {
    await page.goto('/optimize')
    await expect(page.getByText(/optimi/i)).toBeVisible()
  })

  test('runs optimization and shows results', async ({ page }) => {
    await page.goto('/optimize')
    await page.click('button:has-text("Optimize")')
    await expect(page.getByText('Dishwasher')).toBeVisible()
  })

  test('shows schedule details', async ({ page }) => {
    await page.goto('/optimize')
    await page.click('button:has-text("Optimize")')
    await expect(page.getByText(/savings/i)).toBeVisible()
  })
})
