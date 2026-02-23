import { test, expect } from '@playwright/test'

test.describe('Full Supplier Switching Flow', () => {
  test.beforeEach(async ({ page }) => {
    // Set up authenticated state with current supplier
    await page.addInitScript(() => {
      localStorage.setItem('auth_token', 'mock_jwt_token')
      localStorage.setItem('user', JSON.stringify({
        id: 'user_123',
        email: 'test@example.com',
        onboarding_completed: true,
      }))
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
              avgPricePerKwh: 0.28,
              standingCharge: 0.55,
              greenEnergy: false,
              rating: 3.8,
              estimatedAnnualCost: 1350,
              tariffType: 'fixed',
              exitFee: 50,
            },
          },
        })
      )
    })

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
              tariffType: 'time_of_use',
              features: ['Smart tariffs', 'App control', '100% renewable'],
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
              features: ['Green energy', 'Simple pricing'],
              recommended: true,
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
              current: true,
            },
            {
              id: '4',
              name: 'Town Utility',
              avgPricePerKwh: 0.26,
              standingCharge: 0.52,
              greenEnergy: false,
              rating: 3.9,
              estimatedAnnualCost: 1280,
              tariffType: 'fixed',
            },
          ],
        }),
      })
    })

    // Mock switch API
    await page.route('**/api/v1/suppliers/switch', async (route) => {
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({
          success: true,
          referenceNumber: 'SW-2024-12345',
          estimatedCompletionDate: new Date(
            Date.now() + 24 * 60 * 60 * 1000
          ).toISOString(),
          confirmationEmailSent: true,
        }),
      })
    })

    // Mock contract terms API
    await page.route('**/api/v1/suppliers/*/contract-terms', async (route) => {
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({
          contractLength: 12,
          exitFee: 25,
          priceGuarantee: 'Variable rate',
          cancellationPeriod: 14,
          billingFrequency: 'Monthly',
          paymentMethods: ['Direct Debit', 'Card'],
        }),
      })
    })
  })

  test('suppliers page loads with comparison heading', async ({ page }) => {
    await page.goto('/suppliers')

    await expect(page.getByRole('heading', { name: 'Compare Suppliers' })).toBeVisible()
  })

  test('shows current supplier info', async ({ page }) => {
    await page.goto('/suppliers')

    await expect(page.getByText('Your Current')).toBeVisible()
  })

  // TODO: implement supplier-card testids and multi-step switching wizard
  test.skip('user can switch supplier with GDPR consent', async ({ page }) => {
    await page.goto('/suppliers')
    await expect(page.getByRole('heading', { name: 'Compare Suppliers' })).toBeVisible()
    await expect(page.getByText('Current Supplier')).toBeVisible()
    await expect(page.getByText('United Illuminating (UI)')).toBeVisible()
    await expect(page.getByText('Recommended')).toBeVisible()
    await expect(page.getByText('NextEra Energy')).toBeVisible()
    await page
      .locator('[data-testid="supplier-card-2"]')
      .getByRole('button', { name: /switch/i })
      .click()
    await expect(page.getByText('Review Recommendation')).toBeVisible()
    await expect(page.getByText('Estimated Savings')).toBeVisible()
    await expect(page.getByText(/300/)).toBeVisible()
    await page.click('button:has-text("Continue")')
    await expect(page.getByText('Data Processing Consent')).toBeVisible()
    await page.check('[name="gdpr_consent"]')
    await page.check('[name="data_sharing_consent"]')
    await page.check('[name="marketing_consent"]')
    await page.click('button:has-text("I Consent")')
    await expect(page.getByText('Contract Terms')).toBeVisible()
    await page.check('[name="accept_terms"]')
    await page.click('button:has-text("Accept Terms")')
    await expect(page.getByText('Confirm Switch')).toBeVisible()
    await page.click('button:has-text("Confirm Switch")')
    await expect(page.getByText('Switching in Progress')).toBeVisible()
    await expect(page.getByText('SW-2024-12345')).toBeVisible()
  })

  // TODO: implement per-supplier savings display
  test.skip('shows savings comparison with current supplier', async ({ page }) => {
    await page.goto('/suppliers')
    await expect(page.getByText(/Save \$150\/year/)).toBeVisible()
    await expect(page.getByText(/Save \$300\/year/)).toBeVisible()
  })

  // TODO: implement filter-green-energy testid
  test.skip('filters suppliers by green energy', async ({ page }) => {
    await page.goto('/suppliers')
    await page.click('[data-testid="filter-green-energy"]')
    await expect(page.getByText('Eversource Energy')).toBeVisible()
    await expect(page.getByText('NextEra Energy')).toBeVisible()
    await expect(page.getByText('United Illuminating (UI)')).not.toBeVisible()
  })

  // TODO: implement sort-by-price testid
  test.skip('sorts suppliers by price', async ({ page }) => {
    await page.goto('/suppliers')
    await page.click('[data-testid="sort-by-price"]')
    const firstCard = page.locator('[data-testid^="supplier-card"]').first()
    await expect(firstCard).toContainText('NextEra Energy')
  })

  // TODO: implement sort-by-rating testid
  test.skip('sorts suppliers by rating', async ({ page }) => {
    await page.goto('/suppliers')
    await page.click('[data-testid="sort-by-rating"]')
    const firstCard = page.locator('[data-testid^="supplier-card"]').first()
    await expect(firstCard).toContainText('Eversource Energy')
  })

  // TODO: implement supplier-card click to expand details
  test.skip('shows supplier details on click', async ({ page }) => {
    await page.goto('/suppliers')
    await page.locator('[data-testid="supplier-card-1"]').click()
    await expect(page.getByText('Smart tariffs')).toBeVisible()
    await expect(page.getByText('App control')).toBeVisible()
    await expect(page.getByText('100% renewable')).toBeVisible()
  })

  // TODO: implement supplier-card testids
  test.skip('displays current supplier badge', async ({ page }) => {
    await page.goto('/suppliers')
    const currentSupplierCard = page.locator('[data-testid="supplier-card-3"]')
    await expect(currentSupplierCard.getByText('Current')).toBeVisible()
  })

  // TODO: implement multi-step switching wizard with Continue button
  test.skip('shows exit fee warning when switching from fixed tariff', async ({ page }) => {
    await page.goto('/suppliers')
    await page
      .locator('[data-testid="supplier-card-2"]')
      .getByRole('button', { name: /switch/i })
      .click()
    await page.click('button:has-text("Continue")')
    await page.check('[name="gdpr_consent"]')
    await page.check('[name="data_sharing_consent"]')
    await page.click('button:has-text("I Consent")')
    await expect(page.getByText(/exit fee/i)).toBeVisible()
    await expect(page.getByText(/\$50/)).toBeVisible()
  })

  // TODO: implement net savings calculation display
  test.skip('calculates net savings including exit fee', async ({ page }) => {
    await page.goto('/suppliers')
    await page
      .locator('[data-testid="supplier-card-2"]')
      .getByRole('button', { name: /switch/i })
      .click()
    await expect(page.getByText(/Net savings after exit fee/i)).toBeVisible()
    await expect(page.getByText(/\$250/)).toBeVisible()
  })

  // TODO: implement multi-step switching wizard with consent validation
  test.skip('prevents switching without required consents', async ({ page }) => {
    await page.goto('/suppliers')
    await page
      .locator('[data-testid="supplier-card-2"]')
      .getByRole('button', { name: /switch/i })
      .click()
    await page.click('button:has-text("Continue")')
    const nextButton = page.getByRole('button', { name: /consent/i })
    await expect(nextButton).toBeDisabled()
    await page.check('[name="gdpr_consent"]')
    await expect(nextButton).toBeDisabled()
    await page.check('[name="data_sharing_consent"]')
    await expect(nextButton).toBeEnabled()
  })

  // TODO: implement email confirmation display after switch
  test.skip('email confirmation is sent after switch', async ({ page }) => {
    await page.goto('/suppliers')
    await page
      .locator('[data-testid="supplier-card-2"]')
      .getByRole('button', { name: /switch/i })
      .click()
    await page.click('button:has-text("Continue")')
    await page.check('[name="gdpr_consent"]')
    await page.check('[name="data_sharing_consent"]')
    await page.click('button:has-text("I Consent")')
    await page.check('[name="accept_terms"]')
    await page.click('button:has-text("Accept Terms")')
    await page.click('button:has-text("Confirm Switch")')
    await expect(page.getByText(/confirmation email sent/i)).toBeVisible()
    await expect(page.getByText('test@example.com')).toBeVisible()
  })

  // TODO: implement multi-step wizard cancel flow
  test.skip('can cancel switch at any step', async ({ page }) => {
    await page.goto('/suppliers')
    await page
      .locator('[data-testid="supplier-card-2"]')
      .getByRole('button', { name: /switch/i })
      .click()
    await page.click('button:has-text("Cancel")')
    await expect(page.getByText('Review Recommendation')).not.toBeVisible()
  })

  // TODO: implement cooling off period display
  test.skip('shows cooling off period information', async ({ page }) => {
    await page.goto('/suppliers')
    await page
      .locator('[data-testid="supplier-card-2"]')
      .getByRole('button', { name: /switch/i })
      .click()
    await page.click('button:has-text("Continue")')
    await page.check('[name="gdpr_consent"]')
    await page.check('[name="data_sharing_consent"]')
    await page.click('button:has-text("I Consent")')
    await expect(page.getByText(/14 days/i)).toBeVisible()
    await expect(page.getByText(/cooling off period/i)).toBeVisible()
  })
})

test.describe('Supplier Comparison Table', () => {
  test.beforeEach(async ({ page }) => {
    await page.addInitScript(() => {
      localStorage.setItem('auth_token', 'mock_jwt_token')
      localStorage.setItem('user', JSON.stringify({ id: 'user_123' }))
    })

    await page.route('**/api/v1/suppliers**', async (route) => {
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({
          suppliers: [
            { id: '1', name: 'Supplier A', avgPricePerKwh: 0.25, rating: 4.5, estimatedAnnualCost: 1200 },
            { id: '2', name: 'Supplier B', avgPricePerKwh: 0.22, rating: 4.0, estimatedAnnualCost: 1050 },
          ],
        }),
      })
    })
  })

  // TODO: implement supplier-grid and view-toggle testids
  test.skip('can toggle between grid and table view', async ({ page }) => {
    await page.goto('/suppliers')
    await expect(page.locator('[data-testid="supplier-grid"]')).toBeVisible()
    await page.click('[data-testid="view-toggle-table"]')
    await expect(page.getByRole('table')).toBeVisible()
    await page.click('[data-testid="view-toggle-grid"]')
    await expect(page.locator('[data-testid="supplier-grid"]')).toBeVisible()
  })

  // TODO: implement view-toggle-table testid
  test.skip('table shows all supplier details', async ({ page }) => {
    await page.goto('/suppliers')
    await page.click('[data-testid="view-toggle-table"]')
    await expect(page.getByRole('columnheader', { name: /supplier/i })).toBeVisible()
    await expect(page.getByRole('columnheader', { name: /price/i })).toBeVisible()
    await expect(page.getByRole('columnheader', { name: /rating/i })).toBeVisible()
    await expect(page.getByRole('columnheader', { name: /annual cost/i })).toBeVisible()
  })
})
