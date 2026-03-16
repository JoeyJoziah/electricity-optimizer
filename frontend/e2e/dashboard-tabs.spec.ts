import { test, expect, PRESET_MULTI_UTILITY } from './fixtures'

test.describe('Dashboard Tabs', () => {
  // This describe block needs a multi-utility user so the tabs appear
  test.use({ settingsPreset: PRESET_MULTI_UTILITY })

  test('All Utilities tab is active by default for multi-utility user', { tag: ['@smoke'] }, async ({ authenticatedPage: page }) => {
    await page.goto('/dashboard')
    await expect(page.getByTestId('dashboard-tabs')).toBeVisible()

    const allTab = page.getByTestId('tab-all')
    await expect(allTab).toBeVisible()
    await expect(allTab).toHaveAttribute('aria-selected', 'true')
  })

  test('clicking Electricity tab updates URL and content', { tag: ['@regression'] }, async ({ authenticatedPage: page }) => {
    await page.goto('/dashboard')
    await expect(page.getByTestId('dashboard-tabs')).toBeVisible()

    const electricityTab = page.getByTestId('tab-electricity')
    await expect(electricityTab).toBeVisible()
    await electricityTab.click()

    // URL should update with tab param
    await expect(page).toHaveURL(/tab=electricity/)

    // Electricity tab should now be selected
    await expect(electricityTab).toHaveAttribute('aria-selected', 'true')

    // All tab should no longer be selected
    await expect(page.getByTestId('tab-all')).toHaveAttribute('aria-selected', 'false')
  })

  test('direct navigation to tab via URL param', { tag: ['@regression'] }, async ({ authenticatedPage: page }) => {
    await page.goto('/dashboard?tab=natural_gas')
    await expect(page.getByTestId('dashboard-tabs')).toBeVisible()

    const gasTab = page.getByTestId('tab-natural_gas')
    await expect(gasTab).toHaveAttribute('aria-selected', 'true')

    // All tab should not be selected
    await expect(page.getByTestId('tab-all')).toHaveAttribute('aria-selected', 'false')
  })
})
