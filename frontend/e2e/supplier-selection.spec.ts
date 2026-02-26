import { test, expect } from '@playwright/test'
import { mockBetterAuth, setAuthenticatedState } from './helpers/auth'

/**
 * Supplier Selection E2E Tests
 *
 * Tests supplier browsing, selection, and the "next step" connection prompt.
 */
test.describe('Supplier Selection Flow', () => {
  test.beforeEach(async ({ page }) => {
    await mockBetterAuth(page)

    // Mock profile — onboarded user with region
    await page.route('**/api/v1/users/profile', async (route, request) => {
      if (request.method() === 'GET') {
        await route.fulfill({
          status: 200,
          contentType: 'application/json',
          body: JSON.stringify({
            email: 'test@example.com',
            name: 'Test User',
            region: 'us_ct',
            utility_types: ['electricity'],
            current_supplier_id: null,
            annual_usage_kwh: 10500,
            onboarding_completed: true,
          }),
        })
      } else {
        await route.fulfill({ status: 200, contentType: 'application/json', body: '{}' })
      }
    })

    await page.route('**/api/v1/suppliers**', async (route) => {
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({
          suppliers: [
            {
              id: 'sup_1',
              name: 'Eversource Energy',
              avgPricePerKwh: 0.26,
              standingCharge: 0.50,
              greenEnergy: false,
              rating: 3.5,
              estimatedAnnualCost: 1300,
              tariffType: 'variable',
            },
            {
              id: 'sup_2',
              name: 'NextEra Energy',
              avgPricePerKwh: 0.22,
              standingCharge: 0.40,
              greenEnergy: true,
              rating: 4.0,
              estimatedAnnualCost: 1100,
              tariffType: 'variable',
            },
          ],
          total: 2,
        }),
      })
    })

    await page.route('**/api/v1/user/supplier', async (route, request) => {
      if (request.method() === 'GET') {
        await route.fulfill({
          status: 200,
          contentType: 'application/json',
          body: JSON.stringify({ supplier: null }),
        })
      } else {
        await route.fulfill({
          status: 200,
          contentType: 'application/json',
          body: JSON.stringify({ supplier_id: 'sup_1' }),
        })
      }
    })

    await page.route('**/api/v1/prices/current**', async (route) => {
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({ prices: [] }),
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

    await page.route('**/api/v1/savings/summary**', async (route) => {
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({ monthly: 0, weekly: 0, streak_days: 0 }),
      })
    })

    await page.route('**/api/v1/suppliers/recommendation**', async (route) => {
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({ recommendation: null }),
      })
    })
  })

  test('suppliers page shows available suppliers', async ({ page }) => {
    await setAuthenticatedState(page)
    await page.goto('/suppliers')

    await expect(page.getByText('Compare Suppliers')).toBeVisible()
    await expect(page.getByText('Eversource Energy')).toBeVisible()
    await expect(page.getByText('NextEra Energy')).toBeVisible()
  })

  test('shows "not set" when no supplier selected', async ({ page }) => {
    await setAuthenticatedState(page)
    await page.goto('/suppliers')

    await expect(page.getByText('Not set')).toBeVisible()
    await expect(page.getByText('Select Supplier')).toBeVisible()
  })

  test('dashboard shows setup checklist for new users', async ({ page }) => {
    await setAuthenticatedState(page)
    await page.goto('/dashboard')

    // Checklist should be visible
    await expect(page.getByText('Complete your setup for personalized savings')).toBeVisible()
    await expect(page.getByText('Choose your energy supplier')).toBeVisible()
    await expect(page.getByText('Browse Suppliers')).toBeVisible()
  })

  test('setup checklist can be dismissed', async ({ page }) => {
    await setAuthenticatedState(page)
    await page.goto('/dashboard')

    await expect(page.getByText('Complete your setup for personalized savings')).toBeVisible()

    await page.click('[aria-label="Dismiss setup checklist"]')

    await expect(page.getByText('Complete your setup for personalized savings')).not.toBeVisible()
  })
})
