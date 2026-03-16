/**
 * Performance Budget E2E Tests
 *
 * Validates Core Web Vital thresholds using the custom assertion helpers:
 * - LCP < 2500ms for dashboard, prices, suppliers
 * - CLS < 0.1 for all main authenticated pages
 * - SPA navigation < 1000ms across dashboard → prices → suppliers
 * - No layout shift during skeleton → content transition
 *
 * All tests are tagged @regression.
 *
 * Notes:
 * - All API mocks are applied so timings reflect only rendering, not network.
 * - measureLCP / measureCLS resolve after a 3s observation window (see assertions.ts).
 *   These tests use `isMobile` to skip on Mobile Safari/Chrome where the
 *   performance observer API behaves differently for LCP.
 * - SPA navigation timing uses the measureNavigation helper which relies on
 *   domcontentloaded state, so it is independent of network conditions.
 */

import { test, expect } from './fixtures'
import {
  expectPagePerformance,
  measureLCP,
  measureCLS,
  measureNavigation,
} from './helpers/assertions'

// LCP and CLS budgets
const BUDGETS = {
  lcp: 2500,  // ms — Good threshold per Google Web Vitals
  cls: 0.1,   // score — Good threshold per Google Web Vitals
  spaNav: 1000, // ms — SPA link click → domcontentloaded
}

// ---------------------------------------------------------------------------
// LCP budgets on key pages
// ---------------------------------------------------------------------------

test.describe('Performance — LCP Budgets', () => {
  // LCP is most meaningful on desktop Chromium where the PerformanceObserver
  // for largest-contentful-paint is fully supported and consistent.
  test.skip(({ browserName, isMobile }) => isMobile || browserName !== 'chromium',
    'LCP measurement is only reliable on desktop Chromium')

  test('dashboard LCP is under 2500ms @regression', async ({ authenticatedPage }) => {
    await authenticatedPage.goto('/dashboard', {
      waitUntil: 'domcontentloaded',
      timeout: 15000,
    })
    await authenticatedPage.waitForSelector('body')

    // Wait for main content to appear before measuring LCP
    await authenticatedPage.waitForSelector('[data-testid="current-price"]', {
      timeout: 10000,
    }).catch(() => {
      // Widget may not have a testid in all builds — fall through
    })

    await expectPagePerformance(authenticatedPage, { lcp: BUDGETS.lcp })
  })

  test('prices page LCP is under 2500ms @regression', async ({ authenticatedPage }) => {
    await authenticatedPage.goto('/prices', {
      waitUntil: 'domcontentloaded',
      timeout: 15000,
    })
    await authenticatedPage.waitForSelector('body')
    await authenticatedPage.waitForSelector('h1, [role="heading"]', { timeout: 10000 })

    await expectPagePerformance(authenticatedPage, { lcp: BUDGETS.lcp })
  })

  test('suppliers page LCP is under 2500ms @regression', async ({ authenticatedPage }) => {
    await authenticatedPage.goto('/suppliers', {
      waitUntil: 'domcontentloaded',
      timeout: 15000,
    })
    await authenticatedPage.waitForSelector('body')
    await authenticatedPage.waitForSelector('h1, [role="heading"]', { timeout: 10000 })

    await expectPagePerformance(authenticatedPage, { lcp: BUDGETS.lcp })
  })
})

// ---------------------------------------------------------------------------
// CLS budgets on main pages
// ---------------------------------------------------------------------------

test.describe('Performance — CLS Budgets', () => {
  // CLS is measured in Chromium and Firefox; skip on webkit where the
  // layout-shift performance entry type has inconsistent support.
  test.skip(({ browserName }) => browserName === 'webkit',
    'CLS PerformanceObserver not consistently supported in webkit')

  test('dashboard CLS is under 0.1 @regression', async ({ authenticatedPage }) => {
    await authenticatedPage.goto('/dashboard', {
      waitUntil: 'domcontentloaded',
      timeout: 15000,
    })
    await authenticatedPage.waitForSelector('body')

    // Allow the page to fully settle
    await authenticatedPage.waitForTimeout(1000)

    await expectPagePerformance(authenticatedPage, { cls: BUDGETS.cls })
  })

  test('prices page CLS is under 0.1 @regression', async ({ authenticatedPage }) => {
    await authenticatedPage.goto('/prices', {
      waitUntil: 'domcontentloaded',
      timeout: 15000,
    })
    await authenticatedPage.waitForSelector('body')
    await authenticatedPage.waitForTimeout(1000)

    await expectPagePerformance(authenticatedPage, { cls: BUDGETS.cls })
  })

  test('suppliers page CLS is under 0.1 @regression', async ({ authenticatedPage }) => {
    await authenticatedPage.goto('/suppliers', {
      waitUntil: 'domcontentloaded',
      timeout: 15000,
    })
    await authenticatedPage.waitForSelector('body')
    await authenticatedPage.waitForTimeout(1000)

    await expectPagePerformance(authenticatedPage, { cls: BUDGETS.cls })
  })

  test('optimize page CLS is under 0.1 @regression', async ({ authenticatedPage }) => {
    await authenticatedPage.goto('/optimize', {
      waitUntil: 'domcontentloaded',
      timeout: 15000,
    })
    await authenticatedPage.waitForSelector('body')
    await authenticatedPage.waitForTimeout(1000)

    await expectPagePerformance(authenticatedPage, { cls: BUDGETS.cls })
  })

  test('settings page CLS is under 0.1 @regression', async ({ authenticatedPage }) => {
    await authenticatedPage.goto('/settings', {
      waitUntil: 'domcontentloaded',
      timeout: 15000,
    })
    await authenticatedPage.waitForSelector('body')
    await authenticatedPage.waitForTimeout(1000)

    await expectPagePerformance(authenticatedPage, { cls: BUDGETS.cls })
  })
})

// ---------------------------------------------------------------------------
// SPA navigation timing
// ---------------------------------------------------------------------------

test.describe('Performance — SPA Navigation Speed', () => {
  // Navigation timing is tested on desktop only; mobile viewports hide the
  // sidebar so navigation links are not visible.
  test.skip(({ isMobile }) => isMobile, 'Sidebar navigation is hidden on mobile')

  test('dashboard → prices SPA navigation is under 1000ms @regression', async ({
    authenticatedPage,
  }) => {
    await authenticatedPage.goto('/dashboard', {
      waitUntil: 'domcontentloaded',
      timeout: 15000,
    })
    await authenticatedPage.waitForSelector('body')

    const sidebar = authenticatedPage.locator('nav')
    const duration = await measureNavigation(authenticatedPage, async () => {
      await sidebar.getByRole('link', { name: 'Prices', exact: true }).click()
      await authenticatedPage.waitForURL(/\/prices/, { timeout: 10000 })
    })

    expect(duration).toBeLessThan(BUDGETS.spaNav)
  })

  test('prices → suppliers SPA navigation is under 1000ms @regression', async ({
    authenticatedPage,
  }) => {
    await authenticatedPage.goto('/prices', {
      waitUntil: 'domcontentloaded',
      timeout: 15000,
    })
    await authenticatedPage.waitForSelector('body')

    const sidebar = authenticatedPage.locator('nav')
    const duration = await measureNavigation(authenticatedPage, async () => {
      await sidebar.getByRole('link', { name: 'Suppliers', exact: true }).click()
      await authenticatedPage.waitForURL(/\/suppliers/, { timeout: 10000 })
    })

    expect(duration).toBeLessThan(BUDGETS.spaNav)
  })

  test('dashboard → prices → suppliers full navigation chain @regression', async ({
    authenticatedPage,
  }) => {
    await authenticatedPage.goto('/dashboard', {
      waitUntil: 'domcontentloaded',
      timeout: 15000,
    })
    await authenticatedPage.waitForSelector('body')

    const sidebar = authenticatedPage.locator('nav')

    // Leg 1: dashboard → prices
    const leg1 = await measureNavigation(authenticatedPage, async () => {
      await sidebar.getByRole('link', { name: 'Prices', exact: true }).click()
      await authenticatedPage.waitForURL(/\/prices/, { timeout: 10000 })
    })

    // Leg 2: prices → suppliers
    const leg2 = await measureNavigation(authenticatedPage, async () => {
      await sidebar.getByRole('link', { name: 'Suppliers', exact: true }).click()
      await authenticatedPage.waitForURL(/\/suppliers/, { timeout: 10000 })
    })

    expect(leg1).toBeLessThan(BUDGETS.spaNav)
    expect(leg2).toBeLessThan(BUDGETS.spaNav)
  })
})

// ---------------------------------------------------------------------------
// No layout shift during skeleton → content transition
// ---------------------------------------------------------------------------

test.describe('Performance — Skeleton to Content Stability', () => {
  // Measures CLS captured during the window between page load and content
  // rendering, specifically targeting the skeleton loader transition.
  test.skip(({ browserName }) => browserName === 'webkit',
    'CLS PerformanceObserver not consistently supported in webkit')

  test('dashboard has no layout shift during data loading @regression', async ({
    authenticatedPage,
  }) => {
    // Start CLS measurement before navigating so we capture the full load window
    const clsPromise = authenticatedPage.evaluate(() => {
      return new Promise<number>((resolve) => {
        let cls = 0
        const observer = new PerformanceObserver((list) => {
          for (const entry of list.getEntries()) {
            const ls = entry as PerformanceEntry & {
              hadRecentInput: boolean
              value: number
            }
            if (!ls.hadRecentInput) cls += ls.value
          }
        })
        observer.observe({ type: 'layout-shift', buffered: true })
        // Resolve after 4 seconds to capture skeleton → content shift
        setTimeout(() => {
          observer.disconnect()
          resolve(cls)
        }, 4000)
      })
    })

    await authenticatedPage.goto('/dashboard', {
      waitUntil: 'domcontentloaded',
      timeout: 15000,
    })

    const cls = await clsPromise
    expect(cls).toBeLessThan(BUDGETS.cls)
  })

  test('suppliers page has no layout shift during skeleton → content @regression', async ({
    authenticatedPage,
  }) => {
    const clsPromise = authenticatedPage.evaluate(() => {
      return new Promise<number>((resolve) => {
        let cls = 0
        const observer = new PerformanceObserver((list) => {
          for (const entry of list.getEntries()) {
            const ls = entry as PerformanceEntry & {
              hadRecentInput: boolean
              value: number
            }
            if (!ls.hadRecentInput) cls += ls.value
          }
        })
        observer.observe({ type: 'layout-shift', buffered: true })
        setTimeout(() => {
          observer.disconnect()
          resolve(cls)
        }, 4000)
      })
    })

    await authenticatedPage.goto('/suppliers', {
      waitUntil: 'domcontentloaded',
      timeout: 15000,
    })

    const cls = await clsPromise
    expect(cls).toBeLessThan(BUDGETS.cls)
  })
})
