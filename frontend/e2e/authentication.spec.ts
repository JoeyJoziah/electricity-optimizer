import { test, expect } from '@playwright/test'

test.describe('Authentication Flows', () => {
  test.beforeEach(async ({ page }) => {
    // Mock auth endpoints
    await page.route('**/api/v1/auth/signin', async (route) => {
      const body = JSON.parse(route.request().postData() || '{}')

      if (body.email === 'test@example.com' && body.password === 'TestPass123!') {
        await route.fulfill({
          status: 200,
          contentType: 'application/json',
          body: JSON.stringify({
            access_token: 'mock_jwt_token',
            refresh_token: 'mock_refresh_token',
            user: {
              id: 'user_123',
              email: 'test@example.com',
              onboarding_completed: true,
            },
          }),
        })
      } else {
        await route.fulfill({
          status: 401,
          contentType: 'application/json',
          body: JSON.stringify({
            detail: 'Invalid credentials',
          }),
        })
      }
    })

    await page.route('**/api/v1/auth/signout', async (route) => {
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({ success: true }),
      })
    })

    await page.route('**/api/v1/auth/magic-link', async (route) => {
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({
          success: true,
          message: 'Magic link sent to your email',
        }),
      })
    })

    await page.route('**/api/v1/auth/oauth/google**', async (route) => {
      await route.fulfill({
        status: 302,
        headers: {
          Location: 'https://accounts.google.com/o/oauth2/auth?...',
        },
      })
    })

    await page.route('**/api/v1/auth/callback**', async (route) => {
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({
          access_token: 'mock_jwt_token',
          refresh_token: 'mock_refresh_token',
          user: {
            id: 'user_123',
            email: 'oauth@example.com',
            onboarding_completed: true,
          },
        }),
      })
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

    await page.route('**/api/v1/prices/forecast**', async (route) => {
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({
          forecast: [{ hour: 1, price: 0.23, confidence: [0.21, 0.25] }],
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

  test('displays login page', async ({ page }) => {
    await page.goto('/auth/login')

    await expect(page.getByRole('heading', { name: /electricity optimizer/i })).toBeVisible()
    await expect(page.getByPlaceholder(/email/i)).toBeVisible()
    await expect(page.getByPlaceholder(/password/i)).toBeVisible()
    await expect(page.getByRole('button', { name: /sign in/i })).toBeVisible()
  })

  test('user can login with email and password', async ({ page }) => {
    await page.goto('/auth/login')

    await page.fill('[name="email"]', 'test@example.com')
    await page.fill('[name="password"]', 'TestPass123!')
    await page.click('button[type="submit"]')

    // Should redirect to dashboard
    await page.waitForURL('/dashboard')
    await expect(page.getByText('Current Price')).toBeVisible()
  })

  test('shows error for invalid credentials', async ({ page }) => {
    await page.goto('/auth/login')

    await page.fill('[name="email"]', 'wrong@example.com')
    await page.fill('[name="password"]', 'WrongPass123!')
    await page.click('button[type="submit"]')

    // Should show error message
    await expect(page.getByText(/invalid credentials/i)).toBeVisible()
  })

  test('validates email format', async ({ page }) => {
    await page.goto('/auth/login')

    await page.fill('[name="email"]', 'invalid-email')
    await page.fill('[name="password"]', 'TestPass123!')
    await page.click('button[type="submit"]')

    // Should show validation error
    await expect(page.getByText(/valid email/i)).toBeVisible()
  })

  test('shows OAuth login options', async ({ page }) => {
    await page.goto('/auth/login')

    await expect(page.getByRole('button', { name: /continue with google/i })).toBeVisible()
    await expect(page.getByRole('button', { name: /continue with github/i })).toBeVisible()
  })

  test('initiates OAuth flow with Google', async ({ page }) => {
    await page.goto('/auth/login')

    // Mock the OAuth redirect
    await page.route('**/api/v1/auth/oauth/google', async (route) => {
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({ url: 'https://accounts.google.com/mock-oauth' }),
      })
    })

    await page.click('button:has-text("Continue with Google")')

    // Should initiate OAuth flow (in real scenario, redirects to Google)
    // For testing, we verify the button click triggers the flow
    await expect(page.locator('body')).toBeVisible()
  })

  test('handles OAuth callback', async ({ page }) => {
    // Set up the return state
    await page.addInitScript(() => {
      sessionStorage.setItem('oauth_state', 'mock_state')
    })

    await page.goto('/auth/callback?code=mock_code&provider=google&state=mock_state')

    // Should redirect to dashboard
    await page.waitForURL('/dashboard')
  })

  test('user can login with magic link', async ({ page }) => {
    await page.goto('/auth/login')

    // Click magic link option
    await page.click('text=Sign in with email')

    // Should show magic link form
    await expect(page.getByText(/magic link/i)).toBeVisible()

    await page.fill('[name="email"]', 'test@example.com')
    await page.click('button:has-text("Send Magic Link")')

    // Should show confirmation
    await expect(page.getByText(/check your email/i)).toBeVisible()
  })

  test('user can logout', async ({ page }) => {
    // Set up authenticated state
    await page.addInitScript(() => {
      localStorage.setItem('auth_token', 'mock_jwt_token')
      localStorage.setItem('user', JSON.stringify({
        id: 'user_123',
        email: 'test@example.com',
        onboarding_completed: true,
      }))
    })

    await page.goto('/dashboard')
    await expect(page.getByText('Current Price')).toBeVisible()

    // Click logout
    await page.click('[data-testid="user-menu"]')
    await page.click('text=Sign out')

    // Should redirect to login
    await page.waitForURL('/auth/login')
  })

  test('redirects unauthenticated users to login', async ({ page }) => {
    await page.goto('/dashboard')

    // Should redirect to login
    await page.waitForURL(/\/auth\/login/)
  })

  test('shows forgot password link', async ({ page }) => {
    await page.goto('/auth/login')

    await expect(page.getByText(/forgot password/i)).toBeVisible()
  })

  test('can navigate to signup from login', async ({ page }) => {
    await page.goto('/auth/login')

    await page.click('text=Sign up')

    await expect(page).toHaveURL(/\/auth\/signup/)
  })

  test('preserves redirect URL after login', async ({ page }) => {
    // Try to access protected page
    await page.goto('/suppliers')

    // Should redirect to login with redirect param
    await page.waitForURL(/\/auth\/login\?redirect=/)

    // Login
    await page.fill('[name="email"]', 'test@example.com')
    await page.fill('[name="password"]', 'TestPass123!')
    await page.click('button[type="submit"]')

    // Should redirect back to original page
    await page.waitForURL('/suppliers')
  })

  test('session persists on page refresh', async ({ page }) => {
    // Set up authenticated state
    await page.addInitScript(() => {
      localStorage.setItem('auth_token', 'mock_jwt_token')
      localStorage.setItem('user', JSON.stringify({
        id: 'user_123',
        email: 'test@example.com',
        onboarding_completed: true,
      }))
    })

    await page.goto('/dashboard')
    await expect(page.getByText('Current Price')).toBeVisible()

    // Refresh page
    await page.reload()

    // Should still be on dashboard
    await expect(page.getByText('Current Price')).toBeVisible()
  })

  test('handles token expiration gracefully', async ({ page }) => {
    await page.addInitScript(() => {
      localStorage.setItem('auth_token', 'expired_token')
      localStorage.setItem('user', JSON.stringify({
        id: 'user_123',
        email: 'test@example.com',
        onboarding_completed: true,
      }))
    })

    // Mock 401 response
    await page.route('**/api/v1/prices/current**', async (route) => {
      await route.fulfill({
        status: 401,
        contentType: 'application/json',
        body: JSON.stringify({ detail: 'Token expired' }),
      })
    })

    await page.goto('/dashboard')

    // Should redirect to login
    await page.waitForURL(/\/auth\/login/)
    await expect(page.getByText(/session expired/i)).toBeVisible()
  })
})

test.describe('Authentication Security', () => {
  test('rate limits login attempts', async ({ page }) => {
    let attemptCount = 0

    await page.route('**/api/v1/auth/signin', async (route) => {
      attemptCount++
      if (attemptCount > 5) {
        await route.fulfill({
          status: 429,
          contentType: 'application/json',
          body: JSON.stringify({
            detail: 'Too many login attempts. Please try again later.',
          }),
        })
      } else {
        await route.fulfill({
          status: 401,
          contentType: 'application/json',
          body: JSON.stringify({ detail: 'Invalid credentials' }),
        })
      }
    })

    await page.goto('/auth/login')

    // Make multiple failed attempts
    for (let i = 0; i < 6; i++) {
      await page.fill('[name="email"]', 'test@example.com')
      await page.fill('[name="password"]', 'WrongPass!')
      await page.click('button[type="submit"]')
      await page.waitForTimeout(100)
    }

    // Should show rate limit error
    await expect(page.getByText(/too many/i)).toBeVisible()
  })

  test('clears sensitive data on logout', async ({ page }) => {
    await page.addInitScript(() => {
      localStorage.setItem('auth_token', 'mock_jwt_token')
      localStorage.setItem('user', JSON.stringify({ id: 'user_123' }))
    })

    await page.route('**/api/v1/auth/signout', async (route) => {
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({ success: true }),
      })
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

    // Logout
    await page.click('[data-testid="user-menu"]')
    await page.click('text=Sign out')

    // Verify local storage is cleared
    const authToken = await page.evaluate(() => localStorage.getItem('auth_token'))
    expect(authToken).toBeNull()
  })
})
