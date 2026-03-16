import { test, expect } from './fixtures'

test.describe('Dashboard', () => {
  test('displays dashboard with all main widgets', { tag: ['@smoke'] }, async ({ authenticatedPage: page }) => {
    await page.goto('/dashboard')

    // Dashboard title
    await expect(page.getByRole('heading', { name: 'Dashboard' })).toBeVisible()

    // Current price widget
    await expect(page.getByText('Current Price').first()).toBeVisible()
    await expect(page.getByTestId('current-price').first()).toBeVisible()

    // Total saved widget
    await expect(page.getByText('Total Saved')).toBeVisible()

    // Optimal times widget
    await expect(page.getByText('Optimal Times')).toBeVisible()

    // Suppliers widget
    await expect(page.getByRole('heading', { name: 'Top Suppliers' })).toBeVisible()
  })

  test('shows live prices and trend', { tag: ['@smoke'] }, async ({ authenticatedPage: page }) => {
    await page.goto('/dashboard')

    // Current price should be displayed
    await expect(page.getByTestId('current-price').first()).toContainText('0.25')

    // Price trend should show decreasing
    await expect(page.getByTestId('price-trend').first()).toBeVisible()
  })

  test('displays price chart with history', { tag: ['@regression'] }, async ({ authenticatedPage: page }) => {
    await page.goto('/dashboard')

    // Wait for chart to load
    await expect(page.getByText('Price History')).toBeVisible()

    // Chart container should exist
    await expect(page.getByTestId('price-chart-container')).toBeVisible()
  })

  test('shows 24-hour forecast section', { tag: ['@regression'] }, async ({ authenticatedPage: page }) => {
    await page.goto('/dashboard')

    await expect(page.getByText('24-Hour Forecast').first()).toBeVisible()
  })

  test('displays supplier comparison widget', { tag: ['@regression'] }, async ({ authenticatedPage: page }) => {
    await page.goto('/dashboard')

    await expect(page.getByText('Top Suppliers')).toBeVisible()
    await expect(page.getByRole('heading', { name: 'Eversource Energy' })).toBeVisible()
  })

  test('navigates to prices page', { tag: ['@smoke'] }, async ({ authenticatedPage: page, isMobile }) => {
    test.skip(isMobile === true, 'Mobile navigation uses different layout')
    await page.goto('/dashboard')
    await page.getByText('View all prices').click()
    await page.waitForURL(/\/prices/, { timeout: 15000 })
  })

  // Client-side navigation from dashboard to suppliers can be slow on webkit
  test('navigates to suppliers page', { tag: ['@regression'] }, async ({ authenticatedPage: page, isMobile }) => {
    test.skip(isMobile === true, 'Mobile navigation uses different layout')
    await page.goto('/dashboard')
    await page.getByRole('link', { name: 'View all', exact: true }).click()
    await page.waitForURL(/\/suppliers/, { timeout: 20000 })
  })

  // Realtime indicator has class "hidden sm:flex" — not visible on mobile viewports
  test('shows realtime indicator', { tag: ['@regression'] }, async ({ authenticatedPage: page, isMobile }) => {
    test.skip(isMobile === true, 'Realtime indicator is hidden on mobile (sm:flex)')
    await page.goto('/dashboard')
    await expect(page.getByTestId('realtime-indicator')).toBeVisible()
  })

  test('is responsive on mobile', { tag: ['@regression'] }, async ({ authenticatedPage: page }) => {
    await page.setViewportSize({ width: 375, height: 667 })
    await page.goto('/dashboard')

    // Dashboard should still load
    await expect(page.getByText('Current Price').first()).toBeVisible()

    // Sidebar should be hidden on mobile
    await expect(page.getByRole('navigation')).not.toBeVisible()
  })
})

test.describe('Dashboard Error Handling', () => {
  test('handles API errors gracefully', { tag: ['@regression'] }, async ({ authenticatedPage: page }) => {
    // Override the prices/current mock with a 500 error for this test only
    await page.route('**/api/v1/prices/current**', async (route) => {
      await route.fulfill({
        status: 500,
        contentType: 'application/json',
        body: JSON.stringify({ detail: 'Internal server error' }),
      })
    })

    await page.goto('/dashboard')

    // Dashboard should still render even with API errors
    await expect(page.getByRole('heading', { name: 'Dashboard' })).toBeVisible()
  })
})
