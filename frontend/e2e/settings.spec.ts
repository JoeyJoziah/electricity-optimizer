import { test, expect } from './fixtures'

test.describe('Settings Page', () => {
  test('displays settings page with all sections', { tag: ['@smoke'] }, async ({ authenticatedPage: page }) => {
    await page.goto('/settings')
    await expect(page).toHaveURL(/\/settings/)

    // Should show main settings sections — use exact match to avoid
    // matching "Electricity Optimizer" in the sidebar (hidden on mobile)
    await expect(page.getByText(/region/i).first()).toBeVisible()
    await expect(page.getByText('Electricity', { exact: true })).toBeVisible()
  })

  test('shows utility type checkboxes', { tag: ['@regression'] }, async ({ authenticatedPage: page }) => {
    await page.goto('/settings')

    // Utility type options should be present
    // Use { exact: true } to avoid matching "Electricity Optimizer" in sidebar
    await expect(page.getByText('Electricity', { exact: true })).toBeVisible()
    await expect(page.getByText('Natural Gas')).toBeVisible()
    await expect(page.getByText('Heating Oil')).toBeVisible()
    await expect(page.getByText('Propane')).toBeVisible()
    await expect(page.getByText('Community Solar')).toBeVisible()
  })

  test('has save button', { tag: ['@smoke'] }, async ({ authenticatedPage: page }) => {
    await page.goto('/settings')

    const saveButton = page.getByRole('button', { name: /save/i })
    await expect(saveButton).toBeVisible()
  })

  test('shows notification preferences', { tag: ['@regression'] }, async ({ authenticatedPage: page }) => {
    await page.goto('/settings')

    await expect(page.getByText(/notification/i).first()).toBeVisible()
  })

  test('save shows confirmation', { tag: ['@regression'] }, async ({ authenticatedPage: page }) => {
    await page.goto('/settings')

    const saveButton = page.getByRole('button', { name: /save/i })
    await saveButton.click()

    // Should show saved confirmation
    await expect(page.getByText(/saved/i)).toBeVisible({ timeout: 3000 })
  })
})
