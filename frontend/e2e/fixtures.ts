/**
 * Custom Playwright Fixtures
 *
 * Extends the base Playwright test with reusable fixtures:
 * - authenticatedPage: Page with auth cookie + route mocks pre-configured
 * - apiMocks: Centralized API mock manager with call tracking
 * - settings: localStorage settings injector
 *
 * Usage:
 *   import { test, expect } from './fixtures'
 *
 *   test('my test', async ({ authenticatedPage, apiMocks }) => {
 *     await authenticatedPage.goto('/dashboard')
 *     // ... assertions ...
 *   })
 */

import { test as base, Page } from '@playwright/test'
import { mockBetterAuth, setAuthenticatedState } from './helpers/auth'
import { createMockApi, ApiCallTracker, MockApiConfig } from './helpers/api-mocks'
import { initSettings, UserSettings, PRESET_FREE } from './helpers/settings'

// ---------------------------------------------------------------------------
// Fixture type declarations
// ---------------------------------------------------------------------------

type TestFixtures = {
  /** Page with auth mocks, session cookie, localStorage settings, and all API mocks pre-configured. */
  authenticatedPage: Page
  /** API call tracker from the authenticated page setup. */
  apiMocks: ApiCallTracker
  /** Function to initialize settings on any page. */
  initPageSettings: (page: Page, settings?: UserSettings) => Promise<void>
  /** Override API mock config — set this before using authenticatedPage. */
  apiMockConfig: MockApiConfig
  /** Override user settings preset — set this before using authenticatedPage. */
  settingsPreset: UserSettings
}

// ---------------------------------------------------------------------------
// Extended test with custom fixtures
// ---------------------------------------------------------------------------

export const test = base.extend<TestFixtures>({
  // Default config — tests can override via test.use()
  apiMockConfig: [{}, { option: true }],
  settingsPreset: [PRESET_FREE, { option: true }],

  authenticatedPage: async ({ page, apiMockConfig, settingsPreset }, use) => {
    // 1. Set up Better Auth route mocks
    await mockBetterAuth(page)

    // 2. Set the session cookie
    await setAuthenticatedState(page)

    // 3. Inject localStorage settings
    await initSettings(page, settingsPreset)

    // 4. Register all API mocks
    await createMockApi(page, apiMockConfig)

    // Provide the fully configured page
    await use(page)
  },

  apiMocks: async ({ page, apiMockConfig }, use) => {
    // Register mocks and return the tracker
    // Note: authenticatedPage already calls createMockApi, so if both fixtures
    // are used, the page will have mocks from both. To avoid double-registration,
    // tests should use either authenticatedPage OR (page + apiMocks), not both.
    const tracker = await createMockApi(page, apiMockConfig)
    await use(tracker)
  },

  initPageSettings: async ({}, use) => {
    await use(async (page: Page, settings?: UserSettings) => {
      await initSettings(page, settings)
    })
  },
})

export { expect } from '@playwright/test'

// Re-export common types and presets for convenience
export type { MockApiConfig, ApiCallTracker } from './helpers/api-mocks'
export type { UserSettings } from './helpers/settings'
export {
  PRESET_FREE,
  PRESET_PRO,
  PRESET_BUSINESS,
  PRESET_MULTI_UTILITY,
  PRESET_CALIFORNIA,
  PRESET_TEXAS,
  PRESET_EMPTY,
} from './helpers/settings'
