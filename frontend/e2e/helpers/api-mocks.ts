/**
 * Centralized API Mock Factory for E2E Tests
 *
 * Eliminates boilerplate by providing a single function to register all
 * standard API route mocks with sensible defaults and per-test overrides.
 *
 * IMPORTANT: Playwright uses LIFO route matching — catch-all is registered
 * FIRST (lowest priority), then specific routes override it.
 */

import { Page, Route } from '@playwright/test'

// ---------------------------------------------------------------------------
// Mock data types
// ---------------------------------------------------------------------------

export interface MockPriceData {
  region?: string
  price?: number
  trend?: string
  changePercent?: number
}

export interface MockSupplier {
  id: string
  name: string
  avgPricePerKwh: number
  standingCharge?: number
  greenEnergy: boolean
  rating: number
  estimatedAnnualCost: number
  tariffType?: string
  features?: string[]
  recommended?: boolean
  exitFee?: number
}

export interface MockUserProfile {
  email?: string
  name?: string
  region?: string
  utility_types?: string[]
  current_supplier_id?: string | null
  annual_usage_kwh?: number
  onboarding_completed?: boolean
  subscription_tier?: string
}

export interface MockCommunityPost {
  id: string
  user_id: string
  region: string
  utility_type: string
  post_type: string
  title: string
  body: string
  upvotes: number
  rate_per_unit?: number
  rate_unit?: string
  supplier_name?: string
  is_hidden: boolean
  is_pending_moderation: boolean
  created_at: string
}

export interface MockApiConfig {
  /** Override prices/current response */
  pricesCurrent?: MockPriceData | false
  /** Override prices/history response */
  pricesHistory?: object | false
  /** Override prices/forecast response */
  pricesForecast?: object | false
  /** Override prices/optimal-periods response */
  optimalPeriods?: object | false
  /** Override suppliers list response */
  suppliers?: MockSupplier[] | false
  /** Override user profile response */
  userProfile?: MockUserProfile | false
  /** Override user/supplier response */
  userSupplier?: object | false
  /** Override savings/summary response */
  savingsSummary?: object | false
  /** Override alerts response */
  alerts?: object | false
  /** Override connections response */
  connections?: object | false
  /** Override agent response */
  agent?: object | false
  /** Override optimization response */
  optimization?: object | false
  /** Override community posts response */
  communityPosts?: MockCommunityPost[] | false
  /** Override community stats response */
  communityStats?: object | false
  /** Override community vote response */
  communityVote?: object | false
  /** Override auth session response (null = unauthenticated) */
  authSession?: object | null | false
}

// ---------------------------------------------------------------------------
// Route call tracker
// ---------------------------------------------------------------------------

export interface RouteCall {
  url: string
  method: string
  postData: string | null
  timestamp: number
}

export class ApiCallTracker {
  private calls: RouteCall[] = []

  record(route: Route) {
    this.calls.push({
      url: route.request().url(),
      method: route.request().method(),
      postData: route.request().postData(),
      timestamp: Date.now(),
    })
  }

  getCalls(pattern?: string | RegExp, method?: string): RouteCall[] {
    return this.calls.filter((call) => {
      if (method && call.method !== method) return false
      if (pattern) {
        const regex = typeof pattern === 'string' ? new RegExp(pattern) : pattern
        return regex.test(call.url)
      }
      return true
    })
  }

  getCallCount(pattern?: string | RegExp, method?: string): number {
    return this.getCalls(pattern, method).length
  }

  wasCalled(pattern: string | RegExp, method?: string): boolean {
    return this.getCallCount(pattern, method) > 0
  }

  reset() {
    this.calls = []
  }
}

// ---------------------------------------------------------------------------
// Default mock data
// ---------------------------------------------------------------------------

const DEFAULT_PRICE: MockPriceData = {
  region: 'US_CT',
  price: 0.25,
  trend: 'stable',
  changePercent: 0,
}

const DEFAULT_SUPPLIERS: MockSupplier[] = [
  {
    id: '1',
    name: 'Eversource Energy',
    avgPricePerKwh: 0.25,
    standingCharge: 0.5,
    greenEnergy: true,
    rating: 4.5,
    estimatedAnnualCost: 1200,
    tariffType: 'variable',
  },
]

const DEFAULT_PROFILE: MockUserProfile = {
  email: 'test@example.com',
  name: 'Test User',
  region: 'US_CT',
  utility_types: ['electricity'],
  current_supplier_id: null,
  annual_usage_kwh: 10500,
  onboarding_completed: true,
}

// ---------------------------------------------------------------------------
// Main mock registration function
// ---------------------------------------------------------------------------

/**
 * Register all standard API route mocks on a Playwright page.
 *
 * @param page  Playwright Page instance
 * @param overrides  Per-test overrides. Set a key to `false` to skip that mock.
 * @returns ApiCallTracker for asserting which routes were called.
 */
export async function createMockApi(
  page: Page,
  overrides: MockApiConfig = {}
): Promise<ApiCallTracker> {
  const tracker = new ApiCallTracker()

  // --- Catch-all (LIFO: registered first = lowest priority) ---
  await page.route('**/api/v1/**', async (route) => {
    tracker.record(route)
    await route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify({}),
    })
  })

  // --- Auth session ---
  if (overrides.authSession !== false) {
    await page.route('**/api/auth/get-session', async (route) => {
      tracker.record(route)
      const session = overrides.authSession ?? {
        user: {
          id: 'user_e2e_123',
          email: 'test@example.com',
          name: 'Test User',
          emailVerified: true,
        },
        session: {
          id: 'session_e2e_123',
          userId: 'user_e2e_123',
          token: 'mock-session-token-e2e-test',
          expiresAt: new Date(Date.now() + 86400000).toISOString(),
        },
      }
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify(session),
      })
    })
  }

  // --- Prices: current ---
  if (overrides.pricesCurrent !== false) {
    const priceData = { ...DEFAULT_PRICE, ...(overrides.pricesCurrent || {}) }
    await page.route('**/api/v1/prices/current**', async (route) => {
      tracker.record(route)
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({
          prices: [
            {
              ticker: `ELEC-${priceData.region}`,
              current_price: String(priceData.price),
              currency: 'USD',
              region: priceData.region,
              supplier: 'Eversource',
              updated_at: new Date().toISOString(),
              is_peak: false,
              carbon_intensity: null,
              price_change_24h: null,
              price: priceData.price,
              timestamp: new Date().toISOString(),
              trend: priceData.trend,
              changePercent: priceData.changePercent,
            },
          ],
          price: null,
          region: priceData.region,
          timestamp: new Date().toISOString(),
          source: 'mock',
        }),
      })
    })
  }

  // --- Prices: history ---
  if (overrides.pricesHistory !== false) {
    await page.route('**/api/v1/prices/history**', async (route) => {
      tracker.record(route)
      const data = overrides.pricesHistory ?? {
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
      }
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify(data),
      })
    })
  }

  // --- Prices: forecast ---
  if (overrides.pricesForecast !== false) {
    await page.route('**/api/v1/prices/forecast**', async (route) => {
      tracker.record(route)
      const data = overrides.pricesForecast ?? {
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
      }
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify(data),
      })
    })
  }

  // --- Prices: optimal periods ---
  if (overrides.optimalPeriods !== false) {
    await page.route('**/api/v1/prices/optimal-periods**', async (route) => {
      tracker.record(route)
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify(overrides.optimalPeriods ?? { periods: [] }),
      })
    })
  }

  // --- Suppliers ---
  if (overrides.suppliers !== false) {
    await page.route('**/api/v1/suppliers**', async (route) => {
      tracker.record(route)
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
          suppliers: overrides.suppliers ?? DEFAULT_SUPPLIERS,
        }),
      })
    })
  }

  // --- User profile ---
  if (overrides.userProfile !== false) {
    const profile = { ...DEFAULT_PROFILE, ...(overrides.userProfile || {}) }
    await page.route('**/api/v1/users/profile**', async (route) => {
      tracker.record(route)
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify(profile),
      })
    })
  }

  // --- User supplier ---
  if (overrides.userSupplier !== false) {
    await page.route('**/api/v1/user/supplier', async (route) => {
      tracker.record(route)
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify(overrides.userSupplier ?? { supplier: null }),
      })
    })
  }

  // --- Savings summary ---
  if (overrides.savingsSummary !== false) {
    await page.route('**/api/v1/savings/summary**', async (route) => {
      tracker.record(route)
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify(
          overrides.savingsSummary ?? {
            total: 0,
            monthly: 0,
            weekly: 0,
            streak_days: 0,
            currency: 'USD',
          }
        ),
      })
    })
  }

  // --- Alerts ---
  if (overrides.alerts !== false) {
    await page.route('**/api/v1/alerts**', async (route) => {
      tracker.record(route)
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify(overrides.alerts ?? { alerts: [] }),
      })
    })
  }

  // --- Connections ---
  if (overrides.connections !== false) {
    await page.route('**/api/v1/connections**', async (route) => {
      tracker.record(route)
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify(overrides.connections ?? { connections: [] }),
      })
    })
  }

  // --- Agent ---
  if (overrides.agent !== false) {
    await page.route('**/api/v1/agent/**', async (route) => {
      tracker.record(route)
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify(
          overrides.agent ?? { usage: { used: 0, limit: 3, remaining: 3 } }
        ),
      })
    })
  }

  // --- Optimization ---
  if (overrides.optimization !== false) {
    await page.route('**/api/v1/optimization/**', async (route) => {
      tracker.record(route)
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify(
          overrides.optimization ?? { schedules: [], recommendations: [] }
        ),
      })
    })
  }

  // --- Community posts ---
  if (overrides.communityPosts !== false && overrides.communityPosts !== undefined) {
    await page.route('**/api/v1/community/posts**', async (route) => {
      tracker.record(route)
      if (route.request().method() === 'GET') {
        await route.fulfill({
          status: 200,
          contentType: 'application/json',
          body: JSON.stringify({
            posts: overrides.communityPosts,
            total: (overrides.communityPosts as MockCommunityPost[]).length,
            page: 1,
            per_page: 20,
          }),
        })
      } else if (route.request().method() === 'POST') {
        const body = JSON.parse(route.request().postData() || '{}')
        await route.fulfill({
          status: 201,
          contentType: 'application/json',
          body: JSON.stringify({
            id: 'post-new',
            user_id: 'user_e2e_123',
            region: body.region || 'US_CT',
            utility_type: body.utility_type || 'electricity',
            post_type: body.post_type || 'tip',
            title: body.title,
            body: body.body,
            upvotes: 0,
            is_hidden: false,
            is_pending_moderation: true,
            created_at: new Date().toISOString(),
          }),
        })
      }
    })
  }

  // --- Community stats ---
  if (overrides.communityStats !== false && overrides.communityStats !== undefined) {
    await page.route('**/api/v1/community/stats**', async (route) => {
      tracker.record(route)
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify(overrides.communityStats),
      })
    })
  }

  // --- Community vote ---
  if (overrides.communityVote !== false && overrides.communityVote !== undefined) {
    await page.route('**/api/v1/community/posts/*/vote', async (route) => {
      tracker.record(route)
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify(overrides.communityVote ?? { voted: true }),
      })
    })
  }

  return tracker
}
