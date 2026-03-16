import { test, expect } from './fixtures'

// ---------------------------------------------------------------------------
// Supplier Switching Flow
//
// Uses authenticatedPage with a custom settings preset that stores a current
// supplier (United Illuminating) in localStorage. The region is 'US' (not
// 'US_CT') to match the original test's switching scenario. Two additional
// mocks are registered inline:
//   - suppliers (3 specific suppliers with exit fee data)
//   - suppliers/switch (successful switch response)
// These are not in the shared factory so they remain as inline route mocks.
// ---------------------------------------------------------------------------

test.use({
  settingsPreset: {
    region: 'US',
    annualUsageKwh: 10500,
    peakDemandKw: 3,
    displayPreferences: {
      currency: 'USD',
      theme: 'system',
      timeFormat: '24h',
    },
  },
})

const SWITCHING_SUPPLIERS = [
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
]

test.describe('Supplier Switching Flow', () => {
  // Common setup shared across all tests: override suppliers + switch mocks,
  // override localStorage to include current supplier, then navigate to /suppliers.
  // The authenticatedPage fixture already handles auth + base API mocks.

  async function setupSwitchingPage(page: import('@playwright/test').Page) {
    // Override suppliers with the three suppliers used in switching tests
    await page.route('**/api/v1/suppliers**', async (route) => {
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({ suppliers: SWITCHING_SUPPLIERS }),
      })
    })

    // Mock switch API (not in shared factory)
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

    // Inject current supplier into localStorage (augments the fixture's preset)
    await page.addInitScript(() => {
      const key = 'electricity-optimizer-settings'
      const raw = localStorage.getItem(key)
      const existing = raw ? JSON.parse(raw) : { state: {} }
      existing.state.appliances = []
      existing.state.currentSupplier = {
        id: '3',
        name: 'United Illuminating (UI)',
        avgPricePerKwh: 0.285,
        standingCharge: 0.55,
        greenEnergy: false,
        rating: 3.8,
        estimatedAnnualCost: 1350,
        tariffType: 'fixed',
        exitFee: 50,
      }
      existing.state.notificationPreferences = {
        priceAlerts: true,
        optimalTimes: true,
        supplierUpdates: false,
      }
      existing.version = 0
      localStorage.setItem(key, JSON.stringify(existing))
    })

    await page.goto('/suppliers')
  }

  test('displays supplier comparison', { tag: ['@smoke'] }, async ({ authenticatedPage: page }) => {
    await setupSwitchingPage(page)

    // Page title
    await expect(
      page.getByRole('heading', { name: 'Compare Suppliers' })
    ).toBeVisible()

    // Supplier cards
    await expect(page.getByRole('heading', { name: 'Eversource Energy' })).toBeVisible()
    await expect(page.getByRole('heading', { name: 'NextEra Energy' })).toBeVisible()
    await expect(page.getByRole('heading', { name: 'United Illuminating (UI)' })).toBeVisible()
  })

  test('highlights cheapest supplier', { tag: ['@regression'] }, async ({ authenticatedPage: page }) => {
    await setupSwitchingPage(page)

    // NextEra should be marked as cheapest
    await expect(page.getByText('Cheapest Option')).toBeVisible()
    await expect(page.locator('[data-testid="supplier-card-2"]')).toBeVisible()
  })

  test('shows savings compared to current supplier', { tag: ['@regression'] }, async ({ authenticatedPage: page }) => {
    await setupSwitchingPage(page)

    // Should show potential savings
    await expect(page.getByText(/Save/).first()).toBeVisible()
  })

  test('can switch view between grid and table', { tag: ['@regression'] }, async ({ authenticatedPage: page }) => {
    await setupSwitchingPage(page)

    // Default is grid view
    await expect(page.locator('[data-testid="supplier-card-1"]')).toBeVisible()

    // Switch to table view
    await page.getByRole('button', { name: /table view/i }).click()

    // Should show table
    await expect(page.getByRole('table')).toBeVisible()
  })

  test('opens switching wizard when clicking switch button', { tag: ['@smoke'] }, async ({ authenticatedPage: page }) => {
    await setupSwitchingPage(page)

    // Click switch on NextEra Energy
    await page
      .locator('[data-testid="supplier-card-2"]')
      .getByRole('button', { name: /switch/i })
      .click()

    // Wizard should open
    await expect(page.getByRole('heading', { name: 'Review Recommendation' })).toBeVisible()
  })

  test('completes full switching flow', { tag: ['@smoke'] }, async ({ authenticatedPage: page }) => {
    await setupSwitchingPage(page)

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

  test('requires GDPR consent to proceed', { tag: ['@regression'] }, async ({ authenticatedPage: page }) => {
    await setupSwitchingPage(page)

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

  test('can go back through wizard steps', { tag: ['@regression'] }, async ({ authenticatedPage: page }) => {
    await setupSwitchingPage(page)

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

  test('can cancel switching wizard', { tag: ['@regression'] }, async ({ authenticatedPage: page }) => {
    await setupSwitchingPage(page)

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

  test('shows exit fee warning', { tag: ['@regression'] }, async ({ authenticatedPage: page }) => {
    await setupSwitchingPage(page)

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
