/**
 * Missing Pages E2E Tests
 *
 * Covers app pages that don't have dedicated spec files:
 * - /analytics (protected) — Premium analytics dashboard
 * - /beta-signup (protected) — Beta signup form
 * - /rates/[state]/[utility] (public) — ISR SEO rate pages
 * - /auth/callback (public) — OAuth callback handler
 * - /connections (protected) — Utility connections management
 * - /alerts (protected) — Price alert management
 * - /assistant (protected) — AI agent chat
 */

import { test, expect, PRESET_PRO } from './fixtures'
import { mockBetterAuth } from './helpers/auth'
import { createMockApi } from './helpers/api-mocks'

// ---------------------------------------------------------------------------
// Analytics Page (/analytics) — Protected
// ---------------------------------------------------------------------------

test.describe('Analytics Page', { tag: ['@regression'] }, () => {
  test('loads analytics page with heading visible', async ({ authenticatedPage: page }) => {
    await page.goto('/analytics', { waitUntil: 'domcontentloaded' })

    await expect(
      page.getByRole('heading', { name: /premium analytics/i })
    ).toBeVisible()
  })

  test('shows state selector for chart area', async ({ authenticatedPage: page }) => {
    await page.goto('/analytics', { waitUntil: 'domcontentloaded' })

    // The AnalyticsDashboard renders a state selector dropdown
    await expect(page.locator('#state-select')).toBeVisible()
  })

  test('displays forecast and optimization sections', async ({ authenticatedPage: page }) => {
    await page.goto('/analytics', { waitUntil: 'domcontentloaded' })

    // The dashboard description mentions these capabilities
    await expect(
      page.getByText(/rate forecasts|spend optimization|data export/i).first()
    ).toBeVisible()
  })
})

// ---------------------------------------------------------------------------
// Beta Signup Page (/beta-signup) — Protected
// ---------------------------------------------------------------------------

test.describe('Beta Signup Page', { tag: ['@regression'] }, () => {
  test('loads beta signup form with heading', async ({ authenticatedPage: page }) => {
    await page.goto('/beta-signup', { waitUntil: 'domcontentloaded' })

    await expect(
      page.getByRole('heading', { name: /sign up free/i })
    ).toBeVisible()
  })

  test('shows required form fields', async ({ authenticatedPage: page }) => {
    await page.goto('/beta-signup', { waitUntil: 'domcontentloaded' })

    // Email and name inputs
    await expect(page.locator('#email')).toBeVisible()
    await expect(page.locator('#name')).toBeVisible()

    // ZIP code input
    await expect(page.locator('#postcode')).toBeVisible()

    // Supplier and monthly bill selects
    await expect(page.locator('#currentSupplier')).toBeVisible()
    await expect(page.locator('#monthlyBill')).toBeVisible()
  })

  test('shows submission button', async ({ authenticatedPage: page }) => {
    await page.goto('/beta-signup', { waitUntil: 'domcontentloaded' })

    await expect(
      page.getByRole('button', { name: /sign up free/i })
    ).toBeVisible()
  })

  test('shows how did you hear about us field', async ({ authenticatedPage: page }) => {
    await page.goto('/beta-signup', { waitUntil: 'domcontentloaded' })

    await expect(page.locator('#hearAbout')).toBeVisible()
    await expect(page.getByText(/how did you hear about us/i)).toBeVisible()
  })
})

// ---------------------------------------------------------------------------
// ISR Rate Pages (/rates/[state]/[utility]) — Public, SSR
// ---------------------------------------------------------------------------

test.describe('ISR Rate Pages', { tag: ['@smoke'] }, () => {
  test('loads Connecticut electricity rate page', async ({ page }) => {
    await mockBetterAuth(page)
    await createMockApi(page)

    // Mock the public rates endpoint that the server-side fetches
    await page.route('**/api/v1/public/rates/**', async (route) => {
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({
          state: 'US_CT',
          utility_type: 'electricity',
          unit: 'kWh',
          average_price: 0.2534,
          suppliers: [
            {
              supplier: 'Eversource Energy',
              price: 0.2534,
              rate_type: 'variable',
              source: 'public_data',
              updated_at: new Date().toISOString(),
            },
          ],
          count: 1,
        }),
      })
    })

    await page.goto('/rates/connecticut/electricity', { waitUntil: 'domcontentloaded' })

    // Heading should contain state name and utility type
    await expect(
      page.getByRole('heading', { name: /electricity rates in connecticut/i })
    ).toBeVisible()
  })

  test('loads California electricity rate page', async ({ page }) => {
    await mockBetterAuth(page)
    await createMockApi(page)

    await page.route('**/api/v1/public/rates/**', async (route) => {
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({
          state: 'US_CA',
          utility_type: 'electricity',
          unit: 'kWh',
          average_price: 0.3012,
          suppliers: [
            {
              supplier: 'Pacific Gas & Electric',
              price: 0.3012,
              rate_type: 'variable',
              source: 'public_data',
              updated_at: new Date().toISOString(),
            },
          ],
          count: 1,
        }),
      })
    })

    await page.goto('/rates/california/electricity', { waitUntil: 'domcontentloaded' })

    await expect(
      page.getByRole('heading', { name: /electricity rates in california/i })
    ).toBeVisible()
  })

  test('loads Texas electricity rate page', async ({ page }) => {
    await mockBetterAuth(page)
    await createMockApi(page)

    await page.route('**/api/v1/public/rates/**', async (route) => {
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({
          state: 'US_TX',
          utility_type: 'electricity',
          unit: 'kWh',
          average_price: 0.1287,
          suppliers: [],
          count: 0,
        }),
      })
    })

    await page.goto('/rates/texas/electricity', { waitUntil: 'domcontentloaded' })

    await expect(
      page.getByRole('heading', { name: /electricity rates in texas/i })
    ).toBeVisible()
  })

  test('shows state name and utility type in page content', async ({ page }) => {
    await mockBetterAuth(page)
    await createMockApi(page)

    await page.route('**/api/v1/public/rates/**', async (route) => {
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({
          state: 'US_CT',
          utility_type: 'electricity',
          unit: 'kWh',
          average_price: null,
          suppliers: [],
          count: 0,
        }),
      })
    })

    await page.goto('/rates/connecticut/electricity', { waitUntil: 'domcontentloaded' })

    // Breadcrumb should show state name
    await expect(page.getByText('Connecticut').first()).toBeVisible()

    // Page description mentions comparing rates
    await expect(
      page.getByText(/compare current electricity rates/i).first()
    ).toBeVisible()
  })

  test('invalid state returns 404 or error', async ({ page }) => {
    await mockBetterAuth(page)
    await createMockApi(page)

    const response = await page.goto('/rates/nonexistent-state/electricity', {
      waitUntil: 'domcontentloaded',
    })

    // Should either show 404 page or an error message
    const is404 = response?.status() === 404
    const hasNotFound = await page
      .getByText(/not found|404|page doesn.t exist/i)
      .isVisible()
      .catch(() => false)

    expect(is404 || hasNotFound).toBeTruthy()
  })
})

// ---------------------------------------------------------------------------
// OAuth Callback Page (/auth/callback) — Public
// ---------------------------------------------------------------------------

test.describe('OAuth Callback Page', { tag: ['@regression'] }, () => {
  test('shows loading state when landing on callback page', async ({ page }) => {
    await mockBetterAuth(page)
    await createMockApi(page)

    // Intercept the dashboard redirect so we can observe the loading state
    await page.route('**/dashboard', async (route) => {
      // Delay the navigation to allow observing the spinner
      await new Promise((resolve) => setTimeout(resolve, 2000))
      await route.continue()
    })

    await page.goto('/auth/callback', { waitUntil: 'domcontentloaded' })

    // The page shows a spinner with role="status" and aria-label
    const spinner = page.locator('[role="status"][aria-label="Completing authentication"]')
    const spinnerVisible = await spinner.isVisible().catch(() => false)

    // Either the spinner is visible or we already redirected to dashboard
    const onDashboard = page.url().includes('/dashboard')
    expect(spinnerVisible || onDashboard).toBeTruthy()
  })

  test('shows fallback link after timeout or redirects', async ({ page }) => {
    await mockBetterAuth(page)
    await createMockApi(page)

    // Block dashboard navigation so the fallback timer can fire
    await page.route('**/dashboard**', async (route) => {
      // Never fulfill — simulates a stuck redirect
      await new Promise(() => {})
    })

    await page.goto('/auth/callback', { waitUntil: 'domcontentloaded' })

    // Wait for the 5-second fallback timer
    await expect(page.getByText(/taking longer than expected/i)).toBeVisible({
      timeout: 8000,
    })

    // Manual link to dashboard should appear
    await expect(page.getByRole('link', { name: /go to dashboard/i })).toBeVisible()
  })
})

// ---------------------------------------------------------------------------
// Connections Page (/connections) — Protected
// ---------------------------------------------------------------------------

test.describe('Connections Page', { tag: ['@regression'] }, () => {
  test('loads connections page with heading', async ({ authenticatedPage: page }) => {
    await page.goto('/connections', { waitUntil: 'domcontentloaded' })

    await expect(
      page.getByRole('heading', { name: /connections/i }).first()
    ).toBeVisible()
  })

  test('shows connection method picker when no connections exist', async ({
    authenticatedPage: page,
  }) => {
    await page.goto('/connections', { waitUntil: 'domcontentloaded' })

    // Empty state shows "Get Started" heading with connection method picker
    await expect(
      page.getByRole('heading', { name: /get started/i })
    ).toBeVisible()
  })

  test('shows tab navigation', async ({ authenticatedPage: page }) => {
    await page.goto('/connections', { waitUntil: 'domcontentloaded' })

    // Tab navigation with Connections and Analytics tabs
    await expect(page.getByRole('tab', { name: /connections/i })).toBeVisible()
    await expect(page.getByRole('tab', { name: /analytics/i })).toBeVisible()
  })
})

// ---------------------------------------------------------------------------
// Alerts Page (/alerts) — Protected
// ---------------------------------------------------------------------------

test.describe('Alerts Page — Empty State', { tag: ['@smoke'] }, () => {
  test('loads alerts page', async ({ authenticatedPage: page }) => {
    await page.goto('/alerts', { waitUntil: 'domcontentloaded' })

    // Page should load without crashing
    await expect(page).toHaveURL(/\/alerts/)
  })

  test('shows Add Alert button', async ({ authenticatedPage: page }) => {
    await page.goto('/alerts', { waitUntil: 'domcontentloaded' })

    await expect(
      page.getByRole('button', { name: /add alert/i })
    ).toBeVisible()
  })

  test('shows empty state when no alerts configured', async ({
    authenticatedPage: page,
  }) => {
    await page.goto('/alerts', { waitUntil: 'domcontentloaded' })

    // Empty state message
    await expect(page.getByText(/no alerts configured yet/i)).toBeVisible()
    await expect(
      page.getByText(/create your first alert/i)
    ).toBeVisible()
  })
})

test.describe('Alerts Page — With Data', { tag: ['@smoke'] }, () => {
  test.use({
    apiMockConfig: {
      alerts: {
        alerts: [
          {
            id: 'alert-1',
            region: 'US_CT',
            alert_type: 'price_drop',
            price_below: 0.2,
            price_above: null,
            notify_optimal_windows: false,
            is_active: true,
            created_at: new Date().toISOString(),
            last_triggered_at: null,
          },
          {
            id: 'alert-2',
            region: 'US_CA',
            alert_type: 'price_spike',
            price_below: null,
            price_above: 0.35,
            notify_optimal_windows: false,
            is_active: false,
            created_at: new Date().toISOString(),
            last_triggered_at: null,
          },
        ],
      },
    },
  })

  test('shows alert list when alerts exist', async ({ authenticatedPage: page }) => {
    await page.goto('/alerts', { waitUntil: 'domcontentloaded' })

    // Alert cards should be visible
    const alertCards = page.locator('[data-testid="alert-card"]')
    await expect(alertCards).toHaveCount(2)
  })

  test('shows active and paused status badges', async ({ authenticatedPage: page }) => {
    await page.goto('/alerts', { waitUntil: 'domcontentloaded' })

    await expect(page.getByText('Active')).toBeVisible()
    await expect(page.getByText('Paused')).toBeVisible()
  })
})

// ---------------------------------------------------------------------------
// Assistant Page (/assistant) — Protected
// ---------------------------------------------------------------------------

test.describe('Assistant Page', { tag: ['@regression'] }, () => {
  test('loads AI assistant page with heading', async ({ authenticatedPage: page }) => {
    await page.goto('/assistant', { waitUntil: 'domcontentloaded' })

    await expect(
      page.getByRole('heading', { name: /ai assistant/i })
    ).toBeVisible()
  })

  test('shows chat input area', async ({ authenticatedPage: page }) => {
    await page.goto('/assistant', { waitUntil: 'domcontentloaded' })

    // The textarea placeholder says "Ask RateShift AI..."
    await expect(
      page.getByPlaceholder(/ask rateshift ai/i)
    ).toBeVisible()
  })

  test('shows usage indicator', async ({ authenticatedPage: page }) => {
    await page.goto('/assistant', { waitUntil: 'domcontentloaded' })

    // Default mock returns usage: { used: 0, limit: 3, remaining: 3 }
    // The component renders "{used}/{limit} queries today"
    await expect(page.getByText(/0\/3 queries today/i)).toBeVisible()
  })

  test('shows example prompts in empty state', async ({ authenticatedPage: page }) => {
    await page.goto('/assistant', { waitUntil: 'domcontentloaded' })

    // Empty state shows the question "How can I help you save on electricity?"
    await expect(
      page.getByText(/how can i help you save on electricity/i)
    ).toBeVisible()

    // At least one example prompt should be visible
    await expect(
      page.getByText(/cheapest electricity rates/i)
    ).toBeVisible()
  })

  test('shows RateShift AI header in chat panel', async ({ authenticatedPage: page }) => {
    await page.goto('/assistant', { waitUntil: 'domcontentloaded' })

    await expect(
      page.getByRole('heading', { name: /rateshift ai/i })
    ).toBeVisible()
    await expect(
      page.getByText(/energy savings assistant/i)
    ).toBeVisible()
  })
})
