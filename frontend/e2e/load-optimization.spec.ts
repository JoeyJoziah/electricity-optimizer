import { test, expect } from '@playwright/test'

test.describe('Load Optimization Flow', () => {
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
            appliances: [],
          },
        })
      )
    })

    // Mock optimization API
    await page.route('**/api/v1/optimization/schedule', async (route) => {
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({
          schedules: [
            {
              applianceId: 'dishwasher_1',
              applianceName: 'Dishwasher',
              scheduledStart: '2024-01-16T02:00:00Z',
              scheduledEnd: '2024-01-16T04:00:00Z',
              estimatedCost: 0.30,
              savings: 0.15,
              savingsPercent: 33,
              reason: 'Cheapest period between 2-4 AM',
              priceAtScheduledTime: 0.15,
              priceIfRunNow: 0.30,
            },
            {
              applianceId: 'washing_machine_1',
              applianceName: 'Washing Machine',
              scheduledStart: '2024-01-16T03:00:00Z',
              scheduledEnd: '2024-01-16T05:00:00Z',
              estimatedCost: 0.45,
              savings: 0.22,
              savingsPercent: 33,
              reason: 'Off-peak pricing period',
              priceAtScheduledTime: 0.15,
              priceIfRunNow: 0.30,
            },
          ],
          totalSavings: 0.37,
          totalCost: 0.75,
          optimizationScore: 95,
        }),
      })
    })

    // Mock potential savings API
    await page.route('**/api/v1/optimization/potential-savings**', async (route) => {
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({
          dailySavings: 0.37,
          weeklySavings: 2.59,
          monthlySavings: 11.10,
          annualSavings: 135.05,
        }),
      })
    })

    // Mock price forecast for timeline
    await page.route('**/api/v1/prices/forecast**', async (route) => {
      const hours = Array.from({ length: 24 }, (_, i) => ({
        hour: i,
        price: 0.15 + Math.sin(i / 4) * 0.10, // Simulate price variation
        confidence: [0.10, 0.25],
        zone: i >= 1 && i <= 5 ? 'cheap' : i >= 17 && i <= 21 ? 'expensive' : 'normal',
      }))
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({ forecast: hours }),
      })
    })
  })

  test('user can configure and optimize appliance schedule', async ({ page }) => {
    await page.goto('/optimize')

    // Page should load
    await expect(page.getByRole('heading', { name: 'Load Optimization' })).toBeVisible()

    // Add appliances
    await page.click('text=Add Appliance')
    await page.selectOption('[name="appliance_type"]', 'dishwasher')
    await page.fill('[name="power_kw"]', '1.5')
    await page.fill('[name="duration_hours"]', '2')
    await page.fill('[name="earliest_start"]', '18:00')
    await page.fill('[name="latest_end"]', '06:00')
    await page.click('button:has-text("Add")')

    // Verify appliance added
    await expect(page.getByText('Dishwasher')).toBeVisible()
    await expect(page.getByText('1.5 kW')).toBeVisible()

    // Click optimize
    await page.click('button:has-text("Optimize Schedule")')

    // Wait for optimization (ML inference)
    await expect(page.getByText('Optimization Complete')).toBeVisible({ timeout: 10000 })

    // Verify results
    await expect(page.getByText('Estimated Savings')).toBeVisible()
    await expect(page.getByText('Optimal Start Time')).toBeVisible()

    // Check schedule timeline
    const timeline = page.locator('[data-testid="schedule-timeline"]')
    await expect(timeline).toBeVisible()

    // Verify cheapest period highlighted
    await expect(page.locator('.optimal-period')).toHaveCount(1)

    // Save schedule
    await page.click('button:has-text("Save Schedule")')
    await expect(page.getByText('Schedule saved')).toBeVisible()
  })

  test('displays schedule timeline with price zones', async ({ page }) => {
    // Add appliance via local storage
    await page.addInitScript(() => {
      const settings = JSON.parse(localStorage.getItem('electricity-optimizer-settings') || '{}')
      settings.state.appliances = [
        { id: '1', name: 'Washing Machine', powerKw: 2, durationHours: 2, flexible: true },
      ]
      localStorage.setItem('electricity-optimizer-settings', JSON.stringify(settings))
    })

    await page.goto('/optimize')

    // Click optimize
    await page.click('button:has-text("Optimize Now")')

    // Wait for results
    await expect(page.getByText('Optimized Schedule')).toBeVisible()

    // Should show price zones
    await expect(page.getByTestId('price-zone-cheap')).toBeVisible()
    await expect(page.getByTestId('price-zone-expensive')).toBeVisible()
  })

  test('shows optimization score', async ({ page }) => {
    await page.addInitScript(() => {
      const settings = JSON.parse(localStorage.getItem('electricity-optimizer-settings') || '{}')
      settings.state.appliances = [
        { id: '1', name: 'Dishwasher', powerKw: 1.5, durationHours: 2, flexible: true },
      ]
      localStorage.setItem('electricity-optimizer-settings', JSON.stringify(settings))
    })

    await page.goto('/optimize')
    await page.click('button:has-text("Optimize Now")')

    // Should show optimization score
    await expect(page.getByTestId('optimization-score')).toBeVisible()
    await expect(page.getByTestId('optimization-score')).toContainText('95')
  })

  test('can add multiple appliances', async ({ page }) => {
    await page.goto('/optimize')

    // Add dishwasher
    await page.click('button:has-text("Dishwasher")')
    await expect(page.getByText('Dishwasher').first()).toBeVisible()

    // Add washing machine
    await page.click('button:has-text("Washing Machine")')
    await expect(page.getByText('Washing Machine')).toBeVisible()

    // Add EV charger
    await page.click('button:has-text("EV Charger")')
    await expect(page.getByText('EV Charger')).toBeVisible()

    // Should show 3 appliances
    await expect(page.locator('[data-testid^="appliance-card"]')).toHaveCount(3)
  })

  test('can edit appliance settings', async ({ page }) => {
    await page.goto('/optimize')

    // Add appliance
    await page.click('button:has-text("Dishwasher")')

    // Click edit on appliance
    await page.locator('[data-testid="appliance-card-1"] [data-testid="edit-button"]').click()

    // Change power
    await page.fill('[name="power_kw"]', '2.0')

    // Change time window
    await page.fill('[name="earliest_start"]', '20:00')
    await page.fill('[name="latest_end"]', '08:00')

    // Save
    await page.click('button:has-text("Save")')

    // Verify changes
    await expect(page.getByText('2.0 kW')).toBeVisible()
  })

  test('can remove appliance', async ({ page }) => {
    await page.goto('/optimize')

    // Add appliance
    await page.click('button:has-text("Dishwasher")')
    await expect(page.getByText('Dishwasher').first()).toBeVisible()

    // Remove appliance
    await page.locator('[data-testid="appliance-card-1"] [data-testid="delete-button"]').click()

    // Confirm deletion
    await page.click('button:has-text("Confirm")')

    // Should show empty state
    await expect(page.getByText('No appliances added yet')).toBeVisible()
  })

  test('shows savings projections', async ({ page }) => {
    await page.addInitScript(() => {
      const settings = JSON.parse(localStorage.getItem('electricity-optimizer-settings') || '{}')
      settings.state.appliances = [
        { id: '1', name: 'Dishwasher', powerKw: 1.5, durationHours: 2, flexible: true },
      ]
      localStorage.setItem('electricity-optimizer-settings', JSON.stringify(settings))
    })

    await page.goto('/optimize')

    // Should show savings projections
    await expect(page.getByText('Daily Savings')).toBeVisible()
    await expect(page.getByText('$0.37')).toBeVisible()

    await expect(page.getByText('Weekly Savings')).toBeVisible()
    await expect(page.getByText('$2.59')).toBeVisible()

    await expect(page.getByText('Monthly Savings')).toBeVisible()
    await expect(page.getByText('$11.10')).toBeVisible()

    await expect(page.getByText('Annual Savings')).toBeVisible()
    await expect(page.getByText('$135.05')).toBeVisible()
  })

  test('can set appliance as non-flexible', async ({ page }) => {
    await page.goto('/optimize')

    // Add appliance
    await page.click('button:has-text("Dishwasher")')

    // Toggle flexibility off
    const checkbox = page.locator('[data-testid="appliance-card-1"] input[type="checkbox"]')
    await checkbox.uncheck()

    // Should be marked as fixed time
    await expect(page.getByText('Fixed time')).toBeVisible()
  })

  test('shows why schedule was chosen', async ({ page }) => {
    await page.addInitScript(() => {
      const settings = JSON.parse(localStorage.getItem('electricity-optimizer-settings') || '{}')
      settings.state.appliances = [
        { id: '1', name: 'Dishwasher', powerKw: 1.5, durationHours: 2, flexible: true },
      ]
      localStorage.setItem('electricity-optimizer-settings', JSON.stringify(settings))
    })

    await page.goto('/optimize')
    await page.click('button:has-text("Optimize Now")')

    // Click on schedule block for details
    await page.click('[data-testid="schedule-block-1"]')

    // Should show reason
    await expect(page.getByText('Cheapest period between 2-4 AM')).toBeVisible()
    await expect(page.getByText('Price at scheduled time: $0.15/kWh')).toBeVisible()
    await expect(page.getByText('Price if run now: $0.30/kWh')).toBeVisible()
  })

  test('can create recurring schedule', async ({ page }) => {
    await page.addInitScript(() => {
      const settings = JSON.parse(localStorage.getItem('electricity-optimizer-settings') || '{}')
      settings.state.appliances = [
        { id: '1', name: 'Dishwasher', powerKw: 1.5, durationHours: 2, flexible: true },
      ]
      localStorage.setItem('electricity-optimizer-settings', JSON.stringify(settings))
    })

    await page.goto('/optimize')
    await page.click('button:has-text("Optimize Now")')

    // Toggle recurring
    await page.check('[name="recurring"]')

    // Select days
    await page.check('[name="day_monday"]')
    await page.check('[name="day_wednesday"]')
    await page.check('[name="day_friday"]')

    // Save schedule
    await page.click('button:has-text("Save Schedule")')

    await expect(page.getByText('Recurring schedule saved')).toBeVisible()
  })

  test('can enable smart notifications', async ({ page }) => {
    await page.goto('/optimize')

    // Add appliance
    await page.click('button:has-text("Dishwasher")')
    await page.click('button:has-text("Optimize Now")')

    // Enable notifications
    await page.check('[name="enable_notifications"]')

    // Should show notification options
    await expect(page.getByText('30 minutes before')).toBeVisible()

    // Save schedule
    await page.click('button:has-text("Save Schedule")')

    await expect(page.getByText('Notifications enabled')).toBeVisible()
  })
})

test.describe('Optimization Mobile View', () => {
  test('is responsive on mobile', async ({ page }) => {
    await page.addInitScript(() => {
      localStorage.setItem('auth_token', 'mock_jwt_token')
      localStorage.setItem('user', JSON.stringify({ id: 'user_123' }))
    })

    await page.setViewportSize({ width: 375, height: 667 })
    await page.goto('/optimize')

    // Main elements should still be visible
    await expect(page.getByRole('heading', { name: 'Load Optimization' })).toBeVisible()
    await expect(page.getByText('Your Appliances')).toBeVisible()

    // Quick add buttons should be in a scrollable container
    const quickAddContainer = page.locator('[data-testid="quick-add-container"]')
    await expect(quickAddContainer).toBeVisible()
  })

  test('timeline scrolls horizontally on mobile', async ({ page }) => {
    await page.addInitScript(() => {
      localStorage.setItem('auth_token', 'mock_jwt_token')
      localStorage.setItem('user', JSON.stringify({ id: 'user_123' }))
      const settings = JSON.parse(localStorage.getItem('electricity-optimizer-settings') || '{}')
      settings.state = {
        ...settings.state,
        appliances: [{ id: '1', name: 'Dishwasher', powerKw: 1.5, durationHours: 2, flexible: true }],
      }
      localStorage.setItem('electricity-optimizer-settings', JSON.stringify(settings))
    })

    await page.route('**/api/v1/optimization/schedule', async (route) => {
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({
          schedules: [{ applianceId: '1', scheduledStart: '02:00', scheduledEnd: '04:00' }],
          totalSavings: 0.37,
        }),
      })
    })

    await page.setViewportSize({ width: 375, height: 667 })
    await page.goto('/optimize')
    await page.click('button:has-text("Optimize Now")')

    // Timeline should be scrollable
    const timeline = page.locator('[data-testid="schedule-timeline"]')
    await expect(timeline).toHaveCSS('overflow-x', 'auto')
  })
})

test.describe('Optimization Error Handling', () => {
  test('handles API error gracefully', async ({ page }) => {
    await page.addInitScript(() => {
      localStorage.setItem('auth_token', 'mock_jwt_token')
      localStorage.setItem('user', JSON.stringify({ id: 'user_123' }))
    })

    await page.route('**/api/v1/optimization/schedule', async (route) => {
      await route.fulfill({
        status: 500,
        contentType: 'application/json',
        body: JSON.stringify({ detail: 'Optimization service unavailable' }),
      })
    })

    await page.goto('/optimize')
    await page.click('button:has-text("Dishwasher")')
    await page.click('button:has-text("Optimize Now")')

    // Should show error message
    await expect(page.getByText(/optimization failed/i)).toBeVisible()
    await expect(page.getByText(/try again/i)).toBeVisible()
  })

  test('shows loading state during optimization', async ({ page }) => {
    await page.addInitScript(() => {
      localStorage.setItem('auth_token', 'mock_jwt_token')
      localStorage.setItem('user', JSON.stringify({ id: 'user_123' }))
    })

    await page.route('**/api/v1/optimization/schedule', async (route) => {
      await new Promise((resolve) => setTimeout(resolve, 2000))
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({ schedules: [], totalSavings: 0 }),
      })
    })

    await page.goto('/optimize')
    await page.click('button:has-text("Dishwasher")')
    await page.click('button:has-text("Optimize Now")')

    // Should show loading indicator
    await expect(page.getByTestId('optimization-loading')).toBeVisible()
    await expect(page.getByText(/optimizing/i)).toBeVisible()
  })
})
