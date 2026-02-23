import { test, expect } from '@playwright/test'

test.describe('SSE Streaming - Dashboard Real-Time Updates', () => {
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
            annualUsageKwh: 10500,
            peakDemandKw: 3,
          },
        })
      )
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
              trend: 'stable',
              changePercent: 0,
            },
          ],
        }),
      })
    })

    // Mock price history endpoint
    await page.route('**/api/v1/prices/history**', async (route) => {
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({
          prices: [
            { time: new Date(Date.now() - 3600000).toISOString(), price: 0.27 },
            { time: new Date(Date.now() - 1800000).toISOString(), price: 0.26 },
            { time: new Date().toISOString(), price: 0.25 },
          ],
        }),
      })
    })

    // Mock forecast endpoint
    await page.route('**/api/v1/prices/forecast**', async (route) => {
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({
          forecast: [
            { hour: 1, price: 0.23, confidence: [0.21, 0.25] },
            { hour: 2, price: 0.20, confidence: [0.18, 0.22] },
            { hour: 3, price: 0.18, confidence: [0.16, 0.20] },
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
            },
          ],
        }),
      })
    })
  })

  // Realtime indicator has class "hidden sm:flex" — not visible on mobile viewports
  test('dashboard shows realtime indicator', async ({ page, isMobile }) => {
    test.skip(isMobile === true, 'Realtime indicator is hidden on mobile (sm:flex)')

    // Mock SSE endpoint to simulate a successful connection
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

    await page.goto('/dashboard')

    // Dashboard should load
    await expect(page.getByText('Current Price').first()).toBeVisible()

    // Realtime indicator should be present
    await expect(page.getByTestId('realtime-indicator')).toBeVisible()
  })

  test('price data renders on dashboard load', async ({ page }) => {
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

    await page.goto('/dashboard')

    // Current price should display
    await expect(page.getByTestId('current-price').first()).toBeVisible()
    await expect(page.getByTestId('current-price').first()).toContainText('0.25')

    // Price trend indicator should be visible
    await expect(page.getByTestId('price-trend').first()).toBeVisible()
  })

  test('handles SSE connection failure gracefully', async ({ page }) => {
    // Mock SSE endpoint to return an error
    await page.route('**/api/v1/prices/stream**', async (route) => {
      await route.fulfill({
        status: 500,
        contentType: 'text/plain',
        body: 'Internal Server Error',
      })
    })

    await page.goto('/dashboard')

    // Dashboard should still load with data from REST endpoints
    await expect(page.getByText('Current Price').first()).toBeVisible()
    await expect(page.getByTestId('current-price').first()).toBeVisible()

    // The page should not crash even when SSE fails
    await expect(page.getByText('Price History')).toBeVisible()
  })

  test('dashboard loads all widgets without SSE dependency', async ({ page }) => {
    // Block SSE entirely to simulate network failure
    await page.route('**/api/v1/prices/stream**', async (route) => {
      await route.abort('connectionrefused')
    })

    await page.goto('/dashboard')

    // All main sections should still render from REST API data
    await expect(page.getByText('Current Price').first()).toBeVisible()
    await expect(page.getByText('Total Saved')).toBeVisible()
    await expect(page.getByText('Optimal Times')).toBeVisible()
    await expect(page.getByRole('heading', { name: 'Top Suppliers' })).toBeVisible()
    await expect(page.getByText('Price History')).toBeVisible()
    await expect(page.getByText('24-Hour Forecast').first()).toBeVisible()
    await expect(page.getByText('Top Suppliers')).toBeVisible()
  })

  test('SSE delivers price update data in correct format', async ({ page }) => {
    const timestamp = new Date().toISOString()

    // Fulfill SSE with a properly formatted event
    await page.route('**/api/v1/prices/stream**', async (route) => {
      const sseBody = [
        `data: {"region": "US_CT", "supplier": "Eversource", "price_per_kwh": "0.24", "currency": "USD", "is_peak": false, "timestamp": "${timestamp}"}`,
        '',
        `data: {"region": "US_CT", "supplier": "Eversource", "price_per_kwh": "0.23", "currency": "USD", "is_peak": false, "timestamp": "${timestamp}"}`,
        '',
        '',
      ].join('\n')

      await route.fulfill({
        status: 200,
        contentType: 'text/event-stream',
        headers: {
          'Cache-Control': 'no-cache',
          'Connection': 'keep-alive',
        },
        body: sseBody,
      })
    })

    await page.goto('/dashboard')

    // Dashboard should render price data
    await expect(page.getByTestId('current-price').first()).toBeVisible()
  })

  test('multiple price updates do not break the dashboard', async ({ page }) => {
    // Create multiple SSE events
    const events: string[] = []
    for (let i = 0; i < 5; i++) {
      const price = (0.25 - i * 0.01).toFixed(2)
      const ts = new Date(Date.now() + i * 30000).toISOString()
      events.push(
        `data: {"region": "US_CT", "supplier": "Eversource", "price_per_kwh": "${price}", "currency": "USD", "is_peak": false, "timestamp": "${ts}"}`
      )
      events.push('')
    }
    events.push('')

    await page.route('**/api/v1/prices/stream**', async (route) => {
      await route.fulfill({
        status: 200,
        contentType: 'text/event-stream',
        headers: {
          'Cache-Control': 'no-cache',
          'Connection': 'keep-alive',
        },
        body: events.join('\n'),
      })
    })

    await page.goto('/dashboard')

    // Dashboard should handle multiple updates without errors
    await expect(page.getByTestId('current-price').first()).toBeVisible()
    await expect(page.getByText('Price History')).toBeVisible()
    await expect(page.getByText('24-Hour Forecast').first()).toBeVisible()

    // No error states should appear
    await expect(page.getByText(/failed to load/i)).not.toBeVisible()
  })

  test('dashboard shows decreasing price alert banner when trend is down', async ({ page }) => {
    // Mock current prices with decreasing trend
    await page.route('**/api/v1/prices/current**', async (route) => {
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({
          prices: [
            {
              region: 'US_CT',
              price: 0.20,
              timestamp: new Date().toISOString(),
              trend: 'decreasing',
              changePercent: -5.0,
            },
          ],
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
        body: 'data: {"region": "US_CT", "supplier": "Eversource", "price_per_kwh": "0.20", "currency": "USD", "is_peak": false, "timestamp": "' + new Date().toISOString() + '"}\n\n',
      })
    })

    await page.goto('/dashboard')

    // Should show the price dropping alert banner
    await expect(page.getByText(/prices dropping/i)).toBeVisible()
    await expect(page.getByText(/good time for high-energy tasks/i)).toBeVisible()
  })
})

test.describe('SSE Streaming - Error Recovery', () => {
  test.beforeEach(async ({ page }) => {
    await page.addInitScript(() => {
      localStorage.setItem('auth_token', 'mock_jwt_token')
      localStorage.setItem('user', JSON.stringify({
        id: 'user_123',
        email: 'test@example.com',
        onboarding_completed: true,
      }))
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
              trend: 'stable',
              changePercent: 0,
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

  test('dashboard remains functional when SSE returns 404', async ({ page }) => {
    await page.route('**/api/v1/prices/stream**', async (route) => {
      await route.fulfill({
        status: 404,
        contentType: 'application/json',
        body: JSON.stringify({ detail: 'SSE endpoint not found' }),
      })
    })

    await page.goto('/dashboard')

    // Dashboard should still function from REST data
    await expect(page.getByText('Current Price').first()).toBeVisible()
    await expect(page.getByTestId('current-price').first()).toContainText('0.25')
    await expect(page.getByText('Price History')).toBeVisible()
  })

  test('dashboard handles malformed SSE data without crashing', async ({ page }) => {
    await page.route('**/api/v1/prices/stream**', async (route) => {
      // Send malformed SSE data (not valid JSON)
      await route.fulfill({
        status: 200,
        contentType: 'text/event-stream',
        headers: {
          'Cache-Control': 'no-cache',
          'Connection': 'keep-alive',
        },
        body: 'data: {invalid json here}\n\ndata: not-json-at-all\n\n',
      })
    })

    await page.goto('/dashboard')

    // Dashboard should handle parse errors gracefully
    await expect(page.getByText('Current Price').first()).toBeVisible()
    await expect(page.getByTestId('current-price').first()).toBeVisible()

    // No crash - page remains interactive
    await expect(page.getByText('Price History')).toBeVisible()
  })

  test('dashboard is responsive on mobile even without SSE', async ({ page }) => {
    await page.route('**/api/v1/prices/stream**', async (route) => {
      await route.abort('connectionrefused')
    })

    await page.setViewportSize({ width: 375, height: 667 })
    await page.goto('/dashboard')

    // Dashboard should still load on mobile
    await expect(page.getByText('Current Price').first()).toBeVisible()

    // Sidebar should be hidden on mobile
    await expect(page.getByRole('navigation')).not.toBeVisible()
  })
})
