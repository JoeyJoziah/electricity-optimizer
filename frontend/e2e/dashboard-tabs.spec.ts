import { test, expect } from '@playwright/test'
import { mockBetterAuth, setAuthenticatedState } from './helpers/auth'

test.describe('Dashboard Tabs', () => {
  test.beforeEach(async ({ page }) => {
    await mockBetterAuth(page)
    await setAuthenticatedState(page)

    // Set up multi-utility user (electricity + natural_gas) so tabs appear
    await page.addInitScript(() => {
      localStorage.setItem(
        'electricity-optimizer-settings',
        JSON.stringify({
          state: {
            region: 'US_CT',
            annualUsageKwh: 10500,
            peakDemandKw: 5,
            utilityTypes: ['electricity', 'natural_gas'],
            displayPreferences: {
              currency: 'USD',
              theme: 'system',
              timeFormat: '12h',
            },
          },
        })
      )
    })

    // Mock common API endpoints
    await page.route('**/api/v1/prices/current**', async (route) => {
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({ prices: [{ region: 'US_CT', price: 0.25, timestamp: new Date().toISOString(), trend: 'stable', changePercent: 0 }] }),
      })
    })

    await page.route('**/api/v1/**', async (route) => {
      // Catch-all for any other API calls
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({}),
      })
    })

    await page.route('**/api/auth/get-session', async (route) => {
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({
          user: { id: 'user_e2e_123', email: 'test@example.com', name: 'Test User', emailVerified: true },
          session: { id: 'session_e2e_123', userId: 'user_e2e_123', token: 'mock-session-token-e2e-test', expiresAt: new Date(Date.now() + 86400000).toISOString() },
        }),
      })
    })
  })

  test('All Utilities tab is active by default for multi-utility user', async ({ page }) => {
    await page.goto('/dashboard')
    await expect(page.getByTestId('dashboard-tabs')).toBeVisible()

    const allTab = page.getByTestId('tab-all')
    await expect(allTab).toBeVisible()
    await expect(allTab).toHaveAttribute('aria-selected', 'true')
  })

  test('clicking Electricity tab updates URL and content', async ({ page }) => {
    await page.goto('/dashboard')
    await expect(page.getByTestId('dashboard-tabs')).toBeVisible()

    const electricityTab = page.getByTestId('tab-electricity')
    await expect(electricityTab).toBeVisible()
    await electricityTab.click()

    // URL should update with tab param
    await expect(page).toHaveURL(/tab=electricity/)

    // Electricity tab should now be selected
    await expect(electricityTab).toHaveAttribute('aria-selected', 'true')

    // All tab should no longer be selected
    await expect(page.getByTestId('tab-all')).toHaveAttribute('aria-selected', 'false')
  })

  test('direct navigation to tab via URL param', async ({ page }) => {
    await page.goto('/dashboard?tab=natural_gas')
    await expect(page.getByTestId('dashboard-tabs')).toBeVisible()

    const gasTab = page.getByTestId('tab-natural_gas')
    await expect(gasTab).toHaveAttribute('aria-selected', 'true')

    // All tab should not be selected
    await expect(page.getByTestId('tab-all')).toHaveAttribute('aria-selected', 'false')
  })
})
