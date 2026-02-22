import { test, expect } from '@playwright/test'

test.describe('GDPR Compliance Flow', () => {
  test.beforeEach(async ({ page }) => {
    // Set up authenticated state
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
            region: 'US_CT',
            annualUsageKwh: 2900,
            peakDemandKw: 3,
          },
        })
      )
    })

    // Mock GDPR endpoints
    await page.route('**/api/v1/compliance/data-export', async (route) => {
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({
          data: {
            user: {
              id: 'user_123',
              email: 'test@example.com',
              created_at: '2024-01-15T10:00:00Z',
            },
            preferences: {
              region: 'US_CT',
              notification_enabled: true,
            },
            usage_data: [
              { date: '2024-01-15', usage_kwh: 12.5 },
              { date: '2024-01-16', usage_kwh: 10.2 },
            ],
            consents: [
              {
                type: 'data_processing',
                given: true,
                timestamp: '2024-01-15T10:00:00Z',
              },
            ],
          },
          exported_at: new Date().toISOString(),
        }),
        headers: {
          'Content-Disposition': 'attachment; filename="user-data-export.json"',
        },
      })
    })

    await page.route('**/api/v1/compliance/data-delete', async (route) => {
      const body = JSON.parse(route.request().postData() || '{}')
      if (body.confirm_email === 'test@example.com') {
        await route.fulfill({
          status: 200,
          contentType: 'application/json',
          body: JSON.stringify({
            success: true,
            message: 'Account and all data permanently deleted',
            deletion_reference: 'DEL-12345',
          }),
        })
      } else {
        await route.fulfill({
          status: 400,
          contentType: 'application/json',
          body: JSON.stringify({
            detail: 'Email confirmation does not match',
          }),
        })
      }
    })

    await page.route('**/api/v1/compliance/consents', async (route) => {
      if (route.request().method() === 'GET') {
        await route.fulfill({
          status: 200,
          contentType: 'application/json',
          body: JSON.stringify({
            consents: [
              {
                type: 'data_processing',
                description: 'Processing of usage data for optimization',
                given: true,
                timestamp: '2024-01-15T10:00:00Z',
                required: true,
              },
              {
                type: 'marketing',
                description: 'Email marketing communications',
                given: false,
                timestamp: null,
                required: false,
              },
              {
                type: 'analytics',
                description: 'Anonymous usage analytics',
                given: true,
                timestamp: '2024-01-15T10:00:00Z',
                required: false,
              },
            ],
          }),
        })
      } else {
        await route.fulfill({
          status: 200,
          contentType: 'application/json',
          body: JSON.stringify({ success: true }),
        })
      }
    })

    await page.route('**/api/v1/compliance/consent-history', async (route) => {
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({
          history: [
            {
              type: 'data_processing',
              action: 'granted',
              timestamp: '2024-01-15T10:00:00Z',
              ip_address: '192.168.1.1',
              user_agent: 'Mozilla/5.0...',
            },
            {
              type: 'analytics',
              action: 'granted',
              timestamp: '2024-01-15T10:00:00Z',
              ip_address: '192.168.1.1',
              user_agent: 'Mozilla/5.0...',
            },
          ],
        }),
      })
    })
  })

  test('navigates to privacy settings', async ({ page }) => {
    await page.goto('/settings')

    await expect(page.getByRole('heading', { name: 'Privacy & Data' })).toBeVisible()
  })

  test('user can export all data', async ({ page }) => {
    await page.goto('/settings')

    // Find privacy section
    await page.click('text=Privacy & Data')

    // Click export data button
    const downloadPromise = page.waitForEvent('download')
    await page.click('button:has-text("Export")')

    // Verify download starts
    const download = await downloadPromise
    expect(download.suggestedFilename()).toContain('user-data-export')
    expect(download.suggestedFilename()).toContain('.json')
  })

  test('shows export data confirmation', async ({ page }) => {
    await page.goto('/settings')

    await page.click('button:has-text("Export")')

    // Should show success message
    await expect(page.getByText(/data exported successfully/i)).toBeVisible()
  })

  test('user can view consent settings', async ({ page }) => {
    await page.goto('/settings/privacy')

    await expect(page.getByText('Your Consent Settings')).toBeVisible()

    // Should show different consent types
    await expect(page.getByText('Processing of usage data')).toBeVisible()
    await expect(page.getByText('Email marketing')).toBeVisible()
    await expect(page.getByText('Anonymous usage analytics')).toBeVisible()
  })

  test('user can update consent preferences', async ({ page }) => {
    await page.goto('/settings/privacy')

    // Toggle marketing consent
    const marketingCheckbox = page.locator('[name="consent_marketing"]')
    await marketingCheckbox.check()

    // Save changes
    await page.click('button:has-text("Save Preferences")')

    // Should show success message
    await expect(page.getByText(/preferences saved/i)).toBeVisible()
  })

  test('shows required consents as non-optional', async ({ page }) => {
    await page.goto('/settings/privacy')

    // Data processing should be marked as required
    await expect(page.getByText(/required/i)).toBeVisible()

    // Required consents should be disabled
    const requiredCheckbox = page.locator('[name="consent_data_processing"]')
    await expect(requiredCheckbox).toBeDisabled()
  })

  test('user can view consent history', async ({ page }) => {
    await page.goto('/settings/privacy')

    // Click view history
    await page.click('text=View Consent History')

    // Should show consent history
    await expect(page.getByText('Consent History')).toBeVisible()
    await expect(page.getByText('data_processing')).toBeVisible()
    await expect(page.getByText('granted')).toBeVisible()
  })

  test('user can delete all data with confirmation', async ({ page }) => {
    await page.goto('/settings')

    // Click delete data button
    await page.click('button:has-text("Delete My Data")')

    // Should show confirmation dialog
    await expect(page.getByText('Are you sure?')).toBeVisible()
    await expect(page.getByText(/cannot be undone/i)).toBeVisible()

    // Type confirmation email
    await page.fill('[name="confirm_email"]', 'test@example.com')
    await page.click('button:has-text("Permanently Delete")')

    // Should show success and redirect
    await expect(page.getByText(/account deleted/i)).toBeVisible()
    await page.waitForURL('/')
  })

  test('deletion requires correct email confirmation', async ({ page }) => {
    await page.goto('/settings')

    await page.click('button:has-text("Delete My Data")')

    // Type wrong email
    await page.fill('[name="confirm_email"]', 'wrong@example.com')
    await page.click('button:has-text("Permanently Delete")')

    // Should show error
    await expect(page.getByText(/does not match/i)).toBeVisible()
  })

  test('can cancel deletion', async ({ page }) => {
    await page.goto('/settings')

    await page.click('button:has-text("Delete My Data")')

    // Cancel
    await page.click('button:has-text("Cancel")')

    // Dialog should close
    await expect(page.getByText('Are you sure?')).not.toBeVisible()
  })

  test('shows data retention information', async ({ page }) => {
    await page.goto('/settings/privacy')

    await expect(page.getByText(/data retention/i)).toBeVisible()
    await expect(page.getByText(/30 days/i)).toBeVisible()
  })

  test('displays privacy policy link', async ({ page }) => {
    await page.goto('/settings/privacy')

    const privacyLink = page.getByRole('link', { name: /privacy policy/i })
    await expect(privacyLink).toBeVisible()
    await expect(privacyLink).toHaveAttribute('href', '/privacy-policy')
  })

  test('displays terms of service link', async ({ page }) => {
    await page.goto('/settings/privacy')

    const termsLink = page.getByRole('link', { name: /terms of service/i })
    await expect(termsLink).toBeVisible()
    await expect(termsLink).toHaveAttribute('href', '/terms')
  })
})

test.describe('Cookie Consent', () => {
  test('shows cookie consent banner on first visit', async ({ page }) => {
    // Clear any existing consent
    await page.context().clearCookies()

    await page.goto('/')

    // Should show cookie banner
    await expect(page.getByTestId('cookie-banner')).toBeVisible()
    await expect(page.getByText(/we use cookies/i)).toBeVisible()
  })

  test('can accept all cookies', async ({ page }) => {
    await page.context().clearCookies()

    await page.goto('/')

    await page.click('button:has-text("Accept All")')

    // Banner should disappear
    await expect(page.getByTestId('cookie-banner')).not.toBeVisible()

    // Reload and verify banner doesn't show
    await page.reload()
    await expect(page.getByTestId('cookie-banner')).not.toBeVisible()
  })

  test('can accept only essential cookies', async ({ page }) => {
    await page.context().clearCookies()

    await page.goto('/')

    await page.click('button:has-text("Essential Only")')

    // Banner should disappear
    await expect(page.getByTestId('cookie-banner')).not.toBeVisible()
  })

  test('can customize cookie preferences', async ({ page }) => {
    await page.context().clearCookies()

    await page.goto('/')

    await page.click('text=Customize')

    // Should show cookie settings
    await expect(page.getByText('Cookie Preferences')).toBeVisible()
    await expect(page.getByText('Essential')).toBeVisible()
    await expect(page.getByText('Analytics')).toBeVisible()
    await expect(page.getByText('Marketing')).toBeVisible()

    // Essential should be checked and disabled
    const essentialCheckbox = page.locator('[name="essential"]')
    await expect(essentialCheckbox).toBeChecked()
    await expect(essentialCheckbox).toBeDisabled()

    // Toggle analytics
    await page.check('[name="analytics"]')
    await page.click('button:has-text("Save Preferences")')

    // Banner should close
    await expect(page.getByTestId('cookie-banner')).not.toBeVisible()
  })
})

test.describe('Data Subject Requests', () => {
  test.beforeEach(async ({ page }) => {
    await page.addInitScript(() => {
      localStorage.setItem('auth_token', 'mock_jwt_token')
      localStorage.setItem('user', JSON.stringify({
        id: 'user_123',
        email: 'test@example.com',
      }))
    })

    await page.route('**/api/v1/compliance/dsr', async (route) => {
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({
          request_id: 'DSR-12345',
          type: 'rectification',
          status: 'submitted',
          submitted_at: new Date().toISOString(),
          expected_completion: new Date(Date.now() + 30 * 24 * 60 * 60 * 1000).toISOString(),
        }),
      })
    })
  })

  test('can submit data rectification request', async ({ page }) => {
    await page.goto('/settings/privacy/data-requests')

    await page.click('button:has-text("Request Data Rectification")')

    // Fill form
    await page.fill('[name="details"]', 'Please update my email address to newemail@example.com')
    await page.click('button:has-text("Submit Request")')

    // Should show confirmation
    await expect(page.getByText(/request submitted/i)).toBeVisible()
    await expect(page.getByText('DSR-12345')).toBeVisible()
  })

  test('shows data request status', async ({ page }) => {
    await page.route('**/api/v1/compliance/dsr/status', async (route) => {
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({
          requests: [
            {
              id: 'DSR-12345',
              type: 'rectification',
              status: 'in_progress',
              submitted_at: '2024-01-15T10:00:00Z',
              expected_completion: '2024-02-14T10:00:00Z',
            },
          ],
        }),
      })
    })

    await page.goto('/settings/privacy/data-requests')

    await expect(page.getByText('DSR-12345')).toBeVisible()
    await expect(page.getByText('in_progress')).toBeVisible()
  })
})
