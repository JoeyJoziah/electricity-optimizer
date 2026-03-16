import { test, expect } from './fixtures'
import type { MockCommunityPost } from './helpers/api-mocks'

const COMMUNITY_POSTS: MockCommunityPost[] = [
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
]

const COMMUNITY_STATS = {
  total_users: 142,
  avg_savings_pct: 18.5,
  top_tip: 'Switch to off-peak usage to save 15-20%',
  top_tip_author: 'EnergyPro',
  data_since: '2026-01-15',
}

test.describe('Community Page', () => {
  test.use({
    apiMockConfig: {
      communityPosts: COMMUNITY_POSTS,
      communityStats: COMMUNITY_STATS,
      communityVote: { voted: true },
    },
  })

  test('community page renders post list', { tag: ['@smoke'] }, async ({ authenticatedPage: page }) => {
    await page.goto('/community')

    // Page heading
    await expect(page.getByRole('heading', { name: 'Community' })).toBeVisible()

    // Posts should render
    await expect(page.getByText('Save with off-peak charging')).toBeVisible()
    await expect(page.getByText('Eversource rate update')).toBeVisible()
  })

  test('community stats banner displays', { tag: ['@smoke'] }, async ({ authenticatedPage: page }) => {
    await page.goto('/community')

    // Stats banner should show user count and savings
    await expect(page.getByText('142')).toBeVisible()
    await expect(page.getByText(/18\.5%/)).toBeVisible()
  })

  test('vote button updates count on click', { tag: ['@regression'] }, async ({ authenticatedPage: page }) => {
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
