import { test, expect } from '@playwright/test'
import { mockBetterAuth, setAuthenticatedState } from './helpers/auth'

test.describe('Settings Page', () => {
  test.beforeEach(async ({ page }) => {
    await mockBetterAuth(page)
    await setAuthenticatedState(page)

    // Mock backend user/settings endpoints
    await page.route('**/api/v1/user/me', async (route) => {
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({
          id: 'user_e2e_123',
          email: 'test@example.com',
          name: 'Test User',
          region: 'us_ct',
          subscription_tier: 'free',
        }),
      })
    })
  })

  test('displays settings page with all sections', async ({ page }) => {
    await page.goto('/settings')
    await expect(page).toHaveURL(/\/settings/)

    // Should show main settings sections
    await expect(page.getByText(/region/i).first()).toBeVisible()
    await expect(page.getByText(/electricity/i).first()).toBeVisible()
  })

  test('shows utility type checkboxes', async ({ page }) => {
    await page.goto('/settings')

    // Utility type options should be present
    await expect(page.getByText('Electricity')).toBeVisible()
    await expect(page.getByText('Natural Gas')).toBeVisible()
    await expect(page.getByText('Heating Oil')).toBeVisible()
    await expect(page.getByText('Propane')).toBeVisible()
    await expect(page.getByText('Community Solar')).toBeVisible()
  })

  test('has save button', async ({ page }) => {
    await page.goto('/settings')

    const saveButton = page.getByRole('button', { name: /save/i })
    await expect(saveButton).toBeVisible()
  })

  test('shows notification preferences', async ({ page }) => {
    await page.goto('/settings')

    await expect(page.getByText(/notification/i).first()).toBeVisible()
  })

  test('save shows confirmation', async ({ page }) => {
    await page.goto('/settings')

    const saveButton = page.getByRole('button', { name: /save/i })
    await saveButton.click()

    // Should show saved confirmation
    await expect(page.getByText(/saved/i)).toBeVisible({ timeout: 3000 })
  })
})
