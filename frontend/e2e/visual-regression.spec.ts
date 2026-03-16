/**
 * Visual Regression E2E Tests
 *
 * Screenshot comparison tests for key pages using Playwright's built-in
 * toHaveScreenshot(). Reference screenshots are stored in
 * e2e/visual-regression.spec.ts-snapshots/ and auto-generated on first run.
 *
 * Config: playwright.config.ts sets maxDiffPixelRatio: 0.02 globally.
 *
 * Run with:
 *   npx playwright test visual-regression --update-snapshots   # generate baselines
 *   npx playwright test visual-regression                      # compare against baselines
 */

import { test, expect, PRESET_PRO } from './fixtures'
import { mockBetterAuth } from './helpers/auth'
import { createMockApi } from './helpers/api-mocks'

// ---------------------------------------------------------------------------
// Constants
// ---------------------------------------------------------------------------

const MOBILE_VIEWPORT = { width: 375, height: 812 }
const RENDER_SETTLE_MS = 1000

// ---------------------------------------------------------------------------
// Visual Regression Tests
// ---------------------------------------------------------------------------

test.describe('Visual Regression', { tag: ['@regression'] }, () => {
  // -----------------------------------------------------------------------
  // 1. Landing Page (public)
  // -----------------------------------------------------------------------

  test.describe('Landing Page', () => {
    test.beforeEach(async ({ page }) => {
      await mockBetterAuth(page)
      await createMockApi(page, { authSession: null })
    })

    test('desktop light mode', async ({ page }) => {
      await page.goto('/', { waitUntil: 'domcontentloaded' })
      await page.waitForTimeout(RENDER_SETTLE_MS)

      await expect(page).toHaveScreenshot('landing-desktop-light.png')
    })

    test('desktop dark mode', async ({ page }) => {
      await page.addInitScript(() => {
        const settings = JSON.parse(
          localStorage.getItem('electricity-optimizer-settings') || '{}'
        )
        const state = settings?.state || {}
        state.displayPreferences = {
          ...state.displayPreferences,
          theme: 'dark',
        }
        settings.state = state
        localStorage.setItem(
          'electricity-optimizer-settings',
          JSON.stringify(settings)
        )
      })

      await page.goto('/', { waitUntil: 'domcontentloaded' })
      await page.waitForTimeout(RENDER_SETTLE_MS)

      await expect(page).toHaveScreenshot('landing-desktop-dark.png')
    })

    test('mobile viewport', async ({ page }) => {
      await page.setViewportSize(MOBILE_VIEWPORT)

      await page.goto('/', { waitUntil: 'domcontentloaded' })
      await page.waitForTimeout(RENDER_SETTLE_MS)

      await expect(page).toHaveScreenshot('landing-mobile.png')
    })
  })

  // -----------------------------------------------------------------------
  // 2. Pricing Page (public)
  // -----------------------------------------------------------------------

  test.describe('Pricing Page', () => {
    test.beforeEach(async ({ page }) => {
      await mockBetterAuth(page)
      await createMockApi(page, { authSession: null })
    })

    test('desktop', async ({ page }) => {
      await page.goto('/pricing', { waitUntil: 'domcontentloaded' })
      await page.waitForTimeout(RENDER_SETTLE_MS)

      await expect(page.getByText(/free|pro|business/i).first()).toBeVisible({
        timeout: 5000,
      })
      await expect(page).toHaveScreenshot('pricing-desktop.png')
    })

    test('mobile', async ({ page }) => {
      await page.setViewportSize(MOBILE_VIEWPORT)

      await page.goto('/pricing', { waitUntil: 'domcontentloaded' })
      await page.waitForTimeout(RENDER_SETTLE_MS)

      await expect(page).toHaveScreenshot('pricing-mobile.png')
    })
  })

  // -----------------------------------------------------------------------
  // 3. Dashboard (protected)
  // -----------------------------------------------------------------------

  test.describe('Dashboard', () => {
    test('default state', async ({ authenticatedPage }) => {
      await authenticatedPage.goto('/dashboard', {
        waitUntil: 'domcontentloaded',
      })
      await authenticatedPage.waitForTimeout(RENDER_SETTLE_MS)

      await expect(
        authenticatedPage.getByRole('heading', { name: 'Dashboard' })
      ).toBeVisible({ timeout: 10000 })
      await expect(authenticatedPage).toHaveScreenshot(
        'dashboard-default.png'
      )
    })

    test.describe('Pro tier', () => {
      test.use({ settingsPreset: PRESET_PRO })

      test('with Pro settings', async ({ authenticatedPage }) => {
        await authenticatedPage.goto('/dashboard', {
          waitUntil: 'domcontentloaded',
        })
        await authenticatedPage.waitForTimeout(RENDER_SETTLE_MS)

        await expect(
          authenticatedPage.getByRole('heading', { name: 'Dashboard' })
        ).toBeVisible({ timeout: 10000 })
        await expect(authenticatedPage).toHaveScreenshot(
          'dashboard-pro.png'
        )
      })
    })
  })

  // -----------------------------------------------------------------------
  // 4. Suppliers Page (protected)
  // -----------------------------------------------------------------------

  test.describe('Suppliers Page', () => {
    test('desktop', async ({ authenticatedPage }) => {
      await authenticatedPage.goto('/suppliers', {
        waitUntil: 'domcontentloaded',
      })
      await authenticatedPage.waitForTimeout(RENDER_SETTLE_MS)

      await expect(
        authenticatedPage.getByRole('heading').first()
      ).toBeVisible({ timeout: 10000 })
      await expect(authenticatedPage).toHaveScreenshot(
        'suppliers-desktop.png'
      )
    })
  })

  // -----------------------------------------------------------------------
  // 5. Prices Page (protected)
  // -----------------------------------------------------------------------

  test.describe('Prices Page', () => {
    test('desktop', async ({ authenticatedPage }) => {
      await authenticatedPage.goto('/prices', {
        waitUntil: 'domcontentloaded',
      })
      await authenticatedPage.waitForTimeout(RENDER_SETTLE_MS)

      await expect(
        authenticatedPage.getByRole('heading').first()
      ).toBeVisible({ timeout: 10000 })
      await expect(authenticatedPage).toHaveScreenshot(
        'prices-desktop.png'
      )
    })
  })

  // -----------------------------------------------------------------------
  // 6. Settings Page (protected)
  // -----------------------------------------------------------------------

  test.describe('Settings Page', () => {
    test('desktop', async ({ authenticatedPage }) => {
      await authenticatedPage.goto('/settings', {
        waitUntil: 'domcontentloaded',
      })
      await authenticatedPage.waitForTimeout(RENDER_SETTLE_MS)

      await expect(
        authenticatedPage.getByRole('heading').first()
      ).toBeVisible({ timeout: 10000 })
      await expect(authenticatedPage).toHaveScreenshot(
        'settings-desktop.png'
      )
    })
  })

  // -----------------------------------------------------------------------
  // 7. Auth Pages (public, need auth mocks for form rendering)
  // -----------------------------------------------------------------------

  test.describe('Auth Pages', () => {
    test.beforeEach(async ({ page }) => {
      await mockBetterAuth(page)
      await createMockApi(page, { authSession: null })
    })

    test('login page', async ({ page }) => {
      await page.goto('/auth/login', { waitUntil: 'domcontentloaded' })
      await page.waitForTimeout(RENDER_SETTLE_MS)

      await expect(page.locator('#email')).toBeVisible({ timeout: 5000 })
      await expect(page).toHaveScreenshot('auth-login.png')
    })

    test('signup page', async ({ page }) => {
      await page.goto('/auth/signup', { waitUntil: 'domcontentloaded' })
      await page.waitForTimeout(RENDER_SETTLE_MS)

      await expect(page.locator('#email')).toBeVisible({ timeout: 5000 })
      await expect(page).toHaveScreenshot('auth-signup.png')
    })
  })
})
