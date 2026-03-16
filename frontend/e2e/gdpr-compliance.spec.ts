/**
 * GDPR Compliance E2E Tests
 *
 * Tests for the Data & Privacy section on the /settings page:
 * - Data export (Download My Data button)
 * - Account deletion flow (Delete My Account button with window.confirm)
 * - Privacy section display and element presence
 *
 * All tests use the shared `authenticatedPage` fixture which sets up auth
 * mocks, session cookie, localStorage settings, and standard API mocks.
 *
 * Endpoints mocked per test:
 * - GET  /api/v1/compliance/gdpr/export  — data export
 * - DELETE /api/v1/compliance/gdpr/delete — account deletion
 */

import { test, expect } from './fixtures'

test.describe('GDPR Compliance — Data & Privacy', () => {
  // ---------------------------------------------------------------------------
  // Test 1: Privacy section display
  // ---------------------------------------------------------------------------

  test(
    'Privacy & Data section is visible with correct elements',
    { tag: ['@regression'] },
    async ({ authenticatedPage: page }) => {
      await page.goto('/settings')

      // The "Data & Privacy" h3 heading should be visible in the GDPR section
      await expect(page.getByRole('heading', { name: 'Data & Privacy' })).toBeVisible()

      // Descriptive text explaining GDPR compliance should be present
      await expect(
        page.getByText(/manage your personal data.*gdpr/i)
      ).toBeVisible()

      // Both action buttons must be rendered
      await expect(
        page.getByRole('button', { name: /download my data/i })
      ).toBeVisible()

      await expect(
        page.getByRole('button', { name: /delete my account/i })
      ).toBeVisible()
    }
  )

  // ---------------------------------------------------------------------------
  // Test 2: Data export triggers a download
  // ---------------------------------------------------------------------------

  test(
    'clicking Download My Data triggers a file download',
    { tag: ['@regression'] },
    async ({ authenticatedPage: page }) => {
      // Mock the GDPR export endpoint to return sample user data JSON.
      // The page fetches this URL then creates a Blob + synthetic <a download> click,
      // which Playwright captures as a download event.
      await page.route('**/api/v1/compliance/gdpr/export', async (route) => {
        await route.fulfill({
          status: 200,
          contentType: 'application/json',
          body: JSON.stringify({
            user: { id: 'user_e2e_123', email: 'test@example.com' },
            settings: {},
            alerts: [],
            connections: [],
            exported_at: new Date().toISOString(),
          }),
        })
      })

      await page.goto('/settings')

      // Verify button is enabled before clicking
      const exportButton = page.getByRole('button', { name: /download my data/i })
      await expect(exportButton).toBeVisible()
      await expect(exportButton).toBeEnabled()

      // The page uses fetch + Blob + anchor .click() to trigger the download.
      // Playwright intercepts the programmatic anchor click and emits the download event.
      const downloadPromise = page.waitForEvent('download')
      await exportButton.click()
      const download = await downloadPromise

      // The filename is set to `my-data-<YYYY-MM-DD>.json` in the page handler
      expect(download.suggestedFilename()).toMatch(/^my-data-\d{4}-\d{2}-\d{2}\.json$/)
    }
  )

  // ---------------------------------------------------------------------------
  // Test 3: Delete account — cancel returns to settings
  // ---------------------------------------------------------------------------

  test(
    'Delete My Account shows confirmation dialog and cancel returns to settings',
    { tag: ['@regression'] },
    async ({ authenticatedPage: page }) => {
      // Mock the delete endpoint (should NOT be called when user cancels)
      let deleteCalled = false
      await page.route('**/api/v1/compliance/gdpr/delete', async (route) => {
        deleteCalled = true
        await route.fulfill({
          status: 200,
          contentType: 'application/json',
          body: JSON.stringify({ deleted: true }),
        })
      })

      await page.goto('/settings')

      // Intercept window.confirm before clicking — dismiss it (cancel)
      await page.evaluate(() => {
        window.confirm = () => false
      })

      const deleteButton = page.getByRole('button', { name: /delete my account/i })
      await expect(deleteButton).toBeVisible()
      await deleteButton.click()

      // After cancelling, the user stays on /settings
      await expect(page).toHaveURL(/\/settings/)

      // The deletion API must not have been called
      expect(deleteCalled).toBe(false)
    }
  )

  // ---------------------------------------------------------------------------
  // Test 4: Delete account — confirm triggers deletion API call
  // ---------------------------------------------------------------------------

  test(
    'Delete My Account — confirming the dialog calls the deletion endpoint',
    { tag: ['@regression'] },
    async ({ authenticatedPage: page }) => {
      // Track that DELETE /api/v1/compliance/gdpr/delete was called
      let deleteRequestMethod: string | undefined
      await page.route('**/api/v1/compliance/gdpr/delete', async (route) => {
        deleteRequestMethod = route.request().method()
        await route.fulfill({
          status: 200,
          contentType: 'application/json',
          body: JSON.stringify({ deleted: true }),
        })
      })

      // Mock sign-out endpoint called after deletion
      await page.route('**/api/auth/sign-out', async (route) => {
        await route.fulfill({
          status: 200,
          contentType: 'application/json',
          body: JSON.stringify({ success: true }),
        })
      })

      await page.goto('/settings')

      // Intercept window.confirm and accept it (simulates user clicking OK)
      await page.evaluate(() => {
        window.confirm = () => true
      })

      // Also stub window.location.href assignment so navigation doesn't break the test
      await page.evaluate(() => {
        Object.defineProperty(window, 'location', {
          writable: true,
          value: { ...window.location, href: window.location.href },
        })
      })

      const deleteButton = page.getByRole('button', { name: /delete my account/i })
      await expect(deleteButton).toBeVisible()
      await deleteButton.click()

      // Wait for the DELETE request to complete
      await page.waitForRequest('**/api/v1/compliance/gdpr/delete')

      // Confirm the correct HTTP method was used
      expect(deleteRequestMethod).toBe('DELETE')
    }
  )
})
