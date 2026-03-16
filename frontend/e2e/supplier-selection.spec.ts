import { test, expect } from './fixtures'

/**
 * Supplier Selection E2E Tests
 *
 * Tests supplier browsing, selection, and the "next step" connection prompt.
 *
 * Note: The profile endpoint in this spec handles both GET and PUT with
 * different responses, so it is registered as an inline route mock that
 * overrides the shared factory's userProfile mock.
 */
test.describe('Supplier Selection Flow', () => {
  // authenticatedPage sets up auth, PRESET_FREE settings, and standard API mocks.
  // We register additional overrides that the shared factory doesn't cover:
  //   - per-method profile handling (GET returns a specific profile; PUT echoes body)
  //   - per-method user/supplier handling (GET = null; POST = supplier_id)
  //   - suppliers/recommendation (returns null recommendation)
  //   - two specific supplier records with ids sup_1 / sup_2

  test('suppliers page shows available suppliers', { tag: ['@smoke'] }, async ({ authenticatedPage: page }) => {
    // Override profile to return onboarded user with region us_ct
    await page.route('**/api/v1/users/profile**', async (route, request) => {
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

    await page.route('**/api/v1/suppliers/recommendation**', async (route) => {
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({ recommendation: null }),
      })
    })

    await page.goto('/suppliers')

    await expect(page.getByText('Compare Suppliers')).toBeVisible()
    // Use .first() because supplier names appear in both the stats row
    // (e.g., "Cheapest Option: Eversource Energy") and in the supplier card grid
    await expect(page.getByText('Eversource Energy').first()).toBeVisible()
    await expect(page.getByText('NextEra Energy').first()).toBeVisible()
  })

  test('shows "not set" when no supplier selected', { tag: ['@regression'] }, async ({ authenticatedPage: page }) => {
    await page.route('**/api/v1/users/profile**', async (route, request) => {
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

    await page.route('**/api/v1/suppliers/recommendation**', async (route) => {
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({ recommendation: null }),
      })
    })

    await page.goto('/suppliers')

    await expect(page.getByText('Not set')).toBeVisible()
    await expect(page.getByText('Select Supplier')).toBeVisible()
  })

  test('dashboard shows setup checklist for new users', { tag: ['@smoke'] }, async ({ authenticatedPage: page }) => {
    await page.route('**/api/v1/users/profile**', async (route, request) => {
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

    await page.route('**/api/v1/suppliers/recommendation**', async (route) => {
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({ recommendation: null }),
      })
    })

    await page.goto('/dashboard')

    // Checklist should be visible
    await expect(page.getByText('Complete your setup for personalized savings')).toBeVisible()
    await expect(page.getByText('Choose your energy supplier')).toBeVisible()
    await expect(page.getByText('Browse Suppliers')).toBeVisible()
  })

  test('setup checklist can be dismissed', { tag: ['@regression'] }, async ({ authenticatedPage: page }) => {
    await page.route('**/api/v1/users/profile**', async (route, request) => {
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

    await page.route('**/api/v1/suppliers/recommendation**', async (route) => {
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({ recommendation: null }),
      })
    })

    await page.goto('/dashboard')

    await expect(page.getByText('Complete your setup for personalized savings')).toBeVisible()

    await page.click('[aria-label="Dismiss setup checklist"]')

    await expect(page.getByText('Complete your setup for personalized savings')).not.toBeVisible()
  })
})
