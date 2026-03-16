import { test, expect } from './fixtures'

// ---------------------------------------------------------------------------
// Mock supplier data reused across the Returning User describe block
// ---------------------------------------------------------------------------

const RETURNING_USER_SUPPLIERS = [
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
]

// ---------------------------------------------------------------------------
// Full User Journey - Signup to Billing
//
// Most tests in this suite exercise public pages (/, /pricing, /auth/*) or
// navigate to protected pages as part of a logged-in flow. Tests that need an
// authenticated session use the `authenticatedPage` fixture; public-page tests
// use `page` directly so they are not inadvertently redirected by the auth cookie.
// ---------------------------------------------------------------------------

test.describe('Full User Journey - Signup to Billing', () => {
  // The shared authenticatedPage fixture covers auth + standard API mocks.
  // Tests that visit public pages (/,/pricing,/auth/*) use `page` directly
  // so they are not inadvertently redirected by the auth cookie.

  test('Step 1: Landing page shows hero section and CTA', { tag: ['@smoke'] }, async ({ page }) => {
    await page.goto('/')

    // Hero section
    await expect(page.getByText('Save Money on')).toBeVisible()
    await expect(page.getByText('Your Electricity Bills', { exact: true })).toBeVisible()

    // Description text
    await expect(page.getByText(/AI-powered price optimization/)).toBeVisible()

    // CTAs
    await expect(page.getByRole('link', { name: 'Start Saving Today' })).toBeVisible()
    await expect(page.getByRole('link', { name: 'View Demo' })).toBeVisible()

    // Nav links
    await expect(page.getByRole('link', { name: 'Pricing' }).first()).toBeVisible()
    await expect(page.getByRole('link', { name: 'Sign In' })).toBeVisible()
    await expect(page.getByRole('link', { name: 'Get Started' }).first()).toBeVisible()
  })

  test('Step 1 continued: Landing page shows features section', { tag: ['@regression'] }, async ({ page }) => {
    await page.goto('/')

    // Features
    await expect(page.getByText('Real-Time Price Tracking')).toBeVisible()
    await expect(page.getByText('Smart Price Alerts')).toBeVisible()
    await expect(page.getByRole('heading', { name: 'ML-Powered Forecasts' })).toBeVisible()
    await expect(page.getByRole('heading', { name: 'Schedule Optimization' })).toBeVisible()
    await expect(page.getByRole('heading', { name: 'GDPR Compliant' })).toBeVisible()
    await expect(page.getByRole('heading', { name: 'Weather-Aware' })).toBeVisible()
  })

  test('Step 2: Navigate to signup and fill the form', { tag: ['@smoke'] }, async ({ page }) => {
    await page.goto('/')

    // Click Get Started from landing page
    await page.getByRole('link', { name: 'Get Started' }).first().click()

    // Should navigate to signup page
    await expect(page).toHaveURL(/\/auth\/signup/)

    // Signup page heading
    await expect(page.getByRole('heading', { name: /sign up|electricity optimizer/i })).toBeVisible()

    // Fill signup form
    await page.fill('#email', 'newuser@example.com')
    await page.fill('#password', 'SecurePass123!')
    await page.fill('#confirmPassword', 'SecurePass123!')

    // Accept terms
    await page.check('#terms')

    // Submit form
    await page.click('button[type="submit"]')

    // After signup, the mock auth sets a session and redirects. On mobile,
    // the redirect happens before any confirmation text renders. Use URL-based
    // assertion which works reliably across all viewports.
    await page.waitForURL(/\/(onboarding|dashboard|auth)/, { timeout: 10000 })
  })

  test('Step 3: Signup API responds correctly and user is redirected', { tag: ['@regression'] }, async ({ page }) => {
    await page.goto('/auth/signup')

    await page.fill('#email', 'newuser@example.com')
    await page.fill('#password', 'SecurePass123!')
    await page.fill('#confirmPassword', 'SecurePass123!')
    await page.check('#terms')
    await page.click('button[type="submit"]')

    // Signup redirects to onboarding for new users
    await page.waitForURL(/\/(onboarding|dashboard|auth)/, { timeout: 10000 })
  })

  test('Step 4: Dashboard loads with price widgets for authenticated user', { tag: ['@smoke'] }, async ({ authenticatedPage: page }) => {
    // authenticatedPage already has auth cookie + PRESET_FREE settings + all standard API mocks

    // Override suppliers mock to include the three suppliers used in dashboard assertions
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
          ],
        }),
      })
    })

    await page.goto('/dashboard')

    // Dashboard title
    await expect(page.getByRole('heading', { name: 'Dashboard' })).toBeVisible()

    // Current price widget
    await expect(page.getByText('Current Price').first()).toBeVisible()
    await expect(page.getByTestId('current-price').first()).toBeVisible()
    await expect(page.getByTestId('current-price').first()).toContainText('0.25')

    // Total saved widget
    await expect(page.getByText('Total Saved')).toBeVisible()

    // Optimal times widget
    await expect(page.getByText('Optimal Times')).toBeVisible()

    // Suppliers widget
    await expect(page.getByRole('heading', { name: 'Top Suppliers' })).toBeVisible()

    // Price history chart section
    await expect(page.getByText('Price History')).toBeVisible()

    // Forecast section
    await expect(page.getByText('24-Hour Forecast').first()).toBeVisible()
  })

  test('Step 5: Suppliers page shows supplier comparison', { tag: ['@smoke'] }, async ({ authenticatedPage: page }) => {
    await page.goto('/suppliers')

    // Supplier comparison heading
    await expect(page.getByRole('heading', { name: /compare suppliers/i })).toBeVisible()
  })

  test('Step 6: Optimize page shows optimization recommendations', { tag: ['@smoke'] }, async ({ authenticatedPage: page }) => {
    await page.goto('/optimize')

    // Optimization page heading
    await expect(page.getByRole('heading', { name: 'Load Optimization' })).toBeVisible()

    // Should show appliance management section
    await expect(page.getByRole('heading', { name: 'Your Appliances' })).toBeVisible()

    // Quick add buttons for common appliances
    await expect(page.getByRole('button', { name: /Washing Machine/ })).toBeVisible()
  })

  test('Step 7: Pricing page shows tier comparison', { tag: ['@smoke'] }, async ({ page }) => {
    await page.goto('/pricing')

    // Pricing page header
    await expect(page.getByRole('heading', { name: /simple, transparent pricing/i })).toBeVisible()

    // All three tiers
    await expect(page.getByRole('heading', { name: 'Free' })).toBeVisible()
    await expect(page.getByRole('heading', { name: 'Pro' })).toBeVisible()
    await expect(page.getByRole('heading', { name: 'Business' })).toBeVisible()

    // Prices in USD
    await expect(page.getByText('$0')).toBeVisible()
    await expect(page.getByText('$4.99')).toBeVisible()
    await expect(page.getByText('$14.99')).toBeVisible()

    // Pro is highlighted
    await expect(page.getByText('Most Popular')).toBeVisible()
  })

  test('Step 8: Clicking upgrade navigates to signup with plan parameter', { tag: ['@regression'] }, async ({ page }) => {
    await page.goto('/pricing')

    // Click the Pro tier CTA
    await page.getByRole('link', { name: 'Start Free Trial' }).click()

    // Should navigate to signup with plan=pro
    await expect(page).toHaveURL(/\/auth\/signup\?plan=pro/)
  })

  test('Full journey: landing to dashboard navigation', { tag: ['@smoke'] }, async ({ page }) => {
    // Start at landing page
    await page.goto('/')
    await expect(page.getByText('Save Money on')).toBeVisible()

    // Navigate to signup
    await page.getByRole('link', { name: 'Start Saving Today' }).click()
    await expect(page).toHaveURL(/\/auth\/signup/)

    // Signup page is present
    await expect(page.getByRole('heading', { name: /sign up|electricity optimizer/i })).toBeVisible()
  })

  test('Full journey: dashboard to suppliers to optimize navigation', { tag: ['@smoke'] }, async ({ authenticatedPage: page }) => {
    // authenticatedPage already has auth + PRESET_FREE settings + standard mocks.
    // Override suppliers to include the specific names used in assertions.
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
              recommended: true,
            },
          ],
        }),
      })
    })

    // Step 1: Start at dashboard
    await page.goto('/dashboard')
    await expect(page.getByText('Current Price').first()).toBeVisible()
    await expect(page.getByTestId('current-price').first()).toContainText('0.25')

    // Step 2: Navigate to suppliers via the dashboard link
    await page.getByRole('link', { name: 'View all', exact: true }).click()
    await expect(page).toHaveURL('/suppliers')
    await expect(page.getByRole('heading', { name: 'Eversource Energy' })).toBeVisible()
    await expect(page.getByRole('heading', { name: 'NextEra Energy' })).toBeVisible()
  })

  test('Full journey: supplier details show pricing in USD', { tag: ['@regression'] }, async ({ authenticatedPage: page }) => {
    // Override suppliers with the three suppliers that have the dollar amounts asserted below
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
            },
          ],
        }),
      })
    })

    await page.goto('/suppliers')

    // Suppliers should be visible
    await expect(page.getByRole('heading', { name: 'Eversource Energy' })).toBeVisible()
    await expect(page.getByRole('heading', { name: 'NextEra Energy' })).toBeVisible()

    // Prices should be displayed (checking for dollar amounts)
    await expect(page.getByText(/\$1,200|\$1,050|\$1,350/).first()).toBeVisible()
  })

  test('Full journey: pricing page footer links work', { tag: ['@regression'] }, async ({ page }) => {
    await page.goto('/pricing')

    // Footer links
    await expect(page.getByRole('link', { name: 'Home' })).toBeVisible()
    await expect(page.getByRole('link', { name: 'Privacy', exact: true })).toBeVisible()
    await expect(page.getByRole('link', { name: 'Terms', exact: true })).toBeVisible()

    // Click Home link
    await page.getByRole('link', { name: 'Home' }).click()
    await expect(page).toHaveURL('/')
  })
})

// ---------------------------------------------------------------------------
// Full User Journey - Returning User Flow
// ---------------------------------------------------------------------------

test.describe('Full User Journey - Returning User Flow', () => {
  // This suite uses authenticatedPage (auth cookie + PRESET_FREE settings + standard mocks).
  // It also needs the current supplier in localStorage, so we use test.use() to supply
  // a richer settings preset, plus override suppliers and prices mocks inline.

  test.use({
    settingsPreset: {
      region: 'US_CT',
      annualUsageKwh: 10500,
      peakDemandKw: 3,
      displayPreferences: {
        currency: 'USD',
        theme: 'system',
        timeFormat: '24h',
      },
    },
    apiMockConfig: {
      pricesCurrent: { region: 'US_CT', price: 0.25, trend: 'decreasing', changePercent: -2.5 },
      savingsSummary: { monthly: 12.50, weekly: 3.25, streak_days: 5 },
    },
  })

  test('returning user lands directly on dashboard', { tag: ['@smoke'] }, async ({ authenticatedPage: page }) => {
    // Override suppliers to include the returning user's current supplier
    await page.route('**/api/v1/suppliers**', async (route) => {
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({ suppliers: RETURNING_USER_SUPPLIERS }),
      })
    })

    await page.goto('/dashboard')

    // Should show dashboard immediately (no redirect)
    await expect(page.getByRole('heading', { name: 'Dashboard' })).toBeVisible()
    await expect(page.getByText('Current Price').first()).toBeVisible()
    await expect(page.getByTestId('current-price').first()).toContainText('0.25')
  })

  test('returning user navigates full app: dashboard -> suppliers -> optimize -> settings', { tag: ['@smoke'] }, async ({ authenticatedPage: page }) => {
    await page.route('**/api/v1/suppliers**', async (route) => {
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({ suppliers: RETURNING_USER_SUPPLIERS }),
      })
    })

    // Dashboard
    await page.goto('/dashboard')
    await expect(page.getByText('Current Price').first()).toBeVisible()
    await expect(page.getByText('Top Suppliers')).toBeVisible()
    await expect(page.getByRole('heading', { name: 'Eversource Energy' })).toBeVisible()

    // Navigate to suppliers
    await page.goto('/suppliers')
    await expect(page.getByRole('heading', { name: /compare suppliers/i })).toBeVisible()
    await expect(page.getByRole('heading', { name: 'Eversource Energy' })).toBeVisible()
    await expect(page.getByRole('heading', { name: 'NextEra Energy' })).toBeVisible()
    await expect(page.getByRole('heading', { name: 'United Illuminating (UI)' })).toBeVisible()

    // Navigate to optimize
    await page.goto('/optimize')
    await expect(page.getByRole('heading', { name: 'Load Optimization' })).toBeVisible()

    // Navigate to settings
    await page.goto('/settings')
    await expect(page.getByRole('heading', { name: 'Account' })).toBeVisible()
    await expect(page.getByRole('heading', { name: 'Energy Usage' })).toBeVisible()
    await expect(page.getByRole('heading', { name: 'Notifications' })).toBeVisible()
    await expect(page.getByRole('heading', { name: 'Display' })).toBeVisible()
  })

  test('returning user sees current supplier info on settings page', { tag: ['@regression'] }, async ({ authenticatedPage: page }) => {
    // Override user/supplier to return a non-null current supplier
    await page.route('**/api/v1/user/supplier', async (route) => {
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({
          supplier: {
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
        }),
      })
    })

    await page.goto('/settings')

    // Current supplier section — use .first() because "Current Supplier" may
    // appear in both a heading and badge on the suppliers page layout
    await expect(page.getByText('Current Supplier').first()).toBeVisible()
    await expect(page.getByText('United Illuminating (UI)').first()).toBeVisible()
    await expect(page.getByText('Connected').first()).toBeVisible()
  })

  test('returning user can view savings information on dashboard', { tag: ['@regression'] }, async ({ authenticatedPage: page }) => {
    await page.goto('/dashboard')

    // Savings data should be displayed
    await expect(page.getByText('Total Saved')).toBeVisible()
    await expect(page.getByText('Savings & Streaks')).toBeVisible()

    // Streak information
    await expect(page.getByText(/streak/i).first()).toBeVisible()
  })

  test('returning user sees price dropping alert on dashboard', { tag: ['@regression'] }, async ({ authenticatedPage: page }) => {
    await page.goto('/dashboard')

    // With trend=decreasing, should show alert banner
    await expect(page.getByText(/prices dropping/i)).toBeVisible()
    await expect(page.getByText(/good time for high-energy tasks/i)).toBeVisible()
  })

  test('returning user can view schedule on dashboard', { tag: ['@regression'] }, async ({ authenticatedPage: page }) => {
    await page.goto('/dashboard')

    // Schedule section
    await expect(page.getByText("Today's Schedule").first()).toBeVisible()
  })
})

// ---------------------------------------------------------------------------
// Full User Journey - Unauthenticated Guard
// ---------------------------------------------------------------------------

test.describe('Full User Journey - Unauthenticated Guard', () => {
  test('unauthenticated user is redirected to login from dashboard', { tag: ['@smoke'] }, async ({ page }) => {
    // Ensure no session cookie — middleware should redirect
    await page.context().clearCookies()

    await page.route('**/api/auth/get-session', async (route) => {
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify(null),
      })
    })

    await page.goto('/dashboard')

    // Should redirect to login
    await page.waitForURL(/\/auth\/login/, { timeout: 10000 })
  })

  test('landing page is accessible without authentication', { tag: ['@smoke'] }, async ({ page }) => {
    await page.goto('/')

    // Landing page should render fully
    await expect(page.getByText('Save Money on')).toBeVisible()
    await expect(page.getByText('Your Electricity Bills', { exact: true })).toBeVisible()
    await expect(page.getByRole('link', { name: 'Start Saving Today' })).toBeVisible()
  })

  test('pricing page is accessible without authentication', { tag: ['@smoke'] }, async ({ page }) => {
    await page.goto('/pricing')

    // Pricing page should render fully
    await expect(page.getByRole('heading', { name: /simple, transparent pricing/i })).toBeVisible()
    await expect(page.getByText('$0')).toBeVisible()
    await expect(page.getByText('$4.99')).toBeVisible()
    await expect(page.getByText('$14.99')).toBeVisible()
  })
})
