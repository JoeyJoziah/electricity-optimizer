import { test, expect } from '@playwright/test'

test.describe('User Onboarding Flow', () => {
  test.beforeEach(async ({ page }) => {
    // Mock API endpoints
    await page.route('**/api/v1/auth/signup', async (route) => {
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({
          success: true,
          message: 'Verification email sent',
          userId: 'user_123',
        }),
      })
    })

    await page.route('**/api/v1/auth/verify', async (route) => {
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({
          success: true,
          access_token: 'mock_jwt_token',
          refresh_token: 'mock_refresh_token',
          user: {
            id: 'user_123',
            email: 'newuser@example.com',
            onboarding_completed: false,
          },
        }),
      })
    })

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
            },
          ],
        }),
      })
    })
  })

  // TODO: signup form uses Supabase client directly, not mockable via route interception
  test.skip('new user can complete signup form', async ({ page }) => {
    await page.goto('/auth/signup')
    await expect(page.getByRole('heading', { name: /sign up/i })).toBeVisible()
    await page.fill('#email', 'newuser@example.com')
    await page.fill('#password', 'SecurePass123!')
    await page.fill('#confirmPassword', 'SecurePass123!')
    await page.check('#terms')
    await page.click('button[type="submit"]')
    await expect(page.getByText(/check your email/i)).toBeVisible()
  })

  // TODO: signup form uses Supabase client directly
  test.skip('shows password requirements', async ({ page }) => {
    await page.goto('/auth/signup')
    await page.fill('#password', 'weak')
    await expect(page.getByText(/at least 8 characters/i)).toBeVisible()
  })

  // TODO: signup form uses Supabase client directly
  test.skip('validates matching passwords', async ({ page }) => {
    await page.goto('/auth/signup')
    await page.fill('#email', 'newuser@example.com')
    await page.fill('#password', 'SecurePass123!')
    await page.fill('#confirmPassword', 'DifferentPass123!')
    await page.check('#terms')
    await page.click('button[type="submit"]')
    await expect(page.getByText(/passwords do not match/i)).toBeVisible()
  })

  // TODO: signup form uses Supabase client directly
  test.skip('requires terms acceptance', async ({ page }) => {
    await page.goto('/auth/signup')
    await page.fill('#email', 'newuser@example.com')
    await page.fill('#password', 'SecurePass123!')
    await page.fill('#confirmPassword', 'SecurePass123!')
    await page.click('button[type="submit"]')
    await expect(page.getByText(/accept terms/i)).toBeVisible()
  })

  test('navigates from landing page to signup', async ({ page }) => {
    await page.goto('/')

    // Click Get Started
    await page.getByRole('link', { name: 'Get Started' }).first().click()

    // Should navigate to signup
    await expect(page).toHaveURL(/\/auth\/signup/)
  })

  // TODO: /onboarding page not implemented yet
  test.skip('user can complete full onboarding wizard', async ({ page }) => {
    await page.addInitScript(() => {
      localStorage.setItem('auth_token', 'mock_jwt_token')
      localStorage.setItem('user', JSON.stringify({
        id: 'user_123',
        email: 'newuser@example.com',
        onboarding_completed: false,
      }))
    })
    await page.goto('/onboarding')
    await expect(page.getByText(/welcome/i)).toBeVisible()
    await page.click('button:has-text("Get Started")')
    await expect(page.getByText(/select your region/i)).toBeVisible()
    await page.click('text=Connecticut')
    await page.click('button:has-text("Next")')
    await expect(page.getByText(/smart meter/i)).toBeVisible()
    await page.click('text=Skip for now')
    await expect(page.getByText(/preferences/i)).toBeVisible()
    await page.fill('[name="budget"]', '150')
    await page.click('button:has-text("Complete Setup")')
    await expect(page).toHaveURL(/\/dashboard/)
  })

  // TODO: /onboarding page not implemented yet
  test.skip('onboarding shows progress indicator', async ({ page }) => {
    await page.addInitScript(() => {
      localStorage.setItem('auth_token', 'mock_jwt_token')
      localStorage.setItem('user', JSON.stringify({
        id: 'user_123',
        email: 'newuser@example.com',
        onboarding_completed: false,
      }))
    })
    await page.goto('/onboarding')
    await expect(page.getByTestId('progress-indicator')).toBeVisible()
    await expect(page.getByText(/step 1/i)).toBeVisible()
  })

  // TODO: /onboarding page not implemented yet
  test.skip('can go back through onboarding steps', async ({ page }) => {
    await page.addInitScript(() => {
      localStorage.setItem('auth_token', 'mock_jwt_token')
      localStorage.setItem('user', JSON.stringify({
        id: 'user_123',
        email: 'newuser@example.com',
        onboarding_completed: false,
      }))
    })
    await page.goto('/onboarding')
    await page.click('button:has-text("Get Started")')
    await expect(page.getByText(/select your region/i)).toBeVisible()
    await page.click('button:has-text("Back")')
    await expect(page.getByText(/welcome/i)).toBeVisible()
  })

  // TODO: /onboarding page not implemented yet
  test.skip('saves onboarding progress', async ({ page }) => {
    await page.addInitScript(() => {
      localStorage.setItem('auth_token', 'mock_jwt_token')
      localStorage.setItem('user', JSON.stringify({
        id: 'user_123',
        email: 'newuser@example.com',
        onboarding_completed: false,
      }))
    })
    await page.goto('/onboarding')
    await page.click('button:has-text("Get Started")')
    await page.click('text=Connecticut')
    await page.click('button:has-text("Next")')
    await page.reload()
    await expect(page.getByText(/smart meter/i)).toBeVisible()
  })
})

test.describe('Post-Onboarding Dashboard Access', () => {
  test('completed onboarding shows dashboard', async ({ page }) => {
    // Set up completed onboarding state
    await page.addInitScript(() => {
      localStorage.setItem('auth_token', 'mock_jwt_token')
      localStorage.setItem('user', JSON.stringify({
        id: 'user_123',
        email: 'user@example.com',
        onboarding_completed: true,
      }))
      localStorage.setItem(
        'electricity-optimizer-settings',
        JSON.stringify({
          state: {
            region: 'US_CT',
            annualUsageKwh: 2900,
            peakDemandKw: 3,
          },
        })
      )
    })

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

    // Should see dashboard content
    await expect(page.getByText('Current Price').first()).toBeVisible()
    await expect(page.getByText('Forecast')).toBeVisible()
  })

  // TODO: /onboarding page not implemented — redirect cannot work
  test.skip('incomplete onboarding redirects to wizard', async ({ page }) => {
    await page.addInitScript(() => {
      localStorage.setItem('auth_token', 'mock_jwt_token')
      localStorage.setItem('user', JSON.stringify({
        id: 'user_123',
        email: 'user@example.com',
        onboarding_completed: false,
      }))
    })
    await page.goto('/dashboard')
    await expect(page).toHaveURL(/\/onboarding/)
  })
})
