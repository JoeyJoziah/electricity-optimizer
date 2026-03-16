import { test, expect } from './fixtures'

/**
 * Onboarding Wizard E2E Tests
 *
 * Tests the multi-step onboarding flow: state -> utility types -> supplier -> dashboard.
 *
 * All tests here represent a new user (region: null, onboarding_completed: false).
 * The profile mock is registered inline per test since it requires per-method
 * handling (GET returns the new-user profile; PUT echoes back the submitted body).
 * The shared factory's userProfile mock is disabled via apiMockConfig to avoid
 * conflicts with the onboarding-specific version.
 */

test.describe('Onboarding Wizard Flow', () => {
  // Disable the shared factory's userProfile mock so the inline onboarding
  // profile mock (which handles both GET and PUT) is not shadowed.
  test.use({
    apiMockConfig: {
      userProfile: false,
    },
    // New user has no settings yet — use the empty preset
    settingsPreset: {},
  })

  /** Register the new-user profile mock (GET + PUT) and other onboarding-relevant routes. */
  async function setupOnboardingMocks(page: import('@playwright/test').Page) {
    // Profile: GET = new user; PUT = echo body back as updated profile
    await page.route('**/api/v1/users/profile', async (route, request) => {
      if (request.method() === 'GET') {
        await route.fulfill({
          status: 200,
          contentType: 'application/json',
          body: JSON.stringify({
            email: 'test@example.com',
            name: 'Test User',
            region: null,
            utility_types: null,
            current_supplier_id: null,
            annual_usage_kwh: null,
            onboarding_completed: false,
          }),
        })
      } else {
        // PUT — return updated profile
        const body = request.postDataJSON()
        await route.fulfill({
          status: 200,
          contentType: 'application/json',
          body: JSON.stringify({
            email: 'test@example.com',
            name: 'Test User',
            region: body.region || null,
            utility_types: body.utility_types || null,
            current_supplier_id: body.current_supplier_id || null,
            annual_usage_kwh: body.annual_usage_kwh || null,
            onboarding_completed: body.onboarding_completed || false,
          }),
        })
      }
    })

    // Suppliers: TXU and Green Mountain for Texas deregulated flow
    await page.route('**/api/v1/suppliers**', async (route) => {
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({
          suppliers: [
            {
              id: 'sup_1',
              name: 'TXU Energy',
              avgPricePerKwh: 0.12,
              greenEnergy: false,
              rating: 4.2,
              estimatedAnnualCost: 1200,
              tariffType: 'variable',
            },
            {
              id: 'sup_2',
              name: 'Green Mountain Energy',
              avgPricePerKwh: 0.14,
              greenEnergy: true,
              rating: 4.5,
              estimatedAnnualCost: 1400,
              tariffType: 'fixed',
            },
          ],
          total: 2,
        }),
      })
    })
  }

  test('shows multi-step wizard starting with state selection', { tag: ['@smoke'] }, async ({ authenticatedPage: page }) => {
    await setupOnboardingMocks(page)
    await page.goto('/onboarding')

    await expect(page.getByText('Select your state')).toBeVisible()
    await expect(page.getByText('Step 1 of')).toBeVisible()
  })

  test('regulated state flow: state -> utility types -> dashboard', { tag: ['@smoke'] }, async ({ authenticatedPage: page }) => {
    await setupOnboardingMocks(page)
    await page.goto('/onboarding')

    // Step 1: Select Florida (regulated state)
    await page.fill('[placeholder="Search states..."]', 'Florida')
    await page.click('text=Florida')
    await page.click('text=Continue to Dashboard')

    // Step 2: Utility types (regulated message visible)
    await expect(page.getByText('What utilities do you use?')).toBeVisible()
    await expect(page.getByText(/regulated electricity market/)).toBeVisible()
    await expect(page.getByText('Complete Setup')).toBeVisible()

    // Complete
    await page.click('text=Complete Setup')
    await page.waitForURL(/\/dashboard/, { timeout: 10000 })
  })

  test('deregulated state flow includes supplier step', { tag: ['@smoke'] }, async ({ authenticatedPage: page }) => {
    await setupOnboardingMocks(page)
    await page.goto('/onboarding')

    // Step 1: Select Texas (deregulated)
    await page.fill('[placeholder="Search states..."]', 'Texas')
    await page.click('text=Texas')
    await page.click('text=Continue to Dashboard')

    // Step 2: Utility types
    await expect(page.getByText('What utilities do you use?')).toBeVisible()
    await page.click('text=Next: Choose Supplier')

    // Step 3: Supplier picker
    await expect(page.getByText('Who is your energy supplier?')).toBeVisible()
  })

  test('can skip supplier selection', { tag: ['@regression'] }, async ({ authenticatedPage: page }) => {
    await setupOnboardingMocks(page)
    await page.goto('/onboarding')

    // Navigate to supplier step
    await page.fill('[placeholder="Search states..."]', 'Texas')
    await page.click('text=Texas')
    await page.click('text=Continue to Dashboard')
    await page.click('text=Next: Choose Supplier')

    // Skip supplier — use role selector to avoid matching "Skip to main content" a11y link
    await page.getByRole('button', { name: 'Skip' }).click()
    await page.waitForURL(/\/dashboard/, { timeout: 10000 })
  })

  test('back navigation works between steps', { tag: ['@regression'] }, async ({ authenticatedPage: page }) => {
    await setupOnboardingMocks(page)
    await page.goto('/onboarding')

    // Go to step 2
    await page.fill('[placeholder="Search states..."]', 'Connecticut')
    await page.click('text=Connecticut')
    await page.click('text=Continue to Dashboard')

    await expect(page.getByText('What utilities do you use?')).toBeVisible()

    // Go back
    await page.click('text=Back')
    await expect(page.getByText('Select your state')).toBeVisible()
  })

  test('can select multiple utility types', { tag: ['@regression'] }, async ({ authenticatedPage: page }) => {
    await setupOnboardingMocks(page)
    await page.goto('/onboarding')

    // Go to step 2
    await page.fill('[placeholder="Search states..."]', 'Florida')
    await page.click('text=Florida')
    await page.click('text=Continue to Dashboard')

    // Select additional utility type
    await page.click('text=Natural Gas')
    await expect(page.getByText('Natural Gas')).toBeVisible()
  })
})
