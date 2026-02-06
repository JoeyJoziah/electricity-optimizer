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
            region: 'UK',
            annualUsageKwh: 2900,
            peakDemandKw: 3,
            appliances: [],
            currentSupplier: {
              id: '3',
              name: 'British Gas',
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
              name: 'Octopus Energy',
              avgPricePerKwh: 0.25,
              standingCharge: 0.50,
              greenEnergy: true,
              rating: 4.5,
              estimatedAnnualCost: 1200,
              tariffType: 'variable',
              features: ['Smart tariffs', 'App control', '100% renewable'],
            },
            {
              id: '2',
              name: 'Bulb Energy',
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
              name: 'British Gas',
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
              name: 'EDF Energy',
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

  test('user can switch supplier with GDPR consent', async ({ page }) => {
    await page.goto('/suppliers')

    // Verify supplier comparison table loads
    await expect(page.getByRole('heading', { name: 'Compare Suppliers' })).toBeVisible()
    await expect(page.getByText('Current Supplier')).toBeVisible()
    await expect(page.getByText('British Gas')).toBeVisible()

    // Find recommended supplier
    await expect(page.getByText('Recommended')).toBeVisible()
    await expect(page.getByText('Bulb Energy')).toBeVisible()

    // Click switch on recommended supplier
    await page
      .locator('[data-testid="supplier-card-2"]')
      .getByRole('button', { name: /switch/i })
      .click()

    // Step 1: Review recommendation
    await expect(page.getByText('Review Recommendation')).toBeVisible()
    await expect(page.getByText('Estimated Savings')).toBeVisible()

    // Calculate savings (1350 - 1050 = 300)
    await expect(page.getByText(/300/)).toBeVisible()
    await page.click('button:has-text("Continue")')

    // Step 2: GDPR consent
    await expect(page.getByText('Data Processing Consent')).toBeVisible()
    await expect(page.getByText(/your data will be shared/i)).toBeVisible()

    // Check required consents
    await page.check('[name="gdpr_consent"]')
    await page.check('[name="data_sharing_consent"]')

    // Optional marketing consent
    await page.check('[name="marketing_consent"]')

    await page.click('button:has-text("I Consent")')

    // Step 3: Contract review
    await expect(page.getByText('Contract Terms')).toBeVisible()
    await expect(page.getByText('Exit Fee: £25.00')).toBeVisible()
    await expect(page.getByText('Contract Length: 12 months')).toBeVisible()
    await expect(page.getByText('Cooling Off Period: 14 days')).toBeVisible()

    // Must acknowledge terms
    await page.check('[name="accept_terms"]')
    await page.click('button:has-text("Accept Terms")')

    // Step 4: Confirmation
    await expect(page.getByText('Confirm Switch')).toBeVisible()
    await expect(page.getByText('Bulb Energy')).toBeVisible()
    await expect(page.getByText(/confirm your switch/i)).toBeVisible()

    await page.click('button:has-text("Confirm Switch")')

    // Verify success
    await expect(page.getByText('Switching in Progress')).toBeVisible()
    await expect(page.getByText('SW-2024-12345')).toBeVisible()
    await expect(page.getByText(/Estimated completion: 24 hours/i)).toBeVisible()
    await expect(page.getByText('Confirmation email sent')).toBeVisible()
  })

  test('shows savings comparison with current supplier', async ({ page }) => {
    await page.goto('/suppliers')

    // Each supplier card should show savings vs current
    await expect(page.getByText(/Save £150\/year/)).toBeVisible() // Octopus
    await expect(page.getByText(/Save £300\/year/)).toBeVisible() // Bulb
  })

  test('filters suppliers by green energy', async ({ page }) => {
    await page.goto('/suppliers')

    // Toggle green energy filter
    await page.click('[data-testid="filter-green-energy"]')

    // Should only show green suppliers
    await expect(page.getByText('Octopus Energy')).toBeVisible()
    await expect(page.getByText('Bulb Energy')).toBeVisible()
    await expect(page.getByText('British Gas')).not.toBeVisible()
    await expect(page.getByText('EDF Energy')).not.toBeVisible()
  })

  test('sorts suppliers by price', async ({ page }) => {
    await page.goto('/suppliers')

    // Click sort by price
    await page.click('[data-testid="sort-by-price"]')

    // First supplier should be cheapest (Bulb at £1,050)
    const firstCard = page.locator('[data-testid^="supplier-card"]').first()
    await expect(firstCard).toContainText('Bulb Energy')
  })

  test('sorts suppliers by rating', async ({ page }) => {
    await page.goto('/suppliers')

    await page.click('[data-testid="sort-by-rating"]')

    // First supplier should be highest rated (Octopus at 4.5)
    const firstCard = page.locator('[data-testid^="supplier-card"]').first()
    await expect(firstCard).toContainText('Octopus Energy')
  })

  test('shows supplier details on click', async ({ page }) => {
    await page.goto('/suppliers')

    // Click on supplier card (not switch button)
    await page.locator('[data-testid="supplier-card-1"]').click()

    // Should show expanded details
    await expect(page.getByText('Smart tariffs')).toBeVisible()
    await expect(page.getByText('App control')).toBeVisible()
    await expect(page.getByText('100% renewable')).toBeVisible()
  })

  test('displays current supplier badge', async ({ page }) => {
    await page.goto('/suppliers')

    // British Gas should have current supplier badge
    const currentSupplierCard = page.locator('[data-testid="supplier-card-3"]')
    await expect(currentSupplierCard.getByText('Current')).toBeVisible()
  })

  test('shows exit fee warning when switching from fixed tariff', async ({ page }) => {
    await page.goto('/suppliers')

    await page
      .locator('[data-testid="supplier-card-2"]')
      .getByRole('button', { name: /switch/i })
      .click()

    // Navigate to contract step
    await page.click('button:has-text("Continue")')
    await page.check('[name="gdpr_consent"]')
    await page.check('[name="data_sharing_consent"]')
    await page.click('button:has-text("I Consent")')

    // Should show exit fee warning
    await expect(page.getByText(/exit fee/i)).toBeVisible()
    await expect(page.getByText(/£50/)).toBeVisible()
    await expect(page.getByText(/current contract/i)).toBeVisible()
  })

  test('calculates net savings including exit fee', async ({ page }) => {
    await page.goto('/suppliers')

    await page
      .locator('[data-testid="supplier-card-2"]')
      .getByRole('button', { name: /switch/i })
      .click()

    // In review step, should show net savings (£300 - £50 exit fee = £250)
    await expect(page.getByText(/Net savings after exit fee/i)).toBeVisible()
    await expect(page.getByText(/£250/)).toBeVisible()
  })

  test('prevents switching without required consents', async ({ page }) => {
    await page.goto('/suppliers')

    await page
      .locator('[data-testid="supplier-card-2"]')
      .getByRole('button', { name: /switch/i })
      .click()

    await page.click('button:has-text("Continue")')

    // Try to proceed without checking required consents
    const nextButton = page.getByRole('button', { name: /consent/i })
    await expect(nextButton).toBeDisabled()

    // Check only one required consent
    await page.check('[name="gdpr_consent"]')
    await expect(nextButton).toBeDisabled()

    // Check second required consent
    await page.check('[name="data_sharing_consent"]')
    await expect(nextButton).toBeEnabled()
  })

  test('email confirmation is sent after switch', async ({ page }) => {
    await page.goto('/suppliers')

    // Complete full switch flow
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

    // Verify email confirmation
    await expect(page.getByText(/confirmation email sent/i)).toBeVisible()
    await expect(page.getByText('test@example.com')).toBeVisible()
  })

  test('can cancel switch at any step', async ({ page }) => {
    await page.goto('/suppliers')

    await page
      .locator('[data-testid="supplier-card-2"]')
      .getByRole('button', { name: /switch/i })
      .click()

    // At step 1, cancel
    await page.click('button:has-text("Cancel")')

    // Wizard should close
    await expect(page.getByText('Review Recommendation')).not.toBeVisible()

    // Start again and go to step 2
    await page
      .locator('[data-testid="supplier-card-2"]')
      .getByRole('button', { name: /switch/i })
      .click()
    await page.click('button:has-text("Continue")')

    // Cancel at step 2
    await page.click('button:has-text("Cancel")')
    await expect(page.getByText('Data Processing Consent')).not.toBeVisible()
  })

  test('shows cooling off period information', async ({ page }) => {
    await page.goto('/suppliers')

    await page
      .locator('[data-testid="supplier-card-2"]')
      .getByRole('button', { name: /switch/i })
      .click()

    // Navigate to contract step
    await page.click('button:has-text("Continue")')
    await page.check('[name="gdpr_consent"]')
    await page.check('[name="data_sharing_consent"]')
    await page.click('button:has-text("I Consent")')

    // Should show cooling off info
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

  test('can toggle between grid and table view', async ({ page }) => {
    await page.goto('/suppliers')

    // Default is grid view
    await expect(page.locator('[data-testid="supplier-grid"]')).toBeVisible()

    // Switch to table view
    await page.click('[data-testid="view-toggle-table"]')
    await expect(page.getByRole('table')).toBeVisible()

    // Switch back to grid
    await page.click('[data-testid="view-toggle-grid"]')
    await expect(page.locator('[data-testid="supplier-grid"]')).toBeVisible()
  })

  test('table shows all supplier details', async ({ page }) => {
    await page.goto('/suppliers')

    await page.click('[data-testid="view-toggle-table"]')

    // Table headers
    await expect(page.getByRole('columnheader', { name: /supplier/i })).toBeVisible()
    await expect(page.getByRole('columnheader', { name: /price/i })).toBeVisible()
    await expect(page.getByRole('columnheader', { name: /rating/i })).toBeVisible()
    await expect(page.getByRole('columnheader', { name: /annual cost/i })).toBeVisible()
  })
})
