import { test, expect } from '@playwright/test'

test.describe('Full User Journey - Signup to Billing', () => {
  test.beforeEach(async ({ page }) => {
    // Mock auth signup endpoint
    await page.route('**/api/v1/auth/signup', async (route) => {
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({
          access_token: 'mock_jwt_token_new_user',
          refresh_token: 'mock_refresh_token',
          user: {
            id: 'user_new_456',
            email: 'newuser@example.com',
            onboarding_completed: false,
          },
        }),
      })
    })

    // Mock auth signin endpoint
    await page.route('**/api/v1/auth/signin', async (route) => {
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({
          access_token: 'mock_jwt_token',
          refresh_token: 'mock_refresh_token',
          user: {
            id: 'user_new_456',
            email: 'newuser@example.com',
            onboarding_completed: true,
          },
        }),
      })
    })

    // Mock prices current endpoint
    await page.route('**/api/v1/prices/current**', async (route) => {
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({
          prices: [
            {
              region: 'US_CT',
              price: 0.25,
              timestamp: new Date().toISOString(),
              trend: 'decreasing',
              changePercent: -2.5,
            },
          ],
        }),
      })
    })

    // Mock prices history endpoint
    await page.route('**/api/v1/prices/history**', async (route) => {
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({
          prices: [
            { time: new Date(Date.now() - 7200000).toISOString(), price: 0.28 },
            { time: new Date(Date.now() - 3600000).toISOString(), price: 0.26 },
            { time: new Date().toISOString(), price: 0.25 },
          ],
        }),
      })
    })

    // Mock prices forecast endpoint
    await page.route('**/api/v1/prices/forecast**', async (route) => {
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({
          forecast: [
            { hour: 1, price: 0.23, confidence: [0.21, 0.25] },
            { hour: 2, price: 0.20, confidence: [0.18, 0.22] },
            { hour: 3, price: 0.18, confidence: [0.16, 0.20] },
            { hour: 4, price: 0.19, confidence: [0.17, 0.21] },
          ],
        }),
      })
    })

    // Mock suppliers endpoint
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

    // Mock optimization schedule endpoint
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
          ],
          totalSavings: 0.15,
          totalCost: 0.45,
        }),
      })
    })

    // Mock potential savings endpoint
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

    // Mock user onboarding endpoint
    await page.route('**/api/v1/user/onboarding', async (route) => {
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({
          success: true,
          message: 'Onboarding completed',
        }),
      })
    })

    // Mock auth signout endpoint
    await page.route('**/api/v1/auth/signout', async (route) => {
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({ success: true }),
      })
    })

    // Mock SSE stream endpoint
    await page.route('**/api/v1/prices/stream**', async (route) => {
      await route.fulfill({
        status: 200,
        contentType: 'text/event-stream',
        headers: {
          'Cache-Control': 'no-cache',
          'Connection': 'keep-alive',
        },
        body: 'data: {"region": "US_CT", "supplier": "Eversource", "price_per_kwh": "0.25", "currency": "USD", "is_peak": false, "timestamp": "' + new Date().toISOString() + '"}\n\n',
      })
    })

    // Mock billing endpoints
    await page.route('**/api/v1/billing/subscription', async (route) => {
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({
          tier: 'free',
          status: 'active',
          current_period_end: null,
          cancel_at_period_end: false,
        }),
      })
    })

    await page.route('**/api/v1/billing/checkout', async (route) => {
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({
          session_id: 'cs_test_journey_abc123',
          checkout_url: 'https://checkout.stripe.com/c/pay/cs_test_journey_abc123',
        }),
      })
    })
  })

  test('Step 1: Landing page shows hero section and CTA', async ({ page }) => {
    await page.goto('/')

    // Hero section
    await expect(page.getByText('Save Money on')).toBeVisible()
    await expect(page.getByText('Connecticut Electricity', { exact: true })).toBeVisible()

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

  test('Step 1 continued: Landing page shows features section', async ({ page }) => {
    await page.goto('/')

    // Features
    await expect(page.getByText('Real-Time Price Tracking')).toBeVisible()
    await expect(page.getByText('Smart Price Alerts')).toBeVisible()
    await expect(page.getByRole('heading', { name: 'ML-Powered Forecasts' })).toBeVisible()
    await expect(page.getByRole('heading', { name: 'Schedule Optimization' })).toBeVisible()
    await expect(page.getByRole('heading', { name: 'GDPR Compliant' })).toBeVisible()
    await expect(page.getByRole('heading', { name: 'Weather-Aware' })).toBeVisible()
  })

  // TODO: SignupForm uses Supabase client, not the mocked API endpoint
  test.skip('Step 2: Navigate to signup and fill the form', async ({ page }) => {
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

    // Should see confirmation or redirect
    await expect(page.getByText(/check your email|dashboard|onboarding/i)).toBeVisible()
  })

  // TODO: SignupForm uses Supabase client, not the mocked API endpoint
  test.skip('Step 3: Signup API responds correctly and user is redirected', async ({ page }) => {
    // Mock signup to return user with onboarding_completed: false
    await page.route('**/api/v1/auth/signup', async (route) => {
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({
          success: true,
          message: 'Verification email sent',
          userId: 'user_new_456',
        }),
      })
    })

    await page.goto('/auth/signup')

    await page.fill('#email', 'newuser@example.com')
    await page.fill('#password', 'SecurePass123!')
    await page.fill('#confirmPassword', 'SecurePass123!')
    await page.check('#terms')
    await page.click('button[type="submit"]')

    // Should show confirmation message about verification email
    await expect(page.getByText(/check your email/i)).toBeVisible()
  })

  test('Step 4: Dashboard loads with price widgets for authenticated user', async ({ page }) => {
    // Set up authenticated state
    await page.addInitScript(() => {
      localStorage.setItem('auth_token', 'mock_jwt_token')
      localStorage.setItem('user', JSON.stringify({
        id: 'user_new_456',
        email: 'newuser@example.com',
        onboarding_completed: true,
      }))
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

  test('Step 5: Suppliers page shows CT suppliers', async ({ page }) => {
    // Set up authenticated state
    await page.addInitScript(() => {
      localStorage.setItem('auth_token', 'mock_jwt_token')
      localStorage.setItem('user', JSON.stringify({
        id: 'user_new_456',
        email: 'newuser@example.com',
        onboarding_completed: true,
      }))
    })

    await page.goto('/suppliers')

    // Supplier comparison heading
    await expect(page.getByRole('heading', { name: /compare suppliers/i })).toBeVisible()

    // CT suppliers should be listed
    await expect(page.getByRole('heading', { name: 'Eversource Energy' })).toBeVisible()
    await expect(page.getByRole('heading', { name: 'NextEra Energy' })).toBeVisible()
    await expect(page.getByRole('heading', { name: 'United Illuminating (UI)' })).toBeVisible()
  })

  test('Step 6: Optimize page shows optimization recommendations', async ({ page }) => {
    // Set up authenticated state
    await page.addInitScript(() => {
      localStorage.setItem('auth_token', 'mock_jwt_token')
      localStorage.setItem('user', JSON.stringify({
        id: 'user_new_456',
        email: 'newuser@example.com',
        onboarding_completed: true,
      }))
    })

    await page.goto('/optimize')

    // Optimization page heading
    await expect(page.getByRole('heading', { name: 'Load Optimization' })).toBeVisible()

    // Should show appliance management section
    await expect(page.getByRole('heading', { name: 'Your Appliances' })).toBeVisible()

    // Quick add buttons for common appliances
    await expect(page.getByRole('button', { name: /Washing Machine/ })).toBeVisible()
  })

  test('Step 7: Pricing page shows tier comparison', async ({ page }) => {
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

  test('Step 8: Clicking upgrade navigates to signup with plan parameter', async ({ page }) => {
    await page.goto('/pricing')

    // Click the Pro tier CTA
    await page.getByRole('link', { name: 'Start Free Trial' }).click()

    // Should navigate to signup with plan=pro
    await expect(page).toHaveURL(/\/auth\/signup\?plan=pro/)
  })

  test('Full journey: landing to dashboard navigation', async ({ page }) => {
    // Start at landing page
    await page.goto('/')
    await expect(page.getByText('Save Money on')).toBeVisible()

    // Navigate to signup
    await page.getByRole('link', { name: 'Start Saving Today' }).click()
    await expect(page).toHaveURL(/\/auth\/signup/)

    // Signup page is present
    await expect(page.getByRole('heading', { name: /sign up|electricity optimizer/i })).toBeVisible()
  })

  test('Full journey: dashboard to suppliers to optimize navigation', async ({ page }) => {
    // Set up authenticated state
    await page.addInitScript(() => {
      localStorage.setItem('auth_token', 'mock_jwt_token')
      localStorage.setItem('user', JSON.stringify({
        id: 'user_new_456',
        email: 'newuser@example.com',
        onboarding_completed: true,
      }))
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

  test('Full journey: supplier details show pricing in USD', async ({ page }) => {
    // Set up authenticated state with USD display
    await page.addInitScript(() => {
      localStorage.setItem('auth_token', 'mock_jwt_token')
      localStorage.setItem('user', JSON.stringify({
        id: 'user_new_456',
        email: 'newuser@example.com',
        onboarding_completed: true,
      }))
      localStorage.setItem(
        'electricity-optimizer-settings',
        JSON.stringify({
          state: {
            region: 'US_CT',
            annualUsageKwh: 10500,
            peakDemandKw: 3,
            displayPreferences: {
              currency: 'USD',
              theme: 'system',
              timeFormat: '24h',
            },
          },
        })
      )
    })

    await page.goto('/suppliers')

    // Suppliers should be visible
    await expect(page.getByRole('heading', { name: 'Eversource Energy' })).toBeVisible()
    await expect(page.getByRole('heading', { name: 'NextEra Energy' })).toBeVisible()

    // Prices should be displayed (checking for dollar amounts)
    await expect(page.getByText(/\$1,200|\$1,050|\$1,350/).first()).toBeVisible()
  })

  test('Full journey: pricing page footer links work', async ({ page }) => {
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

test.describe('Full User Journey - Returning User Flow', () => {
  test.beforeEach(async ({ page }) => {
    // Set up a returning authenticated user
    await page.addInitScript(() => {
      localStorage.setItem('auth_token', 'mock_jwt_token')
      localStorage.setItem('user', JSON.stringify({
        id: 'user_returning_789',
        email: 'returning@example.com',
        onboarding_completed: true,
      }))
      localStorage.setItem(
        'electricity-optimizer-settings',
        JSON.stringify({
          state: {
            region: 'US_CT',
            annualUsageKwh: 10500,
            peakDemandKw: 3,
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
        })
      )
    })

    // Mock all API endpoints
    await page.route('**/api/v1/prices/current**', async (route) => {
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({
          prices: [
            {
              region: 'US_CT',
              price: 0.25,
              timestamp: new Date().toISOString(),
              trend: 'decreasing',
              changePercent: -2.5,
            },
          ],
        }),
      })
    })

    await page.route('**/api/v1/prices/history**', async (route) => {
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({
          prices: [
            { time: new Date(Date.now() - 3600000).toISOString(), price: 0.27 },
            { time: new Date().toISOString(), price: 0.25 },
          ],
        }),
      })
    })

    await page.route('**/api/v1/prices/forecast**', async (route) => {
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({
          forecast: [
            { hour: 1, price: 0.23, confidence: [0.21, 0.25] },
            { hour: 2, price: 0.20, confidence: [0.18, 0.22] },
          ],
        }),
      })
    })

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
              current: true,
            },
          ],
        }),
      })
    })

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
          ],
          totalSavings: 0.15,
          totalCost: 0.45,
        }),
      })
    })

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

    await page.route('**/api/v1/prices/stream**', async (route) => {
      await route.fulfill({
        status: 200,
        contentType: 'text/event-stream',
        headers: {
          'Cache-Control': 'no-cache',
          'Connection': 'keep-alive',
        },
        body: 'data: {"region": "US_CT", "supplier": "Eversource", "price_per_kwh": "0.25", "currency": "USD", "is_peak": false, "timestamp": "' + new Date().toISOString() + '"}\n\n',
      })
    })

    await page.route('**/api/v1/auth/signout', async (route) => {
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({ success: true }),
      })
    })
  })

  test('returning user lands directly on dashboard', async ({ page }) => {
    await page.goto('/dashboard')

    // Should show dashboard immediately (no redirect)
    await expect(page.getByRole('heading', { name: 'Dashboard' })).toBeVisible()
    await expect(page.getByText('Current Price').first()).toBeVisible()
    await expect(page.getByTestId('current-price').first()).toContainText('0.25')
  })

  test('returning user navigates full app: dashboard -> suppliers -> optimize -> settings', async ({ page }) => {
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

  test('returning user sees current supplier info on settings page', async ({ page }) => {
    await page.goto('/settings')

    // Current supplier section
    await expect(page.getByText('Current Supplier')).toBeVisible()
    await expect(page.getByText('United Illuminating (UI)')).toBeVisible()
    await expect(page.getByText('Connected')).toBeVisible()
  })

  test('returning user can view savings information on dashboard', async ({ page }) => {
    await page.goto('/dashboard')

    // Savings data should be displayed
    await expect(page.getByText('Total Saved')).toBeVisible()
    await expect(page.getByText('Savings & Streaks')).toBeVisible()

    // Streak information
    await expect(page.getByText(/streak/i).first()).toBeVisible()
  })

  test('returning user sees price dropping alert on dashboard', async ({ page }) => {
    await page.goto('/dashboard')

    // With trend=decreasing, should show alert banner
    await expect(page.getByText(/prices dropping/i)).toBeVisible()
    await expect(page.getByText(/good time for high-energy tasks/i)).toBeVisible()
  })

  test('returning user can view schedule on dashboard', async ({ page }) => {
    await page.goto('/dashboard')

    // Schedule section
    await expect(page.getByText("Today's Schedule").first()).toBeVisible()
  })
})

test.describe('Full User Journey - Unauthenticated Guard', () => {
  // TODO: implement authentication redirect
  test.skip('unauthenticated user is redirected to login from dashboard', async ({ page }) => {
    await page.route('**/api/v1/prices/current**', async (route) => {
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({
          prices: [{ region: 'US_CT', price: 0.25, timestamp: new Date().toISOString() }],
        }),
      })
    })

    await page.goto('/dashboard')

    // Should redirect to login
    await page.waitForURL(/\/auth\/login/)
  })

  test('landing page is accessible without authentication', async ({ page }) => {
    await page.goto('/')

    // Landing page should render fully
    await expect(page.getByText('Save Money on')).toBeVisible()
    await expect(page.getByText('Connecticut Electricity', { exact: true })).toBeVisible()
    await expect(page.getByRole('link', { name: 'Start Saving Today' })).toBeVisible()
  })

  test('pricing page is accessible without authentication', async ({ page }) => {
    await page.goto('/pricing')

    // Pricing page should render fully
    await expect(page.getByRole('heading', { name: /simple, transparent pricing/i })).toBeVisible()
    await expect(page.getByText('$0')).toBeVisible()
    await expect(page.getByText('$4.99')).toBeVisible()
    await expect(page.getByText('$14.99')).toBeVisible()
  })
})
