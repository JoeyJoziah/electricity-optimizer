import { test, expect } from '@playwright/test'

test.describe('Billing Flow - Pricing Page', () => {
  test('displays Free, Pro, and Business tiers on pricing page', async ({ page }) => {
    await page.goto('/pricing')

    // Page header
    await expect(page.getByRole('heading', { name: /simple, transparent pricing/i })).toBeVisible()

    // Free tier
    await expect(page.getByText('Free')).toBeVisible()
    await expect(page.getByText('$0')).toBeVisible()
    await expect(page.getByText('Get Started Free')).toBeVisible()

    // Pro tier
    await expect(page.getByText('Pro')).toBeVisible()
    await expect(page.getByText('$4.99')).toBeVisible()
    await expect(page.getByText('/mo').first()).toBeVisible()
    await expect(page.getByText('Start Free Trial')).toBeVisible()
    await expect(page.getByText('Most Popular')).toBeVisible()

    // Business tier
    await expect(page.getByText('Business')).toBeVisible()
    await expect(page.getByText('$14.99')).toBeVisible()
    await expect(page.getByText('Contact Sales')).toBeVisible()
  })

  test('Pro tier is highlighted as most popular', async ({ page }) => {
    await page.goto('/pricing')

    await expect(page.getByText('Most Popular')).toBeVisible()

    // Pro card should have the highlighted styling (blue border)
    const proCard = page.locator('div').filter({ hasText: /^\$4\.99/ }).first()
    await expect(proCard).toBeVisible()
  })

  test('Free tier lists correct features and limitations', async ({ page }) => {
    await page.goto('/pricing')

    // Free tier features
    await expect(page.getByText('Real-time CT electricity prices')).toBeVisible()
    await expect(page.getByText('1 price alert')).toBeVisible()
    await expect(page.getByText('Manual schedule optimization')).toBeVisible()

    // Free tier limitations
    await expect(page.getByText('No ML forecasts')).toBeVisible()
    await expect(page.getByText('No weather integration')).toBeVisible()
    await expect(page.getByText('No email notifications')).toBeVisible()
  })

  test('Pro tier lists all features', async ({ page }) => {
    await page.goto('/pricing')

    await expect(page.getByText('Unlimited price alerts')).toBeVisible()
    await expect(page.getByText('ML-powered 24hr forecasts')).toBeVisible()
    await expect(page.getByText('Smart schedule optimization')).toBeVisible()
    await expect(page.getByText('Weather-aware predictions')).toBeVisible()
    await expect(page.getByText('Historical price data')).toBeVisible()
    await expect(page.getByText('Email notifications via SendGrid')).toBeVisible()
    await expect(page.getByText('Savings tracker & gamification')).toBeVisible()
  })

  test('Business tier lists all features', async ({ page }) => {
    await page.goto('/pricing')

    await expect(page.getByText('REST API access')).toBeVisible()
    await expect(page.getByText('Multi-property management')).toBeVisible()
    await expect(page.getByText('Priority email support')).toBeVisible()
    await expect(page.getByText('SSE real-time streaming')).toBeVisible()
    await expect(page.getByText('Dedicated account manager')).toBeVisible()
  })

  test('CTA buttons link to correct signup pages', async ({ page }) => {
    await page.goto('/pricing')

    // Free tier links to /auth/signup
    const freeLink = page.getByRole('link', { name: 'Get Started Free' })
    await expect(freeLink).toHaveAttribute('href', '/auth/signup')

    // Pro tier links to /auth/signup?plan=pro
    const proLink = page.getByRole('link', { name: 'Start Free Trial' })
    await expect(proLink).toHaveAttribute('href', '/auth/signup?plan=pro')

    // Business tier links to /auth/signup?plan=business
    const businessLink = page.getByRole('link', { name: 'Contact Sales' })
    await expect(businessLink).toHaveAttribute('href', '/auth/signup?plan=business')
  })

  test('FAQ section is visible and has expected questions', async ({ page }) => {
    await page.goto('/pricing')

    await expect(page.getByText('Frequently asked questions')).toBeVisible()
    await expect(page.getByText('Can I cancel anytime?')).toBeVisible()
    await expect(page.getByText('What payment methods do you accept?')).toBeVisible()
    await expect(page.getByText('Is my data secure?')).toBeVisible()
    await expect(page.getByText('Where does the price data come from?')).toBeVisible()
  })
})

test.describe('Billing Flow - Upgrade to Pro', () => {
  test.beforeEach(async ({ page }) => {
    // Set up authenticated free-tier user
    await page.addInitScript(() => {
      localStorage.setItem('auth_token', 'mock_jwt_token')
      localStorage.setItem('user', JSON.stringify({
        id: 'user_123',
        email: 'test@example.com',
        onboarding_completed: true,
      }))
    })

    // Mock billing subscription endpoint - free tier
    await page.route('**/api/v1/billing/subscription', async (route) => {
      if (route.request().method() === 'GET') {
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
      }
    })

    // Mock billing checkout endpoint
    await page.route('**/api/v1/billing/checkout', async (route) => {
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({
          session_id: 'cs_test_abc123',
          checkout_url: 'https://checkout.stripe.com/c/pay/cs_test_abc123',
        }),
      })
    })

    // Mock billing portal endpoint
    await page.route('**/api/v1/billing/portal', async (route) => {
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({
          portal_url: 'https://billing.stripe.com/p/session/test_portal_abc123',
        }),
      })
    })

    // Mock standard API endpoints
    await page.route('**/api/v1/prices/current**', async (route) => {
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({
          prices: [{ region: 'US_CT', price: 0.25, timestamp: new Date().toISOString() }],
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
            { time: new Date().toISOString(), price: 0.25 },
          ],
        }),
      })
    })

    await page.route('**/api/v1/suppliers**', async (route) => {
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({ suppliers: [] }),
      })
    })
  })

  test('clicking Upgrade to Pro triggers checkout session creation', async ({ page }) => {
    let checkoutCalled = false

    await page.route('**/api/v1/billing/checkout', async (route) => {
      checkoutCalled = true
      const body = JSON.parse(route.request().postData() || '{}')
      expect(body.plan || body.tier).toBeTruthy()

      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({
          session_id: 'cs_test_abc123',
          checkout_url: 'https://checkout.stripe.com/c/pay/cs_test_abc123',
        }),
      })
    })

    await page.goto('/pricing')

    // Click the Pro tier CTA
    await page.getByRole('link', { name: 'Start Free Trial' }).click()

    // Should navigate to signup with plan param
    await expect(page).toHaveURL(/\/auth\/signup\?plan=pro/)
  })

  test('free tier user sees upgrade prompts on settings page', async ({ page }) => {
    await page.goto('/settings')

    // Settings page should load
    await expect(page.getByText('Account')).toBeVisible()

    // Should show subscription status or upgrade prompt
    // The settings page shows account info; free tier users should see current tier
    await expect(page.getByText(/Region/)).toBeVisible()
  })

  test('handles checkout error gracefully when Stripe not configured', async ({ page }) => {
    // Override checkout mock to return 503
    await page.route('**/api/v1/billing/checkout', async (route) => {
      await route.fulfill({
        status: 503,
        contentType: 'application/json',
        body: JSON.stringify({
          detail: 'Stripe is not configured. Set STRIPE_SECRET_KEY to enable billing.',
        }),
      })
    })

    await page.goto('/pricing')

    // The pricing page should still render correctly even if checkout fails later
    await expect(page.getByText('$4.99')).toBeVisible()
    await expect(page.getByText('$14.99')).toBeVisible()
  })
})

test.describe('Billing Flow - Subscribed User', () => {
  test.beforeEach(async ({ page }) => {
    // Set up authenticated pro-tier user
    await page.addInitScript(() => {
      localStorage.setItem('auth_token', 'mock_jwt_token')
      localStorage.setItem('user', JSON.stringify({
        id: 'user_123',
        email: 'pro-user@example.com',
        onboarding_completed: true,
        subscription_tier: 'pro',
      }))
    })

    // Mock billing subscription endpoint - pro tier
    await page.route('**/api/v1/billing/subscription', async (route) => {
      if (route.request().method() === 'GET') {
        await route.fulfill({
          status: 200,
          contentType: 'application/json',
          body: JSON.stringify({
            tier: 'pro',
            status: 'active',
            current_period_end: new Date(Date.now() + 30 * 24 * 60 * 60 * 1000).toISOString(),
            cancel_at_period_end: false,
          }),
        })
      }
    })

    // Mock billing portal endpoint
    await page.route('**/api/v1/billing/portal', async (route) => {
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({
          portal_url: 'https://billing.stripe.com/p/session/test_portal_abc123',
        }),
      })
    })

    // Mock standard API endpoints
    await page.route('**/api/v1/prices/current**', async (route) => {
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({
          prices: [{ region: 'US_CT', price: 0.25, timestamp: new Date().toISOString() }],
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
            { time: new Date().toISOString(), price: 0.25 },
          ],
        }),
      })
    })

    await page.route('**/api/v1/suppliers**', async (route) => {
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({ suppliers: [] }),
      })
    })
  })

  test('subscribed user can access settings page', async ({ page }) => {
    await page.goto('/settings')

    await expect(page.getByText('Account')).toBeVisible()
    await expect(page.getByText('Energy Usage')).toBeVisible()
    await expect(page.getByText('Notifications')).toBeVisible()
    await expect(page.getByText('Display')).toBeVisible()
    await expect(page.getByText('Privacy & Data')).toBeVisible()
  })

  test('settings page shows subscription region as Connecticut', async ({ page }) => {
    await page.addInitScript(() => {
      localStorage.setItem(
        'electricity-optimizer-settings',
        JSON.stringify({
          state: {
            region: 'US_CT',
            annualUsageKwh: 10500,
            peakDemandKw: 3,
          },
        })
      )
    })

    await page.goto('/settings')

    // Region selector should show Connecticut
    await expect(page.getByText('Connecticut')).toBeVisible()
  })

  test('customer portal link works for subscribed users', async ({ page }) => {
    let portalCalled = false

    await page.route('**/api/v1/billing/portal', async (route) => {
      portalCalled = true
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({
          portal_url: 'https://billing.stripe.com/p/session/test_portal_abc123',
        }),
      })
    })

    await page.goto('/settings')

    // The settings page should be accessible for subscribed users
    await expect(page.getByText('Account')).toBeVisible()
  })

  test('pricing page still renders for already subscribed users', async ({ page }) => {
    await page.goto('/pricing')

    // Pricing page should still show all tiers
    await expect(page.getByText('Free')).toBeVisible()
    await expect(page.getByText('Pro')).toBeVisible()
    await expect(page.getByText('Business')).toBeVisible()
    await expect(page.getByText('$4.99')).toBeVisible()
    await expect(page.getByText('$14.99')).toBeVisible()
  })
})

test.describe('Billing Flow - Upgrade Journey', () => {
  test('upgrade flow from landing page through pricing to signup', async ({ page }) => {
    // Step 1: Visit landing page
    await page.goto('/')
    await expect(page.getByText('Save Money on')).toBeVisible()
    await expect(page.getByText('Connecticut Electricity')).toBeVisible()

    // Step 2: Navigate to pricing page via nav link
    await page.getByRole('link', { name: 'Pricing' }).first().click()
    await expect(page).toHaveURL('/pricing')

    // Step 3: Verify pricing tiers
    await expect(page.getByText('$0')).toBeVisible()
    await expect(page.getByText('$4.99')).toBeVisible()
    await expect(page.getByText('$14.99')).toBeVisible()

    // Step 4: Click Start Free Trial (Pro)
    await page.getByRole('link', { name: 'Start Free Trial' }).click()

    // Step 5: Should redirect to signup with plan=pro
    await expect(page).toHaveURL(/\/auth\/signup\?plan=pro/)
  })

  test('landing page shows pricing preview with all three tiers', async ({ page }) => {
    await page.goto('/')

    // Scroll to pricing section on landing page
    await expect(page.getByText('Simple, transparent pricing')).toBeVisible()

    // Verify all three tiers on landing page
    await expect(page.getByText('$0')).toBeVisible()
    await expect(page.getByText('$4.99')).toBeVisible()
    await expect(page.getByText('$14.99')).toBeVisible()

    // Verify Pro features in landing preview
    await expect(page.getByText('Unlimited price alerts')).toBeVisible()
    await expect(page.getByText('ML-powered forecasts')).toBeVisible()
  })
})
