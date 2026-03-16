/**
 * LocalStorage Settings Presets for E2E Tests
 *
 * Provides pre-configured user settings for common test scenarios.
 */

import { Page } from '@playwright/test'

// ---------------------------------------------------------------------------
// Settings types
// ---------------------------------------------------------------------------

export interface UserSettings {
  region?: string
  annualUsageKwh?: number
  peakDemandKw?: number
  utilityTypes?: string[]
  displayPreferences?: {
    currency?: string
    theme?: string
    timeFormat?: string
  }
}

// ---------------------------------------------------------------------------
// Presets
// ---------------------------------------------------------------------------

/** Default free-tier single-utility user */
export const PRESET_FREE: UserSettings = {
  region: 'US_CT',
  annualUsageKwh: 10500,
  peakDemandKw: 5,
  utilityTypes: ['electricity'],
  displayPreferences: {
    currency: 'USD',
    theme: 'system',
    timeFormat: '12h',
  },
}

/** Pro-tier single-utility user */
export const PRESET_PRO: UserSettings = {
  ...PRESET_FREE,
}

/** Business-tier single-utility user */
export const PRESET_BUSINESS: UserSettings = {
  ...PRESET_FREE,
}

/** Multi-utility user (electricity + natural gas) */
export const PRESET_MULTI_UTILITY: UserSettings = {
  region: 'US_CT',
  annualUsageKwh: 10500,
  peakDemandKw: 5,
  utilityTypes: ['electricity', 'natural_gas'],
  displayPreferences: {
    currency: 'USD',
    theme: 'system',
    timeFormat: '12h',
  },
}

/** California user (deregulated market) */
export const PRESET_CALIFORNIA: UserSettings = {
  region: 'US_CA',
  annualUsageKwh: 8500,
  peakDemandKw: 4,
  utilityTypes: ['electricity'],
  displayPreferences: {
    currency: 'USD',
    theme: 'system',
    timeFormat: '12h',
  },
}

/** Texas user (ERCOT market) */
export const PRESET_TEXAS: UserSettings = {
  region: 'US_TX',
  annualUsageKwh: 12000,
  peakDemandKw: 6,
  utilityTypes: ['electricity'],
  displayPreferences: {
    currency: 'USD',
    theme: 'system',
    timeFormat: '12h',
  },
}

/** User with no settings (fresh user) */
export const PRESET_EMPTY: UserSettings = {}

// ---------------------------------------------------------------------------
// Injection functions
// ---------------------------------------------------------------------------

const SETTINGS_KEY = 'electricity-optimizer-settings'

/**
 * Inject user settings into localStorage via addInitScript.
 * Must be called BEFORE page.goto().
 */
export async function initSettings(page: Page, settings: UserSettings = PRESET_FREE) {
  await page.addInitScript(
    ([key, data]) => {
      localStorage.setItem(key, JSON.stringify({ state: data }))
    },
    [SETTINGS_KEY, settings] as const
  )
}

/**
 * Clear user settings from localStorage.
 */
export async function clearSettings(page: Page) {
  await page.evaluate((key) => localStorage.removeItem(key), SETTINGS_KEY)
}
