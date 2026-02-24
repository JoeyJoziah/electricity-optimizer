import { test, expect } from '@playwright/test'
import { mockBetterAuth, setAuthenticatedState } from './helpers/auth'

test.describe('Prices Page', () => {
  test.beforeEach(async ({ page }) => {
    await mockBetterAuth(page)
    await setAuthenticatedState(page)

    // Mock price endpoints
    await page.route('**/api/v1/prices/current**', async (route) => {
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({
          prices: [
            {
              region: 'US_CT',
              price: 0.2512,
              timestamp: new Date().toISOString(),
              trend: 'decreasing',
              changePercent: -1.8,
            },
          ],
        }),
      })
    })

    await page.route('**/api/v1/prices/history**', async (route) => {
      const now = Date.now()
      const prices = Array.from({ length: 24 }, (_, i) => ({
        time: new Date(now - (23 - i) * 3600000).toISOString(),
        price: 0.22 + Math.sin(i / 4) * 0.05,
      }))
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({ prices }),
      })
    })

    await page.route('**/api/v1/prices/forecast**', async (route) => {
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({
          forecast: [
            { hour: 1, price: 0.23, confidence: [0.21, 0.25] },
            { hour: 2, price: 0.21, confidence: [0.19, 0.23] },
            { hour: 3, price: 0.19, confidence: [0.17, 0.21] },
            { hour: 4, price: 0.20, confidence: [0.18, 0.22] },
          ],
        }),
      })
    })

    await page.route('**/api/v1/prices/optimal-periods**', async (route) => {
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({
          periods: [
            {
              start: new Date(Date.now() + 3600000).toISOString(),
              end: new Date(Date.now() + 7200000).toISOString(),
              avgPrice: 0.18,
            },
          ],
        }),
      })
    })

    // Mock user endpoint
    await page.route('**/api/v1/user/me', async (route) => {
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({
          id: 'user_e2e_123',
          email: 'test@example.com',
          name: 'Test User',
          region: 'us_ct',
        }),
      })
    })
  })

  test('displays prices page', async ({ page }) => {
    await page.goto('/prices')
    await expect(page).toHaveURL(/\/prices/)
  })

  test('shows current price data', async ({ page }) => {
    await page.goto('/prices')

    // Should show price information
    await expect(page.getByText(/\$0\.25/)).toBeVisible({ timeout: 5000 })
  })

  test('shows time range selector', async ({ page }) => {
    await page.goto('/prices')

    // Time range buttons
    await expect(page.getByRole('button', { name: '24h' })).toBeVisible()
  })

  test('switches time range', async ({ page }) => {
    await page.goto('/prices')

    const btn7d = page.getByRole('button', { name: '7d' })
    if (await btn7d.isVisible()) {
      await btn7d.click()
      // Should update without error
      await page.waitForTimeout(500)
    }
  })

  test('renders chart area', async ({ page }) => {
    await page.goto('/prices')

    // Chart container or skeleton should be visible
    const chartArea = page.locator('[class*="chart"], [class*="Chart"], [role="img"], svg')
    // Either chart renders or skeleton is shown
    await expect(chartArea.first().or(page.getByText(/loading/i))).toBeVisible({
      timeout: 5000,
    })
  })
})
