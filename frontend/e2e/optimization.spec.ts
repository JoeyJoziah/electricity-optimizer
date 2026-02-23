import { test, expect } from '@playwright/test'

test.describe('Load Optimization', () => {
  test.beforeEach(async ({ page }) => {
    // Mock optimization API
    await page.route('**/api/v1/optimization/schedule**', async (route) => {
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({
          schedules: [
            {
              applianceId: '1',
              applianceName: 'Washing Machine',
              scheduledStart: new Date().toISOString().replace(/T.*/, 'T02:00:00Z'),
              scheduledEnd: new Date().toISOString().replace(/T.*/, 'T04:00:00Z'),
              estimatedCost: 0.45,
              savings: 0.15,
              reason: 'Lowest price period',
            },
            {
              applianceId: '2',
              applianceName: 'Dishwasher',
              scheduledStart: new Date().toISOString().replace(/T.*/, 'T03:00:00Z'),
              scheduledEnd: new Date().toISOString().replace(/T.*/, 'T04:30:00Z'),
              estimatedCost: 0.30,
              savings: 0.10,
              reason: 'Off-peak pricing',
            },
          ],
          totalSavings: 0.25,
          totalCost: 0.75,
        }),
      })
    })

    // Mock potential savings API
    await page.route('**/api/v1/optimization/potential-savings**', async (route) => {
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({
          dailySavings: 0.25,
          weeklySavings: 1.75,
          monthlySavings: 7.50,
          annualSavings: 91.25,
        }),
      })
    })

    await page.goto('/optimize')
  })

  test('displays optimization page', async ({ page }) => {
    await expect(
      page.getByRole('heading', { name: 'Load Optimization' })
    ).toBeVisible()
  })

  test('shows empty state when no appliances', async ({ page }) => {
    await expect(page.getByText('No appliances added yet')).toBeVisible()
  })

  test('can add appliance using quick add', async ({ page }) => {
    // Click quick add for Washing Machine
    await page.getByRole('button', { name: /Washing Machine/ }).click()

    // Should now show in appliances list
    await expect(page.getByText('Washing Machine').first()).toBeVisible()
  })

  test('can add custom appliance', async ({ page }) => {
    // Fill in custom appliance form — use click + fill to ensure focus and onChange fires
    const nameInput = page.getByPlaceholder('Appliance name')
    await nameInput.click()
    await nameInput.fill('Pool Pump')

    await page.getByPlaceholder('Power (kW)').click()
    await page.getByPlaceholder('Power (kW)').fill('1.5')

    await page.getByPlaceholder('Duration (hrs)').click()
    await page.getByPlaceholder('Duration (hrs)').fill('4')

    // Wait for button to become enabled after React state update
    const addButton = page.getByRole('button', { name: /Add Appliance/ })
    await expect(addButton).toBeEnabled({ timeout: 5000 })
    await addButton.click()

    // Should appear in list
    await expect(page.getByText('Pool Pump')).toBeVisible()
  })

  // TODO: implement appliance edit mode testids (supplier-card-settings)
  test.skip('can remove appliance in edit mode', async ({ page }) => {
    await page.getByRole('button', { name: /Washing Machine/ }).click()
    await expect(page.getByText('Washing Machine').first()).toBeVisible()
    await page.locator('[data-testid="supplier-card-settings"]').first().click()
    await page.getByRole('button').filter({ has: page.locator('svg') }).last().click()
    await expect(page.getByText('No appliances added yet')).toBeVisible()
  })

  // TODO: implement schedule-block testids on ScheduleTimeline
  test.skip('runs optimization and shows results', async ({ page }) => {
    await page.getByRole('button', { name: /Washing Machine/ }).click()
    await page.getByRole('button', { name: /Dishwasher/ }).click()
    await page.getByRole('button', { name: /Optimize Now/ }).click()
    await expect(page.getByText('Optimized Schedule')).toBeVisible()
    await expect(page.getByTestId('schedule-block-1')).toBeVisible()
    await expect(page.getByText(/Total savings/i)).toBeVisible()
  })

  // TODO: implement schedule details after optimization
  test.skip('displays schedule details', async ({ page }) => {
    await page.getByRole('button', { name: /Washing Machine/ }).click()
    await page.getByRole('button', { name: /Optimize Now/ }).click()
    await expect(page.getByText('Schedule Details')).toBeVisible()
    await expect(page.getByText('Washing Machine')).toBeVisible()
    await expect(page.getByText('Lowest price period')).toBeVisible()
  })

  test('shows potential savings summary', async ({ page }) => {
    // Add appliances
    await page.getByRole('button', { name: /Washing Machine/ }).click()

    // Should show savings projections
    await expect(page.getByText('Daily Savings')).toBeVisible()
    await expect(page.getByText('Monthly Savings')).toBeVisible()
    await expect(page.getByText('Annual Savings')).toBeVisible()
  })

  test('can toggle appliance flexibility', async ({ page }) => {
    // Add an appliance
    await page.getByRole('button', { name: /Washing Machine/ }).click()

    // Find the checkbox in the appliance card
    const checkbox = page.locator('input[type="checkbox"]').first()

    // Should be checked by default (flexible)
    await expect(checkbox).toBeChecked()

    // Toggle it
    await checkbox.click()
    await expect(checkbox).not.toBeChecked()
  })

  test('shows different priority levels', async ({ page }) => {
    // Add appliances with different priorities
    await page.getByRole('button', { name: /Washing Machine/ }).click()
    await page.getByRole('button', { name: /EV Charger/ }).click()

    // Should show priority badges
    await expect(page.getByText('medium').first()).toBeVisible()
    await expect(page.getByText('high')).toBeVisible()
  })

  // TODO: implement price-zone testids on ScheduleTimeline
  test.skip('timeline shows price zones', async ({ page }) => {
    await page.getByRole('button', { name: /Washing Machine/ }).click()
    await page.getByRole('button', { name: /Optimize Now/ }).click()
    await expect(page.getByTestId('price-zone-cheap')).toBeVisible()
    await expect(page.getByTestId('price-zone-expensive')).toBeVisible()
  })
})

test.describe('Optimization Mobile', () => {
  test('is responsive on mobile', async ({ page }) => {
    await page.setViewportSize({ width: 375, height: 667 })
    await page.goto('/optimize')

    // Should still show main elements
    await expect(
      page.getByRole('heading', { name: 'Load Optimization' })
    ).toBeVisible()
    await expect(page.getByRole('heading', { name: 'Your Appliances' })).toBeVisible()
  })
})
