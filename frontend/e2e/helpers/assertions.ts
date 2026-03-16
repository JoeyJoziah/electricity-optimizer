/**
 * Custom E2E Assertion Helpers
 *
 * Provides reusable assertion patterns for API call verification,
 * console error detection, and performance measurement.
 */

import { Page, expect } from '@playwright/test'
import type { ApiCallTracker } from './api-mocks'

// ---------------------------------------------------------------------------
// API call assertions
// ---------------------------------------------------------------------------

/**
 * Assert that an API endpoint was called at least once.
 */
export async function expectApiCalled(
  tracker: ApiCallTracker,
  pattern: string | RegExp,
  options?: { method?: string; count?: number; bodyContains?: string }
) {
  const calls = tracker.getCalls(pattern, options?.method)

  if (options?.count !== undefined) {
    expect(calls.length).toBe(options.count)
  } else {
    expect(calls.length).toBeGreaterThan(0)
  }

  if (options?.bodyContains) {
    const matched = calls.some(
      (c) => c.postData && c.postData.includes(options.bodyContains!)
    )
    expect(matched).toBe(true)
  }
}

/**
 * Assert that an API endpoint was NOT called.
 */
export function expectApiNotCalled(
  tracker: ApiCallTracker,
  pattern: string | RegExp,
  method?: string
) {
  expect(tracker.getCallCount(pattern, method)).toBe(0)
}

// ---------------------------------------------------------------------------
// Console error assertions
// ---------------------------------------------------------------------------

/** Known benign console errors to ignore */
const BENIGN_ERRORS = [
  'Failed to load resource',
  'ERR_CONNECTION_REFUSED',
  'net::ERR',
  'favicon.ico',
  'No queryFn',
  'ResizeObserver',
  'Download the React DevTools',
  'hydration',
  'Hydration',
]

/**
 * Collect console errors during an action, filtering out known benign ones.
 * Returns array of unexpected error messages.
 */
export async function collectConsoleErrors(
  page: Page,
  action: () => Promise<void>
): Promise<string[]> {
  const errors: string[] = []
  const handler = (msg: { type: () => string; text: () => string }) => {
    if (msg.type() === 'error') {
      const text = msg.text()
      if (!BENIGN_ERRORS.some((b) => text.includes(b))) {
        errors.push(text)
      }
    }
  }
  page.on('console', handler)
  await action()
  page.off('console', handler)
  return errors
}

/**
 * Assert that an action produces no unexpected console errors.
 */
export async function expectNoConsoleErrors(
  page: Page,
  action: () => Promise<void>
) {
  const errors = await collectConsoleErrors(page, action)
  expect(errors).toEqual([])
}

// ---------------------------------------------------------------------------
// Performance assertions
// ---------------------------------------------------------------------------

/**
 * Measure Largest Contentful Paint (LCP) for the current page.
 */
export async function measureLCP(page: Page): Promise<number> {
  return page.evaluate(() => {
    return new Promise<number>((resolve) => {
      let lcp = 0
      const observer = new PerformanceObserver((list) => {
        const entries = list.getEntries()
        for (const entry of entries) {
          lcp = entry.startTime
        }
      })
      observer.observe({ type: 'largest-contentful-paint', buffered: true })

      // Wait a bit to collect LCP entries, then resolve
      setTimeout(() => {
        observer.disconnect()
        resolve(lcp)
      }, 3000)
    })
  })
}

/**
 * Measure Cumulative Layout Shift (CLS) for the current page.
 */
export async function measureCLS(page: Page): Promise<number> {
  return page.evaluate(() => {
    return new Promise<number>((resolve) => {
      let cls = 0
      const observer = new PerformanceObserver((list) => {
        for (const entry of list.getEntries()) {
          const layoutShift = entry as PerformanceEntry & {
            hadRecentInput: boolean
            value: number
          }
          if (!layoutShift.hadRecentInput) {
            cls += layoutShift.value
          }
        }
      })
      observer.observe({ type: 'layout-shift', buffered: true })

      setTimeout(() => {
        observer.disconnect()
        resolve(cls)
      }, 3000)
    })
  })
}

/**
 * Assert page performance metrics meet thresholds.
 */
export async function expectPagePerformance(
  page: Page,
  thresholds: { lcp?: number; cls?: number }
) {
  if (thresholds.lcp !== undefined) {
    const lcp = await measureLCP(page)
    expect(lcp).toBeLessThan(thresholds.lcp)
  }

  if (thresholds.cls !== undefined) {
    const cls = await measureCLS(page)
    expect(cls).toBeLessThan(thresholds.cls)
  }
}

/**
 * Measure SPA navigation time between pages.
 */
export async function measureNavigation(
  page: Page,
  action: () => Promise<void>
): Promise<number> {
  const start = Date.now()
  await action()
  await page.waitForLoadState('domcontentloaded')
  return Date.now() - start
}
