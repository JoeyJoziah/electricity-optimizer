import { test, expect } from '@playwright/test'
import { mockBetterAuth, setAuthenticatedState } from './helpers/auth'

/**
 * GDPR Compliance E2E Tests
 *
 * These tests cover features that are planned but not yet implemented:
 * - Data export/download
 * - Consent management page (/settings/privacy)
 * - Account deletion with email confirmation
 * - Cookie consent banner
 * - Data subject requests
 *
 * Tracked in GitHub Project #4 — unskip as features are built.
 */
test.describe('GDPR Compliance Flow', () => {
  // Skip entire suite — GDPR consent management UI not yet implemented
  test.skip()

  test.beforeEach(async ({ page }) => {
    await mockBetterAuth(page)
    await setAuthenticatedState(page)
  })

  test('navigates to privacy settings', async ({ page }) => {
    await page.goto('/settings')
    await expect(page.getByRole('heading', { name: 'Privacy & Data' })).toBeVisible()
  })

  test('user can export all data', async ({ page }) => {
    await page.goto('/settings')
    await page.click('text=Privacy & Data')
    const downloadPromise = page.waitForEvent('download')
    await page.click('button:has-text("Export")')
    const download = await downloadPromise
    expect(download.suggestedFilename()).toContain('user-data-export')
  })

  test('user can view consent settings', async ({ page }) => {
    await page.goto('/settings/privacy')
    await expect(page.getByText('Your Consent Settings')).toBeVisible()
  })

  test('user can delete all data with confirmation', async ({ page }) => {
    await page.goto('/settings')
    await page.click('button:has-text("Delete My Data")')
    await expect(page.getByText('Are you sure?')).toBeVisible()
  })
})
