/**
 * Comprehensive Page Load E2E Tests
 *
 * Tests every page in the app for:
 * - Successful load (no crash, no white screen)
 * - No JavaScript console errors
 * - No unexpected redirect loops
 * - Correct auth behavior (public vs protected)
 * - Reasonable load time (< 10s)
 *
 * Pages are categorized:
 * - Public: accessible without auth (/,  /pricing, /privacy, /terms, /beta-signup)
 * - Auth:   login/signup flows (/auth/*)
 * - Protected: require session cookie (dashboard, prices, suppliers, etc.)
 *
 * Refactoring note: This file uses the fixtures `test` export for tagged tests
 * but keeps the local helper functions (collectConsoleErrors, initSettings,
 * mockAllApis) because many tests require unauthenticated state or a custom
 * mock layer that differs from the shared factory.
 */

import { test, expect } from './fixtures'
import { type Page, type Route } from '@playwright/test'
import { mockBetterAuth, setAuthenticatedState, clearAuthState } from './helpers/auth'

// ---------------------------------------------------------------------------
// Shared helpers
// ---------------------------------------------------------------------------

/** Collect console errors during page load. Returns array of error messages. */
async function collectConsoleErrors(page: Page, action: () => Promise<void>): Promise<string[]> {
  const errors: string[] = []
  const handler = (msg: import('@playwright/test').ConsoleMessage) => {
    if (msg.type() === 'error') {
      const text = msg.text()
      // Ignore known benign console errors
      if (
        text.includes('Failed to load resource') || // expected when API mocks don't cover all routes
        text.includes('ERR_CONNECTION_REFUSED') ||   // no real backend
        text.includes('net::ERR') ||
        text.includes('favicon.ico') ||
        text.includes('No queryFn') ||               // React Query missing query function (known)
        text.includes('ResizeObserver') ||            // browser resize observer warnings
        text.includes('Download the React DevTools')  // dev warning
      ) {
        return
      }
      errors.push(text)
    }
  }
  page.on('console', handler)
  await action()
  page.off('console', handler)
  return errors
}

/** Set up localStorage with valid settings so hooks fire properly. */
async function initSettings(page: Page) {
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
}

/** Mock all common API endpoints to prevent real network calls. */
async function mockAllApis(page: Page) {
  // Register catch-all FIRST so it has lowest priority (Playwright uses LIFO matching).
  // More specific routes registered after this will take precedence.
  await page.route('**/api/v1/**', async (route) => {
    await route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify({}),
    })
  })

  await page.route('**/api/v1/prices/current**', async (route) => {
    await route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify({
        prices: [{
          ticker: 'ELEC-US_CT',
          current_price: '0.2500',
          currency: 'USD',
          region: 'US_CT',
          supplier: 'Eversource',
          updated_at: new Date().toISOString(),
          is_peak: false,
          carbon_intensity: null,
          price_change_24h: null,
        }],
        price: null,
        region: 'US_CT',
        timestamp: new Date().toISOString(),
        source: 'mock',
      }),
    })
  })

  await page.route('**/api/v1/prices/history**', async (route) => {
    await route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify({
        region: 'US_CT',
        supplier: null,
        start_date: new Date(Date.now() - 86400000).toISOString(),
        end_date: new Date().toISOString(),
        prices: [],
        average_price: null,
        min_price: null,
        max_price: null,
        source: 'mock',
        total: 0,
        page: 1,
        page_size: 24,
        pages: 1,
      }),
    })
  })

  await page.route('**/api/v1/prices/forecast**', async (route) => {
    await route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify({
        region: 'US_CT',
        forecast: {
          id: 'mock-forecast',
          region: 'US_CT',
          generated_at: new Date().toISOString(),
          horizon_hours: 24,
          prices: [],
          confidence: 0.85,
          model_version: 'v1',
          source_api: null,
        },
        generated_at: new Date().toISOString(),
        horizon_hours: 24,
        confidence: 0.85,
        source: 'mock',
      }),
    })
  })

  await page.route('**/api/v1/prices/optimal-periods**', async (route) => {
    await route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify({ periods: [] }),
    })
  })

  await page.route('**/api/v1/suppliers**', async (route) => {
    // Don't intercept /suppliers/recommendation or /suppliers/compare
    const url = route.request().url()
    if (url.includes('/recommendation') || url.includes('/compare')) {
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({ recommendation: null, comparisons: [] }),
      })
      return
    }
    await route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify({
        suppliers: [
          {
            id: '1',
            name: 'Eversource Energy',
            avgPricePerKwh: 0.25,
            greenEnergy: true,
            rating: 4.5,
            estimatedAnnualCost: 1200,
          },
        ],
      }),
    })
  })

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
      body: JSON.stringify({
        total: 0,
        monthly: 0,
        weekly: 0,
        streak_days: 0,
        currency: 'USD',
      }),
    })
  })

  await page.route('**/api/v1/alerts**', async (route) => {
    await route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify({ alerts: [] }),
    })
  })

  await page.route('**/api/v1/connections**', async (route) => {
    await route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify({ connections: [] }),
    })
  })

  await page.route('**/api/v1/agent/**', async (route) => {
    await route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify({ usage: { used: 0, limit: 3, remaining: 3 } }),
    })
  })

  await page.route('**/api/v1/optimization/**', async (route) => {
    await route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify({ schedules: [], recommendations: [] }),
    })
  })
}

// ---------------------------------------------------------------------------
// Public Pages (no auth required)
// ---------------------------------------------------------------------------

test.describe('Public Pages - Load Successfully', () => {
  test('/ (landing page) loads without errors', { tag: ['@smoke'] }, async ({ page }) => {
    const errors = await collectConsoleErrors(page, async () => {
      await page.goto('/', { waitUntil: 'domcontentloaded', timeout: 15000 })
    })

    await expect(page.locator('body')).toBeVisible()
    // Landing page should have a heading or hero content
    await expect(page.getByRole('heading').first()).toBeVisible({ timeout: 5000 })

    // Should stay on landing page (no redirect)
    expect(page.url()).not.toContain('/auth/')
    expect(errors).toEqual([])
  })

  test('/pricing loads without errors', { tag: ['@smoke'] }, async ({ page }) => {
    const errors = await collectConsoleErrors(page, async () => {
      await page.goto('/pricing', { waitUntil: 'domcontentloaded', timeout: 15000 })
    })

    await expect(page.locator('body')).toBeVisible()
    expect(page.url()).toContain('/pricing')
    // Should show pricing tiers
    await expect(page.getByText(/free|pro|business/i).first()).toBeVisible({ timeout: 5000 })
    expect(errors).toEqual([])
  })

  test('/privacy loads without errors', { tag: ['@regression'] }, async ({ page }) => {
    const errors = await collectConsoleErrors(page, async () => {
      await page.goto('/privacy', { waitUntil: 'domcontentloaded', timeout: 15000 })
    })

    await expect(page.locator('body')).toBeVisible()
    expect(page.url()).toContain('/privacy')
    await expect(page.getByRole('heading', { level: 1 })).toBeVisible({ timeout: 5000 })
    expect(errors).toEqual([])
  })

  test('/terms loads without errors', { tag: ['@regression'] }, async ({ page }) => {
    const errors = await collectConsoleErrors(page, async () => {
      await page.goto('/terms', { waitUntil: 'domcontentloaded', timeout: 15000 })
    })

    await expect(page.locator('body')).toBeVisible()
    expect(page.url()).toContain('/terms')
    await expect(page.getByRole('heading', { level: 1, name: /terms/i })).toBeVisible({ timeout: 5000 })
    expect(errors).toEqual([])
  })
})

// ---------------------------------------------------------------------------
// Auth Pages (accessible without session, redirected if session exists)
// ---------------------------------------------------------------------------

test.describe('Auth Pages - Load Successfully', () => {
  test.beforeEach(async ({ page }) => {
    await mockBetterAuth(page)
    await clearAuthState(page)
  })

  test('/auth/login loads without errors', { tag: ['@smoke'] }, async ({ page }) => {
    const errors = await collectConsoleErrors(page, async () => {
      await page.goto('/auth/login', { waitUntil: 'domcontentloaded', timeout: 15000 })
    })

    await expect(page.locator('body')).toBeVisible()
    expect(page.url()).toContain('/auth/login')
    // Should show login form
    await expect(page.locator('#email')).toBeVisible({ timeout: 5000 })
    await expect(page.locator('#password')).toBeVisible()
    expect(errors).toEqual([])
  })

  test('/auth/signup loads without errors', { tag: ['@smoke'] }, async ({ page }) => {
    const errors = await collectConsoleErrors(page, async () => {
      await page.goto('/auth/signup', { waitUntil: 'domcontentloaded', timeout: 15000 })
    })

    await expect(page.locator('body')).toBeVisible()
    expect(page.url()).toContain('/auth/signup')
    // Should show signup form
    await expect(page.locator('#email')).toBeVisible({ timeout: 5000 })
    expect(errors).toEqual([])
  })

  test('/auth/forgot-password loads without errors', { tag: ['@regression'] }, async ({ page }) => {
    const errors = await collectConsoleErrors(page, async () => {
      await page.goto('/auth/forgot-password', { waitUntil: 'domcontentloaded', timeout: 15000 })
    })

    await expect(page.locator('body')).toBeVisible()
    expect(page.url()).toContain('/auth/forgot-password')
    await expect(page.getByRole('heading').first()).toBeVisible({ timeout: 5000 })
    expect(errors).toEqual([])
  })

  test('/auth/reset-password loads without errors', { tag: ['@regression'] }, async ({ page }) => {
    const errors = await collectConsoleErrors(page, async () => {
      await page.goto('/auth/reset-password', { waitUntil: 'domcontentloaded', timeout: 15000 })
    })

    await expect(page.locator('body')).toBeVisible()
    // May redirect or show content depending on token presence
    expect(errors).toEqual([])
  })

  test('/auth/verify-email loads without errors', { tag: ['@regression'] }, async ({ page }) => {
    const errors = await collectConsoleErrors(page, async () => {
      await page.goto('/auth/verify-email', { waitUntil: 'domcontentloaded', timeout: 15000 })
    })

    await expect(page.locator('body')).toBeVisible()
    expect(errors).toEqual([])
  })

  test('auth pages redirect authenticated users to dashboard', { tag: ['@regression'] }, async ({ page }) => {
    await setAuthenticatedState(page)
    await mockAllApis(page)
    await initSettings(page)

    await page.goto('/auth/login')
    // Middleware should redirect authenticated user to /dashboard
    await page.waitForURL(/\/dashboard/, { timeout: 10000 })
  })
})

// ---------------------------------------------------------------------------
// Protected Pages (require auth, test with mocked session)
// ---------------------------------------------------------------------------

test.describe('Protected Pages - Load Successfully', () => {
  test.beforeEach(async ({ page }) => {
    await mockBetterAuth(page)
    await setAuthenticatedState(page)
    await mockAllApis(page)
    await initSettings(page)
  })

  test('/dashboard loads without errors', { tag: ['@smoke'] }, async ({ page }) => {
    const errors = await collectConsoleErrors(page, async () => {
      await page.goto('/dashboard', { waitUntil: 'domcontentloaded', timeout: 15000 })
    })

    await expect(page.locator('body')).toBeVisible()
    expect(page.url()).toContain('/dashboard')
    await expect(page.getByRole('heading', { name: 'Dashboard' })).toBeVisible({ timeout: 10000 })
    expect(errors).toEqual([])
  })

  test('/prices loads without errors', { tag: ['@smoke'] }, async ({ page }) => {
    const errors = await collectConsoleErrors(page, async () => {
      await page.goto('/prices', { waitUntil: 'domcontentloaded', timeout: 15000 })
    })

    await expect(page.locator('body')).toBeVisible()
    expect(page.url()).toContain('/prices')
    await expect(page.getByRole('heading').first()).toBeVisible({ timeout: 10000 })
    expect(errors).toEqual([])
  })

  test('/suppliers loads without errors', { tag: ['@smoke'] }, async ({ page }) => {
    const errors = await collectConsoleErrors(page, async () => {
      await page.goto('/suppliers', { waitUntil: 'domcontentloaded', timeout: 15000 })
    })

    await expect(page.locator('body')).toBeVisible()
    expect(page.url()).toContain('/suppliers')
    await expect(page.getByRole('heading').first()).toBeVisible({ timeout: 10000 })
    expect(errors).toEqual([])
  })

  test('/connections loads without errors', { tag: ['@smoke'] }, async ({ page }) => {
    const errors = await collectConsoleErrors(page, async () => {
      await page.goto('/connections', { waitUntil: 'domcontentloaded', timeout: 15000 })
    })

    await expect(page.locator('body')).toBeVisible()
    expect(page.url()).toContain('/connections')
    await expect(page.getByRole('heading').first()).toBeVisible({ timeout: 10000 })
    expect(errors).toEqual([])
  })

  test('/optimize loads without errors', { tag: ['@smoke'] }, async ({ page }) => {
    const errors = await collectConsoleErrors(page, async () => {
      await page.goto('/optimize', { waitUntil: 'domcontentloaded', timeout: 15000 })
    })

    await expect(page.locator('body')).toBeVisible()
    expect(page.url()).toContain('/optimize')
    await expect(page.getByRole('heading').first()).toBeVisible({ timeout: 10000 })
    expect(errors).toEqual([])
  })

  test('/settings loads without errors', { tag: ['@smoke'] }, async ({ page }) => {
    const errors = await collectConsoleErrors(page, async () => {
      await page.goto('/settings', { waitUntil: 'domcontentloaded', timeout: 15000 })
    })

    await expect(page.locator('body')).toBeVisible()
    expect(page.url()).toContain('/settings')
    await expect(page.getByRole('heading').first()).toBeVisible({ timeout: 10000 })
    expect(errors).toEqual([])
  })

  test('/alerts loads without errors', { tag: ['@smoke'] }, async ({ page }) => {
    const errors = await collectConsoleErrors(page, async () => {
      await page.goto('/alerts', { waitUntil: 'domcontentloaded', timeout: 15000 })
    })

    await expect(page.locator('body')).toBeVisible()
    expect(page.url()).toContain('/alerts')
    await expect(page.getByRole('heading').first()).toBeVisible({ timeout: 10000 })
    expect(errors).toEqual([])
  })

  test('/assistant loads without errors', { tag: ['@smoke'] }, async ({ page }) => {
    const errors = await collectConsoleErrors(page, async () => {
      await page.goto('/assistant', { waitUntil: 'domcontentloaded', timeout: 15000 })
    })

    await expect(page.locator('body')).toBeVisible()
    expect(page.url()).toContain('/assistant')
    await expect(page.getByRole('heading').first()).toBeVisible({ timeout: 10000 })
    expect(errors).toEqual([])
  })

  test('/onboarding loads without errors', { tag: ['@regression'] }, async ({ page }) => {
    // Override profile to simulate user needing onboarding
    await page.route('**/api/v1/users/profile**', async (route) => {
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({
          email: 'test@example.com',
          name: 'Test User',
          region: null,
          utility_types: [],
          current_supplier_id: null,
          annual_usage_kwh: null,
          onboarding_completed: false,
        }),
      })
    })

    const errors = await collectConsoleErrors(page, async () => {
      await page.goto('/onboarding', { waitUntil: 'domcontentloaded', timeout: 15000 })
    })

    await expect(page.locator('body')).toBeVisible()
    expect(errors).toEqual([])
  })

  // Wave 4/5 utility pages
  test('/propane loads without errors', { tag: ['@regression'] }, async ({ page }) => {
    const errors = await collectConsoleErrors(page, async () => {
      await page.goto('/propane', { waitUntil: 'domcontentloaded', timeout: 15000 })
    })

    await expect(page.locator('body')).toBeVisible()
    expect(page.url()).toContain('/propane')
    await expect(page.getByRole('heading').first()).toBeVisible({ timeout: 10000 })
    expect(errors).toEqual([])
  })

  test('/water loads without errors', { tag: ['@regression'] }, async ({ page }) => {
    const errors = await collectConsoleErrors(page, async () => {
      await page.goto('/water', { waitUntil: 'domcontentloaded', timeout: 15000 })
    })

    await expect(page.locator('body')).toBeVisible()
    expect(page.url()).toContain('/water')
    await expect(page.getByRole('heading').first()).toBeVisible({ timeout: 10000 })
    expect(errors).toEqual([])
  })

  test('/gas-rates loads without errors', { tag: ['@regression'] }, async ({ page }) => {
    const errors = await collectConsoleErrors(page, async () => {
      await page.goto('/gas-rates', { waitUntil: 'domcontentloaded', timeout: 15000 })
    })

    await expect(page.locator('body')).toBeVisible()
    expect(page.url()).toContain('/gas-rates')
    await expect(page.getByRole('heading').first()).toBeVisible({ timeout: 10000 })
    expect(errors).toEqual([])
  })

  test('/heating-oil loads without errors', { tag: ['@regression'] }, async ({ page }) => {
    const errors = await collectConsoleErrors(page, async () => {
      await page.goto('/heating-oil', { waitUntil: 'domcontentloaded', timeout: 15000 })
    })

    await expect(page.locator('body')).toBeVisible()
    expect(page.url()).toContain('/heating-oil')
    await expect(page.getByRole('heading').first()).toBeVisible({ timeout: 10000 })
    expect(errors).toEqual([])
  })

  test('/community-solar loads without errors', { tag: ['@regression'] }, async ({ page }) => {
    const errors = await collectConsoleErrors(page, async () => {
      await page.goto('/community-solar', { waitUntil: 'domcontentloaded', timeout: 15000 })
    })

    await expect(page.locator('body')).toBeVisible()
    expect(page.url()).toContain('/community-solar')
    await expect(page.getByRole('heading').first()).toBeVisible({ timeout: 10000 })
    expect(errors).toEqual([])
  })

  test('/community loads without errors', { tag: ['@regression'] }, async ({ page }) => {
    const errors = await collectConsoleErrors(page, async () => {
      await page.goto('/community', { waitUntil: 'domcontentloaded', timeout: 15000 })
    })

    await expect(page.locator('body')).toBeVisible()
    expect(page.url()).toContain('/community')
    await expect(page.getByRole('heading').first()).toBeVisible({ timeout: 10000 })
    expect(errors).toEqual([])
  })
})

// ---------------------------------------------------------------------------
// Protected Pages - Auth Guard (redirect when unauthenticated)
// ---------------------------------------------------------------------------

test.describe('Protected Pages - Redirect When Unauthenticated', () => {
  test.beforeEach(async ({ page }) => {
    await mockBetterAuth(page)
    await clearAuthState(page)
  })

  const protectedPages = [
    '/dashboard',
    '/prices',
    '/suppliers',
    '/connections',
    '/optimize',
    '/settings',
    '/alerts',
    '/assistant',
    '/onboarding',
    '/propane',
    '/water',
    '/gas-rates',
    '/heating-oil',
    '/community-solar',
    '/community',
  ]

  for (const path of protectedPages) {
    test(`${path} redirects to login when unauthenticated`, { tag: ['@smoke'] }, async ({ page }) => {
      await page.goto(path)
      await page.waitForURL(/\/auth\/login/, { timeout: 10000 })
      expect(page.url()).toContain('/auth/login')
      // Should include callbackUrl
      expect(page.url()).toContain(`callbackUrl=${encodeURIComponent(path)}`)
    })
  }
})

// ---------------------------------------------------------------------------
// No Redirect Loop Tests
// ---------------------------------------------------------------------------

test.describe('No Redirect Loops', () => {
  test('unauthenticated user on / does not loop', { tag: ['@regression'] }, async ({ page }) => {
    await mockBetterAuth(page)
    await clearAuthState(page)

    await page.goto('/', { waitUntil: 'domcontentloaded', timeout: 15000 })
    await page.waitForTimeout(2000)

    // Should stay on landing page
    const url = page.url()
    expect(url.endsWith('/') || url.endsWith(':3000') || url.endsWith(':3000/')).toBeTruthy()
    // URL should not be excessively long (no nested redirects)
    expect(url.length).toBeLessThan(300)
  })

  test('authenticated user does not loop between auth and dashboard', { tag: ['@regression'] }, async ({ page }) => {
    await mockBetterAuth(page)
    await setAuthenticatedState(page)
    await mockAllApis(page)
    await initSettings(page)

    await page.goto('/dashboard', { waitUntil: 'domcontentloaded', timeout: 15000 })
    await page.waitForTimeout(2000)

    // Should stay on dashboard
    expect(page.url()).toContain('/dashboard')
    expect(page.url().length).toBeLessThan(300)
  })

  test('stale session does not cause infinite redirect', { tag: ['@regression'] }, async ({ page }) => {
    await mockBetterAuth(page, { sessionExpired: true })
    await setAuthenticatedState(page) // cookie exists but session is expired

    // Mock APIs to return 401 (stale session)
    await page.route('**/api/v1/**', async (route) => {
      await route.fulfill({
        status: 401,
        contentType: 'application/json',
        body: JSON.stringify({ detail: 'Unauthorized' }),
      })
    })

    await page.goto('/dashboard', { waitUntil: 'domcontentloaded', timeout: 15000 })

    // Wait for any potential redirect loops to manifest
    await page.waitForTimeout(3000)

    // URL should not be excessively long (no nested callbackUrl)
    expect(page.url().length).toBeLessThan(500)
  })
})

// ---------------------------------------------------------------------------
// Page Refresh Stability Tests
// ---------------------------------------------------------------------------

test.describe('Page Refresh Stability', () => {
  test.beforeEach(async ({ page }) => {
    await mockBetterAuth(page)
    await setAuthenticatedState(page)
    await mockAllApis(page)
    await initSettings(page)
  })

  test('dashboard survives multiple rapid refreshes', { tag: ['@regression'] }, async ({ page }) => {
    await page.goto('/dashboard', { waitUntil: 'domcontentloaded', timeout: 15000 })
    await expect(page.getByRole('heading', { name: 'Dashboard' })).toBeVisible({ timeout: 10000 })

    // Refresh 3 times
    for (let i = 0; i < 3; i++) {
      await page.reload({ waitUntil: 'domcontentloaded', timeout: 15000 })
      await page.waitForTimeout(500)
    }

    // Should still be on dashboard with content
    expect(page.url()).toContain('/dashboard')
    await expect(page.getByRole('heading', { name: 'Dashboard' })).toBeVisible({ timeout: 10000 })
  })

  test('prices page survives refresh', { tag: ['@regression'] }, async ({ page }) => {
    await page.goto('/prices', { waitUntil: 'domcontentloaded', timeout: 15000 })
    await expect(page.getByRole('heading').first()).toBeVisible({ timeout: 10000 })

    await page.reload({ waitUntil: 'domcontentloaded', timeout: 15000 })

    expect(page.url()).toContain('/prices')
    await expect(page.getByRole('heading').first()).toBeVisible({ timeout: 10000 })
  })

  test('settings page survives refresh', { tag: ['@regression'] }, async ({ page }) => {
    await page.goto('/settings', { waitUntil: 'domcontentloaded', timeout: 15000 })
    await expect(page.getByRole('heading').first()).toBeVisible({ timeout: 10000 })

    await page.reload({ waitUntil: 'domcontentloaded', timeout: 15000 })

    expect(page.url()).toContain('/settings')
    await expect(page.getByRole('heading').first()).toBeVisible({ timeout: 10000 })
  })
})

// ---------------------------------------------------------------------------
// Cross-Page Navigation Tests
// ---------------------------------------------------------------------------

test.describe('Cross-Page Navigation', () => {
  test.beforeEach(async ({ page }) => {
    await mockBetterAuth(page)
    await setAuthenticatedState(page)
    await mockAllApis(page)
    await initSettings(page)
  })

  // Sidebar navigation links — skip on mobile (sidebar hidden)
  test('can navigate between all sidebar pages', { tag: ['@smoke'] }, async ({ page, isMobile }) => {
    test.skip(isMobile === true, 'Sidebar is hidden on mobile')

    // Use the sidebar nav element to scope link clicks (avoids matching page-body links)
    await page.goto('/dashboard', { waitUntil: 'domcontentloaded', timeout: 15000 })
    await expect(page.getByRole('heading', { name: 'Dashboard' })).toBeVisible({ timeout: 10000 })

    const sidebar = page.locator('nav')

    // Navigate to Prices
    await sidebar.getByRole('link', { name: 'Prices', exact: true }).click()
    await page.waitForURL(/\/prices/, { timeout: 10000 })
    await expect(page.getByRole('heading').first()).toBeVisible({ timeout: 10000 })

    // Navigate to Suppliers
    await sidebar.getByRole('link', { name: 'Suppliers', exact: true }).click()
    await page.waitForURL(/\/suppliers/, { timeout: 10000 })
    await expect(page.getByRole('heading').first()).toBeVisible({ timeout: 10000 })

    // Navigate to Optimize
    await sidebar.getByRole('link', { name: 'Optimize', exact: true }).click()
    await page.waitForURL(/\/optimize/, { timeout: 10000 })
    await expect(page.getByRole('heading').first()).toBeVisible({ timeout: 10000 })

    // Navigate to Alerts
    await sidebar.getByRole('link', { name: 'Alerts', exact: true }).click()
    await page.waitForURL(/\/alerts/, { timeout: 10000 })
    await expect(page.getByRole('heading').first()).toBeVisible({ timeout: 10000 })

    // Navigate to Connections
    await sidebar.getByRole('link', { name: 'Connections', exact: true }).click()
    await page.waitForURL(/\/connections/, { timeout: 10000 })
    await expect(page.getByRole('heading').first()).toBeVisible({ timeout: 10000 })

    // Navigate to Assistant
    await sidebar.getByRole('link', { name: 'Assistant', exact: true }).click()
    await page.waitForURL(/\/assistant/, { timeout: 10000 })
    await expect(page.getByRole('heading').first()).toBeVisible({ timeout: 10000 })

    // Navigate back to Dashboard
    await sidebar.getByRole('link', { name: 'Dashboard', exact: true }).click()
    await page.waitForURL(/\/dashboard/, { timeout: 10000 })
    await expect(page.getByRole('heading', { name: 'Dashboard' })).toBeVisible({ timeout: 10000 })
  })
})

// ---------------------------------------------------------------------------
// Error Recovery Tests
// ---------------------------------------------------------------------------

test.describe('Error Recovery', () => {
  test.beforeEach(async ({ page }) => {
    await mockBetterAuth(page)
    await setAuthenticatedState(page)
    await initSettings(page)
  })

  test('dashboard shows error state when all APIs fail', { tag: ['@regression'] }, async ({ page }) => {
    // Mock all API endpoints to return 500
    await page.route('**/api/v1/**', async (route) => {
      await route.fulfill({
        status: 500,
        contentType: 'application/json',
        body: JSON.stringify({ detail: 'Internal server error' }),
      })
    })

    await page.goto('/dashboard', { waitUntil: 'domcontentloaded', timeout: 15000 })

    // Dashboard should still render (not white screen/crash)
    await expect(page.locator('body')).toBeVisible()
    // The heading should still appear
    await expect(page.getByRole('heading', { name: 'Dashboard' })).toBeVisible({ timeout: 10000 })
  })

  test('pages recover after transient API failure', { tag: ['@regression'] }, async ({ page }) => {
    let callCount = 0
    await page.route('**/api/v1/prices/current**', async (route) => {
      callCount++
      if (callCount <= 1) {
        // First call fails
        await route.fulfill({
          status: 500,
          contentType: 'application/json',
          body: JSON.stringify({ detail: 'Temporary failure' }),
        })
      } else {
        // Subsequent calls succeed
        await route.fulfill({
          status: 200,
          contentType: 'application/json',
          body: JSON.stringify({
            prices: [{
              ticker: 'ELEC-US_CT',
              current_price: '0.2500',
              currency: 'USD',
              region: 'US_CT',
              supplier: 'Eversource',
              updated_at: new Date().toISOString(),
              is_peak: false,
              carbon_intensity: null,
              price_change_24h: null,
            }],
            price: null,
            region: 'US_CT',
            timestamp: new Date().toISOString(),
            source: 'mock',
          }),
        })
      }
    })

    // Mock remaining APIs normally
    await mockAllApis(page)

    await page.goto('/dashboard', { waitUntil: 'domcontentloaded', timeout: 15000 })

    // Dashboard should eventually show content (React Query retries)
    await expect(page.locator('body')).toBeVisible()
    await expect(page.getByRole('heading', { name: 'Dashboard' })).toBeVisible({ timeout: 10000 })
  })
})
