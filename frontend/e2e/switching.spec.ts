import { test, expect } from '@playwright/test'

test.describe('Supplier Switching Flow', () => {
  test.beforeEach(async ({ page }) => {
    // Mock suppliers API
    await page.route('**/api/v1/suppliers**', async (route) => {
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({
          suppliers: [
            {
              id: '1',
              name: 'Eversource Energy',
              avgPricePerKwh: 0.25,
              standingCharge: 0.50,
              greenEnergy: true,
              rating: 4.5,
              estimatedAnnualCost: 1200,
              tariffType: 'variable',
            },
            {
              id: '2',
              name: 'NextEra Energy',
              avgPricePerKwh: 0.22,
              standingCharge: 0.45,
              greenEnergy: true,
              rating: 4.3,
              estimatedAnnualCost: 1050,
              tariffType: 'variable',
            },
            {
              id: '3',
              name: 'United Illuminating (UI)',
              avgPricePerKwh: 0.28,
              standingCharge: 0.55,
              greenEnergy: false,
              rating: 3.8,
              estimatedAnnualCost: 1350,
              tariffType: 'fixed',
              exitFee: 50,
            },
          ],
        }),
      })
    })

    // Mock switch API
    await page.route('**/api/v1/suppliers/switch**', async (route) => {
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({
          success: true,
          referenceNumber: 'SW-12345',
          estimatedCompletionDate: new Date(
            Date.now() + 14 * 24 * 60 * 60 * 1000
          ).toISOString(),
        }),
      })
    })

    // Set up local storage with current supplier
    await page.addInitScript(() => {
      localStorage.setItem(
        'electricity-optimizer-settings',
        JSON.stringify({
          state: {
            region: 'US',
            annualUsageKwh: 10500,
            peakDemandKw: 3,
            appliances: [],
            currentSupplier: {
              id: '3',
              name: 'United Illuminating (UI)',
              avgPricePerKwh: 0.285,
              standingCharge: 0.55,
              greenEnergy: false,
              rating: 3.8,
              estimatedAnnualCost: 1350,
              tariffType: 'fixed',
              exitFee: 50,
            },
            notificationPreferences: {
              priceAlerts: true,
              optimalTimes: true,
              supplierUpdates: false,
            },
            displayPreferences: {
              currency: 'USD',
              theme: 'system',
              timeFormat: '24h',
            },
          },
          version: 0,
        })
      )
    })

    await page.goto('/suppliers')
  })

  test('displays supplier comparison', async ({ page }) => {
    // Page title
    await expect(
      page.getByRole('heading', { name: 'Compare Suppliers' })
    ).toBeVisible()

    // Supplier cards
    await expect(page.getByRole('heading', { name: 'Eversource Energy' })).toBeVisible()
    await expect(page.getByRole('heading', { name: 'NextEra Energy' })).toBeVisible()
    await expect(page.getByRole('heading', { name: 'United Illuminating (UI)' })).toBeVisible()
  })

  test('highlights cheapest supplier', async ({ page }) => {
    // NextEra should be marked as cheapest
    await expect(page.getByText('Cheapest Option')).toBeVisible()
    await expect(page.locator('[data-testid="supplier-card-2"]')).toBeVisible()
  })

  test('shows savings compared to current supplier', async ({ page }) => {
    // Should show potential savings
    await expect(page.getByText(/Save/).first()).toBeVisible()
  })

  // TODO: implement table view toggle on suppliers page
  test.skip('can switch view between grid and table', async ({ page }) => {
    // Default is grid view
    await expect(page.locator('[data-testid="supplier-card-1"]')).toBeVisible()

    // Switch to table view
    await page.getByRole('button').filter({ has: page.locator('svg') }).nth(1).click()

    // Should show table
    await expect(page.getByRole('table')).toBeVisible()
  })

  test('opens switching wizard when clicking switch button', async ({
    page,
  }) => {
    // Click switch on NextEra Energy
    await page
      .locator('[data-testid="supplier-card-2"]')
      .getByRole('button', { name: /switch/i })
      .click()

    // Wizard should open
    await expect(page.getByRole('heading', { name: 'Review Recommendation' })).toBeVisible()
  })

  test('completes full switching flow', async ({ page }) => {
    // Open wizard for NextEra Energy
    await page
      .locator('[data-testid="supplier-card-2"]')
      .getByRole('button', { name: /switch/i })
      .click()

    // Step 1: Review
    await expect(page.getByRole('heading', { name: 'Review Recommendation' })).toBeVisible()
    await expect(page.getByRole('heading', { name: 'NextEra Energy' })).toBeVisible()
    await page.getByRole('button', { name: 'Next', exact: true }).click()

    // Step 2: GDPR Consent
    await expect(page.getByRole('heading', { name: 'Data Consent' })).toBeVisible()
    await page.getByRole('checkbox', { name: /consent/i }).check()
    await page.getByRole('button', { name: 'Next', exact: true }).click()

    // Step 3: Contract Terms
    await expect(page.getByRole('heading', { name: 'Contract Terms' })).toBeVisible()
    await page.getByRole('button', { name: 'Next', exact: true }).click()

    // Step 4: Confirm
    await expect(page.getByRole('heading', { name: 'Confirm Switch' })).toBeVisible()
    await page.getByRole('button', { name: /confirm/i }).click()

    // Should close wizard after successful switch
    await expect(page.getByRole('heading', { name: 'Review Recommendation' })).not.toBeVisible()
  })

  test('requires GDPR consent to proceed', async ({ page }) => {
    // Open wizard
    await page
      .locator('[data-testid="supplier-card-2"]')
      .getByRole('button', { name: /switch/i })
      .click()

    // Go to step 2
    await page.getByRole('button', { name: 'Next', exact: true }).click()

    // Next button should be disabled without consent
    await expect(page.getByRole('button', { name: 'Next', exact: true })).toBeDisabled()

    // Check consent
    await page.getByRole('checkbox', { name: /consent/i }).check()

    // Now should be enabled
    await expect(page.getByRole('button', { name: 'Next', exact: true })).toBeEnabled()
  })

  test('can go back through wizard steps', async ({ page }) => {
    // Open wizard
    await page
      .locator('[data-testid="supplier-card-2"]')
      .getByRole('button', { name: /switch/i })
      .click()

    // Go to step 2
    await page.getByRole('button', { name: 'Next', exact: true }).click()
    await expect(page.getByRole('heading', { name: 'Data Consent' })).toBeVisible()

    // Go back
    await page.getByRole('button', { name: /back/i }).click()
    await expect(page.getByRole('heading', { name: 'Review Recommendation' })).toBeVisible()
  })

  test('can cancel switching wizard', async ({ page }) => {
    // Open wizard
    await page
      .locator('[data-testid="supplier-card-2"]')
      .getByRole('button', { name: /switch/i })
      .click()

    // Cancel
    await page.getByRole('button', { name: /cancel/i }).click()

    // Wizard should be closed
    await expect(page.getByRole('heading', { name: 'Review Recommendation' })).not.toBeVisible()
  })

  test('shows exit fee warning', async ({ page }) => {
    // Open wizard
    await page
      .locator('[data-testid="supplier-card-2"]')
      .getByRole('button', { name: /switch/i })
      .click()

    // Navigate to contract step
    await page.getByRole('button', { name: 'Next', exact: true }).click()
    await page.getByRole('checkbox', { name: /consent/i }).check()
    await page.getByRole('button', { name: 'Next', exact: true }).click()

    // Should show exit fee warning in the wizard
    const wizard = page.getByLabel('Supplier Switching Wizard')
    await expect(wizard.getByText('Exit Fee', { exact: true })).toBeVisible()
  })
})
