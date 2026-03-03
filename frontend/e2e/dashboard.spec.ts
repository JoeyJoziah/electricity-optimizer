import { test, expect } from '@playwright/test'
import { mockBetterAuth, setAuthenticatedState } from './helpers/auth'

test.describe('Dashboard', () => {
  test.beforeEach(async ({ page }) => {
    await mockBetterAuth(page)
    await setAuthenticatedState(page)

    // Initialize settings store with region so hooks fire (enabled: !!region)
    await page.addInitScript(() => {
      localStorage.setItem(
        'electricity-optimizer-settings',
        JSON.stringify({
          state: {
            region: 'US_CT',
            annualUsageKwh: 10500,
            peakDemandKw: 5,
            displayPreferences: {
              currency: 'USD',
              theme: 'system',
              timeFormat: '12h',
            },
          },
        })
      )
    })

    // Mock API responses
    await page.route('**/api/v1/prices/current**', async (route) => {
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({
          prices: [
            {
              region: 'US_CT',
              price: 0.25,
              timestamp: new Date().toISOString(),
              trend: 'decreasing',
              changePercent: -2.5,
            },
          ],
        }),
      })
    })

    await page.route('**/api/v1/prices/history**', async (route) => {
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({
          prices: [
            { time: new Date(Date.now() - 3600000).toISOString(), price: 0.28 },
            { time: new Date(Date.now() - 1800000).toISOString(), price: 0.26 },
            { time: new Date().toISOString(), price: 0.25 },
          ],
        }),
      })
    })

    await page.route('**/api/v1/prices/forecast**', async (route) => {
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({
          forecast: [
            { hour: 1, price: 0.23, confidence: [0.21, 0.25] },
            { hour: 2, price: 0.20, confidence: [0.18, 0.22] },
            { hour: 3, price: 0.18, confidence: [0.16, 0.20] },
          ],
        }),
      })
    })

    await page.route('**/api/v1/suppliers**', async (route) => {
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({
          suppliers: [
            {
              id: '1',
              name: 'Eversource Energy',
              avgPricePerKwh: 0.25,
              standingCharge: 0.50,
              greenEnergy: true,
              rating: 4.5,
              estimatedAnnualCost: 1200,
              tariffType: 'variable',
            },
            {
              id: '2',
              name: 'NextEra Energy',
              avgPricePerKwh: 0.22,
              standingCharge: 0.45,
              greenEnergy: true,
              rating: 4.3,
              estimatedAnnualCost: 1050,
              tariffType: 'variable',
            },
          ],
        }),
      })
    })

    // Mock additional endpoints needed when navigating away from dashboard
    await page.route('**/api/v1/users/profile**', async (route) => {
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({
          email: 'test@example.com',
          name: 'Test User',
          region: 'US_CT',
          utility_types: ['electricity'],
          current_supplier_id: null,
          annual_usage_kwh: 10500,
          onboarding_completed: true,
        }),
      })
    })

    await page.route('**/api/v1/user/supplier', async (route) => {
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({ supplier: null }),
      })
    })

    await page.route('**/api/v1/savings/summary**', async (route) => {
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({ monthly: 0, weekly: 0, streak_days: 0 }),
      })
    })

    await page.route('**/api/v1/prices/optimal-periods**', async (route) => {
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({ periods: [] }),
      })
    })

    await page.route('**/api/v1/suppliers/recommendation**', async (route) => {
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({ recommendation: null }),
      })
    })

    await page.goto('/dashboard')
  })

  test('displays dashboard with all main widgets', async ({ page }) => {
    // Dashboard title
    await expect(page.getByRole('heading', { name: 'Dashboard' })).toBeVisible()

    // Current price widget
    await expect(page.getByText('Current Price').first()).toBeVisible()
    await expect(page.getByTestId('current-price').first()).toBeVisible()

    // Total saved widget
    await expect(page.getByText('Total Saved')).toBeVisible()

    // Optimal times widget
    await expect(page.getByText('Optimal Times')).toBeVisible()

    // Suppliers widget
    await expect(page.getByRole('heading', { name: 'Top Suppliers' })).toBeVisible()
  })

  test('shows live prices and trend', async ({ page }) => {
    // Current price should be displayed
    await expect(page.getByTestId('current-price').first()).toContainText('0.25')

    // Price trend should show decreasing
    await expect(page.getByTestId('price-trend').first()).toBeVisible()
  })

  test('displays price chart with history', async ({ page }) => {
    // Wait for chart to load
    await expect(page.getByText('Price History')).toBeVisible()

    // Chart container should exist
    await expect(page.getByTestId('price-chart-container')).toBeVisible()
  })

  test('shows 24-hour forecast section', async ({ page }) => {
    await expect(page.getByText('24-Hour Forecast').first()).toBeVisible()
  })

  test('displays supplier comparison widget', async ({ page }) => {
    await expect(page.getByText('Top Suppliers')).toBeVisible()
    await expect(page.getByRole('heading', { name: 'Eversource Energy' })).toBeVisible()
  })

  test('navigates to prices page', async ({ page, isMobile }) => {
    test.skip(isMobile === true, 'Mobile navigation uses different layout')
    await page.getByText('View all prices').click()
    await page.waitForURL(/\/prices/, { timeout: 15000 })
  })

  // Client-side navigation from dashboard to suppliers can be slow on webkit
  test('navigates to suppliers page', async ({ page, isMobile }) => {
    test.skip(isMobile === true, 'Mobile navigation uses different layout')
    await page.getByRole('link', { name: 'View all', exact: true }).click()
    await page.waitForURL(/\/suppliers/, { timeout: 20000 })
  })

  // Realtime indicator has class "hidden sm:flex" — not visible on mobile viewports
  test('shows realtime indicator', async ({ page, isMobile }) => {
    test.skip(isMobile === true, 'Realtime indicator is hidden on mobile (sm:flex)')
    await expect(page.getByTestId('realtime-indicator')).toBeVisible()
  })

  test('is responsive on mobile', async ({ page }) => {
    await page.setViewportSize({ width: 375, height: 667 })

    // Dashboard should still load
    await expect(page.getByText('Current Price').first()).toBeVisible()

    // Sidebar should be hidden on mobile
    await expect(page.getByRole('navigation')).not.toBeVisible()
  })
})

test.describe('Dashboard Error Handling', () => {
  test('handles API errors gracefully', async ({ page }) => {
    await mockBetterAuth(page)
    await setAuthenticatedState(page)

    await page.route('**/api/v1/prices/current**', async (route) => {
      await route.fulfill({
        status: 500,
        contentType: 'application/json',
        body: JSON.stringify({ detail: 'Internal server error' }),
      })
    })

    await page.goto('/dashboard')

    // Dashboard should still render even with API errors
    await expect(page.getByRole('heading', { name: 'Dashboard' })).toBeVisible()
  })
})
