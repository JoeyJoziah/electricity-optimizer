import { test, expect } from './fixtures'

const OPTIMIZATION_SCHEDULE = {
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
}

const POTENTIAL_SAVINGS = {
  dailySavings: 0.25,
  weeklySavings: 1.75,
  monthlySavings: 7.50,
  annualSavings: 91.25,
}

test.describe('Load Optimization', () => {
  test.use({
    apiMockConfig: {
      optimization: OPTIMIZATION_SCHEDULE,
    },
  })

  // The optimization page also needs a potential-savings route that the shared
  // factory does not cover — register it inline for all tests via beforeEach
  test.beforeEach(async ({ authenticatedPage: page }) => {
    await page.route('**/api/v1/optimization/potential-savings**', async (route) => {
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify(POTENTIAL_SAVINGS),
      })
    })

    await page.goto('/optimize')
  })

  test('displays optimization page', { tag: ['@smoke'] }, async ({ authenticatedPage: page }) => {
    await expect(
      page.getByRole('heading', { name: 'Load Optimization' })
    ).toBeVisible()
  })

  test('shows empty state when no appliances', { tag: ['@smoke'] }, async ({ authenticatedPage: page }) => {
    await expect(page.getByText('No appliances added yet')).toBeVisible()
  })

  test('can add appliance using quick add', { tag: ['@regression'] }, async ({ authenticatedPage: page }) => {
    // Click quick add for Washing Machine
    await page.getByRole('button', { name: /Washing Machine/ }).click()

    // Should now show in appliances list
    await expect(page.getByText('Washing Machine').first()).toBeVisible()
  })

  test('can add custom appliance', { tag: ['@regression'] }, async ({ authenticatedPage: page }) => {
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

  test('can remove appliance in edit mode', { tag: ['@regression'] }, async ({ authenticatedPage: page }) => {
    // Add an appliance first
    await page.getByRole('button', { name: /Washing Machine/ }).click()
    await expect(page.getByText('Washing Machine').first()).toBeVisible()

    // Click the settings/edit toggle button to enter edit mode
    await page.locator('[data-testid="appliance-card-settings"]').first().click()

    // Wait for edit mode UI to appear — the Trash2 button has an SVG with
    // the text-danger-500 class. Find the button containing it.
    const trashButton = page.locator('button').filter({ has: page.locator('.text-danger-500') })
    await expect(trashButton).toBeVisible({ timeout: 5000 })
    await trashButton.click()

    // The appliance should be removed, showing the empty state
    await expect(page.getByText('No appliances added yet')).toBeVisible()
  })

  test('runs optimization and shows results', { tag: ['@smoke'] }, async ({ authenticatedPage: page }) => {
    await page.getByRole('button', { name: /Washing Machine/ }).click()
    await page.getByRole('button', { name: /Dishwasher/ }).click()
    await page.getByRole('button', { name: /Optimize Now/ }).click()
    await expect(page.getByText('Optimized Schedule')).toBeVisible()
    await expect(page.getByTestId('schedule-block-1')).toBeVisible()
    // Use .first() because "Total savings" text appears in both the summary card
    // ("Total savings today") and potentially in other elements
    await expect(page.getByText(/Total savings/i).first()).toBeVisible()
  })

  test('displays schedule details', { tag: ['@regression'] }, async ({ authenticatedPage: page }) => {
    await page.getByRole('button', { name: /Washing Machine/ }).click()
    await page.getByRole('button', { name: /Optimize Now/ }).click()
    await expect(page.getByText('Schedule Details')).toBeVisible()
    await expect(page.getByText('Washing Machine').first()).toBeVisible()
    await expect(page.getByText('Lowest price period')).toBeVisible()
  })

  test('shows potential savings summary', { tag: ['@regression'] }, async ({ authenticatedPage: page }) => {
    // Add appliances
    await page.getByRole('button', { name: /Washing Machine/ }).click()

    // Should show savings projections
    await expect(page.getByText('Daily Savings')).toBeVisible()
    await expect(page.getByText('Monthly Savings')).toBeVisible()
    await expect(page.getByText('Annual Savings')).toBeVisible()
  })

  test('can toggle appliance flexibility', { tag: ['@regression'] }, async ({ authenticatedPage: page }) => {
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

  test('shows different priority levels', { tag: ['@regression'] }, async ({ authenticatedPage: page }) => {
    // Add appliances with different priorities
    await page.getByRole('button', { name: /Washing Machine/ }).click()
    await page.getByRole('button', { name: /EV Charger/ }).click()

    // Should show priority badges
    await expect(page.getByText('medium').first()).toBeVisible()
    await expect(page.getByText('high')).toBeVisible()
  })

  test('timeline shows price zones', { tag: ['@regression'] }, async ({ authenticatedPage: page }) => {
    await page.getByRole('button', { name: /Washing Machine/ }).click()
    await page.getByRole('button', { name: /Optimize Now/ }).click()
    await expect(page.getByTestId('price-zone-cheap')).toBeVisible()
    await expect(page.getByTestId('price-zone-expensive')).toBeVisible()
  })
})

test.describe('Optimization Mobile', () => {
  test('is responsive on mobile', { tag: ['@regression'] }, async ({ authenticatedPage: page }) => {
    await page.route('**/api/v1/optimization/potential-savings**', async (route) => {
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({ dailySavings: 0, weeklySavings: 0, monthlySavings: 0, annualSavings: 0 }),
      })
    })

    await page.setViewportSize({ width: 375, height: 667 })
    await page.goto('/optimize')

    // Should still show main elements
    await expect(
      page.getByRole('heading', { name: 'Load Optimization' })
    ).toBeVisible()
    await expect(page.getByRole('heading', { name: 'Your Appliances' })).toBeVisible()
  })
})
