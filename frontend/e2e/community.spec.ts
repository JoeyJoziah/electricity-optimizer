import { test, expect } from '@playwright/test'
import { mockBetterAuth, setAuthenticatedState } from './helpers/auth'

test.describe('Community Page', () => {
  test.beforeEach(async ({ page }) => {
    await mockBetterAuth(page)
    await setAuthenticatedState(page)

    await page.addInitScript(() => {
      localStorage.setItem(
        'electricity-optimizer-settings',
        JSON.stringify({
          state: {
            region: 'US_CT',
            annualUsageKwh: 10500,
            utilityTypes: ['electricity'],
            displayPreferences: { currency: 'USD', theme: 'system', timeFormat: '12h' },
          },
        })
      )
    })

    // Mock auth session
    await page.route('**/api/auth/get-session', async (route) => {
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({
          user: { id: 'user_e2e_123', email: 'test@example.com', name: 'Test User', emailVerified: true },
          session: { id: 'session_e2e_123', userId: 'user_e2e_123', token: 'mock-session-token-e2e-test', expiresAt: new Date(Date.now() + 86400000).toISOString() },
        }),
      })
    })

    // Mock community posts
    await page.route('**/api/v1/community/posts**', async (route) => {
      if (route.request().method() === 'GET') {
        await route.fulfill({
          status: 200,
          contentType: 'application/json',
          body: JSON.stringify({
            posts: [
              {
                id: 'post-1',
                user_id: 'user-other',
                region: 'US_CT',
                utility_type: 'electricity',
                post_type: 'tip',
                title: 'Save with off-peak charging',
                body: 'I switched to charging my EV at night and saved 30%.',
                upvotes: 5,
                is_hidden: false,
                is_pending_moderation: false,
                created_at: new Date().toISOString(),
              },
              {
                id: 'post-2',
                user_id: 'user-other-2',
                region: 'US_CT',
                utility_type: 'electricity',
                post_type: 'rate_report',
                title: 'Eversource rate update',
                body: 'New rate posted for residential.',
                rate_per_unit: 0.245,
                rate_unit: 'kWh',
                supplier_name: 'Eversource',
                upvotes: 3,
                is_hidden: false,
                is_pending_moderation: false,
                created_at: new Date().toISOString(),
              },
            ],
            total: 2,
            page: 1,
            per_page: 20,
          }),
        })
      } else if (route.request().method() === 'POST') {
        const body = JSON.parse(route.request().postData() || '{}')
        await route.fulfill({
          status: 201,
          contentType: 'application/json',
          body: JSON.stringify({
            id: 'post-new',
            user_id: 'user_e2e_123',
            region: body.region || 'US_CT',
            utility_type: body.utility_type || 'electricity',
            post_type: body.post_type || 'tip',
            title: body.title,
            body: body.body,
            upvotes: 0,
            is_hidden: false,
            is_pending_moderation: true,
            created_at: new Date().toISOString(),
          }),
        })
      }
    })

    // Mock community stats
    await page.route('**/api/v1/community/stats**', async (route) => {
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({
          total_users: 142,
          avg_savings_pct: 18.5,
          top_tip: 'Switch to off-peak usage to save 15-20%',
          top_tip_author: 'EnergyPro',
          data_since: '2026-01-15',
        }),
      })
    })

    // Mock vote endpoint
    await page.route('**/api/v1/community/posts/*/vote', async (route) => {
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({ voted: true }),
      })
    })

    // Catch-all for other API calls
    await page.route('**/api/v1/**', async (route) => {
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({}),
      })
    })
  })

  test('community page renders post list', async ({ page }) => {
    await page.goto('/community')

    // Page heading
    await expect(page.getByRole('heading', { name: 'Community' })).toBeVisible()

    // Posts should render
    await expect(page.getByText('Save with off-peak charging')).toBeVisible()
    await expect(page.getByText('Eversource rate update')).toBeVisible()
  })

  test('community stats banner displays', async ({ page }) => {
    await page.goto('/community')

    // Stats banner should show user count and savings
    await expect(page.getByText('142')).toBeVisible()
    await expect(page.getByText(/18\.5%/)).toBeVisible()
  })

  test('vote button updates count on click', async ({ page }) => {
    await page.goto('/community')

    // Find the first vote button and click it
    const voteButtons = page.getByTestId('vote-button')
    const firstVote = voteButtons.first()
    await expect(firstVote).toBeVisible()

    // Click to vote
    await firstVote.click()

    // Vote count should update (optimistic: 5 → 6)
    await expect(firstVote).toContainText('6')
  })
})
