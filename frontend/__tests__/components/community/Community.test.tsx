import { render, screen, fireEvent, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import '@testing-library/jest-dom'

// --- Mocks ---

// Mock settings store
jest.mock('@/lib/store/settings', () => ({
  useSettingsStore: (selector: (s: { region: string; utilityTypes: string[] }) => unknown) =>
    selector({ region: 'us_ct', utilityTypes: ['electricity', 'natural_gas'] }),
}))

// Mock auth
const mockUser = { id: 'user-1', name: 'Test User', email: 'test@example.com' }
let mockAuth = { user: mockUser, isAuthenticated: true, isLoading: false, signOut: jest.fn(), signIn: jest.fn(), signUp: jest.fn(), signInWithGoogle: jest.fn(), signInWithGitHub: jest.fn(), sendMagicLink: jest.fn() }

jest.mock('@/lib/hooks/useAuth', () => ({
  useAuth: () => mockAuth,
}))

// Mock Skeleton
jest.mock('@/components/ui/skeleton', () => ({
  Skeleton: (props: Record<string, unknown>) => <div data-testid="skeleton" {...props} />,
}))

// Mock community hooks
const mockPosts = {
  posts: [
    {
      id: 'post-1',
      title: 'Great tip for saving',
      body: 'Switch to off-peak usage to save up to 30% on your electricity bill.',
      post_type: 'tip',
      utility_type: 'electricity',
      region: 'us_ct',
      user_id: 'user-1',
      upvote_count: 5,
      created_at: new Date(Date.now() - 3600000).toISOString(),
      is_hidden: false,
      is_pending_moderation: false,
      rate_per_unit: null,
      rate_unit: null,
      supplier_name: null,
    },
    {
      id: 'post-2',
      title: 'Rate report for Eversource',
      body: 'Current rate from Eversource is quite competitive for the area.',
      post_type: 'rate_report',
      utility_type: 'electricity',
      region: 'us_ct',
      user_id: 'user-2',
      upvote_count: 3,
      created_at: new Date(Date.now() - 86400000).toISOString(),
      is_hidden: false,
      is_pending_moderation: false,
      rate_per_unit: 0.185,
      rate_unit: 'kWh',
      supplier_name: 'Eversource',
    },
    {
      id: 'post-3',
      title: 'Hidden post',
      body: 'This was flagged.',
      post_type: 'discussion',
      utility_type: 'electricity',
      region: 'us_ct',
      user_id: 'user-3',
      upvote_count: 0,
      created_at: new Date(Date.now() - 172800000).toISOString(),
      is_hidden: true,
      is_pending_moderation: false,
      rate_per_unit: null,
      rate_unit: null,
      supplier_name: null,
    },
    {
      id: 'post-4',
      title: 'My pending post',
      body: 'This is being reviewed by moderators.',
      post_type: 'tip',
      utility_type: 'electricity',
      region: 'us_ct',
      user_id: 'user-1',
      upvote_count: 0,
      created_at: new Date(Date.now() - 60000).toISOString(),
      is_hidden: false,
      is_pending_moderation: true,
      rate_per_unit: null,
      rate_unit: null,
      supplier_name: null,
    },
  ],
  page: 1,
  pages: 2,
  total: 8,
}

const mockStats = {
  user_count: 142,
  avg_savings_pct: 18.5,
  post_count: 87,
  since: '2025-06-01T00:00:00Z',
  top_tip: { title: 'Switch to off-peak hours', id: 'tip-1' },
}

let mockPostsLoading = false
let mockPostsError: Error | null = null
let mockStatsLoading = false
let mockStatsError: Error | null = null

const mockCreateMutate = jest.fn()
const mockVoteMutate = jest.fn()
const mockReportMutate = jest.fn()

jest.mock('@/lib/hooks/useCommunity', () => ({
  useCommunityPosts: () => ({
    data: mockPostsLoading ? undefined : mockPostsError ? undefined : mockPosts,
    isLoading: mockPostsLoading,
    error: mockPostsError,
  }),
  useCreatePost: () => ({
    mutate: mockCreateMutate,
    isPending: false,
    isError: false,
  }),
  useToggleVote: () => ({
    mutate: mockVoteMutate,
    isPending: false,
  }),
  useReportPost: () => ({
    mutate: mockReportMutate,
    isPending: false,
  }),
  useCommunityStats: () => ({
    data: mockStatsLoading ? undefined : mockStatsError ? undefined : mockStats,
    isLoading: mockStatsLoading,
    error: mockStatsError,
  }),
}))

// Import components after mocks
import { PostList } from '@/components/community/PostList'
import { PostForm } from '@/components/community/PostForm'
import { VoteButton } from '@/components/community/VoteButton'
import { ReportButton } from '@/components/community/ReportButton'
import { CommunityStats } from '@/components/community/CommunityStats'

describe('PostList', () => {
  beforeEach(() => {
    mockPostsLoading = false
    mockPostsError = null
    jest.clearAllMocks()
  })

  it('renders posts from mock data', () => {
    render(<PostList utilityType="electricity" currentUserId="user-1" />)

    expect(screen.getByTestId('post-list')).toBeInTheDocument()
    expect(screen.getByText('Great tip for saving')).toBeInTheDocument()
    expect(screen.getByText('Rate report for Eversource')).toBeInTheDocument()
  })

  it('shows "[Content under review]" for hidden posts (non-author)', () => {
    render(<PostList utilityType="electricity" currentUserId="user-1" />)

    expect(screen.getByTestId('post-post-3-hidden')).toBeInTheDocument()
    expect(screen.getByText('[Content under review]')).toBeInTheDocument()
  })

  it('shows "Your post is being reviewed" for author pending posts', () => {
    render(<PostList utilityType="electricity" currentUserId="user-1" />)

    expect(screen.getByTestId('post-post-4-pending')).toBeInTheDocument()
    expect(screen.getByText('Your post is being reviewed')).toBeInTheDocument()
  })

  it('shows pagination when multiple pages exist', () => {
    render(<PostList utilityType="electricity" />)

    expect(screen.getByTestId('post-pagination')).toBeInTheDocument()
    expect(screen.getByText('Page 1 of 2')).toBeInTheDocument()
    expect(screen.getByText('Previous')).toBeInTheDocument()
    expect(screen.getByText('Next')).toBeInTheDocument()
  })

  it('shows rate info for rate_report posts', () => {
    render(<PostList utilityType="electricity" />)

    expect(screen.getByText(/\$0.185\/kWh/)).toBeInTheDocument()
    expect(screen.getByText(/— Eversource/)).toBeInTheDocument()
  })

  it('shows loading skeletons when loading', () => {
    mockPostsLoading = true
    render(<PostList utilityType="electricity" />)

    expect(screen.getByTestId('post-list-loading')).toBeInTheDocument()
  })

  it('shows empty state when no posts', () => {
    // Override to return empty
    const origMock = jest.requireMock('@/lib/hooks/useCommunity')
    const origFn = origMock.useCommunityPosts
    origMock.useCommunityPosts = () => ({
      data: { posts: [], page: 1, pages: 0, total: 0 },
      isLoading: false,
      error: null,
    })

    render(<PostList utilityType="electricity" />)
    expect(screen.getByTestId('post-list-empty')).toBeInTheDocument()
    expect(screen.getByText('No posts yet. Be the first to share!')).toBeInTheDocument()

    origMock.useCommunityPosts = origFn
  })

  it('shows error state', () => {
    mockPostsError = new Error('fail')
    render(<PostList utilityType="electricity" />)

    expect(screen.getByTestId('post-list-error')).toBeInTheDocument()
  })
})

describe('PostForm', () => {
  beforeEach(() => {
    mockAuth = { ...mockAuth, user: mockUser }
    jest.clearAllMocks()
  })

  it('requires authentication — shows login prompt when not authed', () => {
    mockAuth = { ...mockAuth, user: null as unknown as typeof mockUser }
    render(<PostForm />)

    expect(screen.getByTestId('post-form-auth-required')).toBeInTheDocument()
    expect(screen.getByText('Sign in')).toBeInTheDocument()
  })

  it('shows expandable button when collapsed', () => {
    render(<PostForm />)

    expect(screen.getByTestId('post-form-expand')).toBeInTheDocument()
    expect(screen.getByText(/Share a tip/)).toBeInTheDocument()
  })

  it('expands to show full form on click', async () => {
    const user = userEvent.setup()
    render(<PostForm />)

    await user.click(screen.getByTestId('post-form-expand'))

    expect(screen.getByTestId('post-form')).toBeInTheDocument()
    expect(screen.getByTestId('post-title-input')).toBeInTheDocument()
    expect(screen.getByTestId('post-body-input')).toBeInTheDocument()
  })

  it('shows consent text in expanded form', async () => {
    const user = userEvent.setup()
    render(<PostForm />)

    await user.click(screen.getByTestId('post-form-expand'))

    expect(screen.getByTestId('consent-text')).toBeInTheDocument()
    expect(screen.getByText(/visible to other users/)).toBeInTheDocument()
  })

  it('shows rate fields only for rate_report type', async () => {
    const user = userEvent.setup()
    render(<PostForm />)

    await user.click(screen.getByTestId('post-form-expand'))

    // Default post type is 'tip', no rate fields
    expect(screen.queryByTestId('rate-fields')).not.toBeInTheDocument()

    // Switch to rate_report
    fireEvent.change(screen.getByTestId('post-type-select'), { target: { value: 'rate_report' } })

    expect(screen.getByTestId('rate-fields')).toBeInTheDocument()
    expect(screen.getByTestId('rate-input')).toBeInTheDocument()
    expect(screen.getByTestId('rate-unit-select')).toBeInTheDocument()
    expect(screen.getByTestId('supplier-input')).toBeInTheDocument()
  })

  it('validates required fields', async () => {
    const user = userEvent.setup()
    render(<PostForm />)

    await user.click(screen.getByTestId('post-form-expand'))
    await user.click(screen.getByTestId('post-submit-btn'))

    expect(screen.getByTestId('title-error')).toBeInTheDocument()
    expect(screen.getByTestId('body-error')).toBeInTheDocument()
  })

  it('calls API on valid submit', async () => {
    const user = userEvent.setup()
    render(<PostForm />)

    await user.click(screen.getByTestId('post-form-expand'))
    await user.type(screen.getByTestId('post-title-input'), 'Test title here')
    await user.type(screen.getByTestId('post-body-input'), 'This is a valid body with more than 10 characters.')
    await user.click(screen.getByTestId('post-submit-btn'))

    expect(mockCreateMutate).toHaveBeenCalledWith(
      expect.objectContaining({
        title: 'Test title here',
        body: 'This is a valid body with more than 10 characters.',
        post_type: 'tip',
      }),
      expect.anything(),
    )
  })
})

describe('VoteButton', () => {
  beforeEach(() => {
    jest.clearAllMocks()
  })

  it('renders vote count', () => {
    render(<VoteButton postId="post-1" count={5} />)

    expect(screen.getByTestId('vote-count-post-1')).toHaveTextContent('5')
  })

  it('toggles with optimistic update on click', async () => {
    const user = userEvent.setup()
    render(<VoteButton postId="post-1" count={5} />)

    await user.click(screen.getByTestId('vote-btn-post-1'))

    // Optimistic: count should increase
    expect(screen.getByTestId('vote-count-post-1')).toHaveTextContent('6')
    expect(mockVoteMutate).toHaveBeenCalledWith('post-1', expect.anything())
  })

  it('shows filled arrow when voted', async () => {
    const user = userEvent.setup()
    render(<VoteButton postId="post-1" count={5} />)

    await user.click(screen.getByTestId('vote-btn-post-1'))

    // Button should have active styling
    const btn = screen.getByTestId('vote-btn-post-1')
    expect(btn.className).toContain('bg-primary-100')
  })
})

describe('ReportButton', () => {
  beforeEach(() => {
    jest.clearAllMocks()
  })

  it('shows report button initially', () => {
    render(<ReportButton postId="post-1" />)

    expect(screen.getByTestId('report-btn-post-1')).toBeInTheDocument()
    expect(screen.getByText('Report')).toBeInTheDocument()
  })

  it('shows confirmation dialog on click', async () => {
    const user = userEvent.setup()
    render(<ReportButton postId="post-1" />)

    await user.click(screen.getByTestId('report-btn-post-1'))

    expect(screen.getByTestId('report-confirm-post-1')).toBeInTheDocument()
    expect(screen.getByText('Report this post?')).toBeInTheDocument()
  })

  it('calls report API on confirm', async () => {
    const user = userEvent.setup()
    render(<ReportButton postId="post-1" />)

    await user.click(screen.getByTestId('report-btn-post-1'))
    await user.click(screen.getByTestId('report-yes-post-1'))

    expect(mockReportMutate).toHaveBeenCalledWith(
      { postId: 'post-1' },
      expect.anything(),
    )
  })

  it('dismisses confirmation on No', async () => {
    const user = userEvent.setup()
    render(<ReportButton postId="post-1" />)

    await user.click(screen.getByTestId('report-btn-post-1'))
    expect(screen.getByText('Report this post?')).toBeInTheDocument()

    await user.click(screen.getByText('No'))
    expect(screen.queryByText('Report this post?')).not.toBeInTheDocument()
    expect(screen.getByTestId('report-btn-post-1')).toBeInTheDocument()
  })
})

describe('CommunityStats', () => {
  beforeEach(() => {
    mockStatsLoading = false
    mockStatsError = null
    jest.clearAllMocks()
  })

  it('renders stats banner with data', () => {
    render(<CommunityStats />)

    expect(screen.getByTestId('community-stats')).toBeInTheDocument()
    expect(screen.getByTestId('stats-banner')).toHaveTextContent('142 users in your area')
    expect(screen.getByTestId('stats-banner')).toHaveTextContent('saved an average of 19%')
  })

  it('renders attribution text', () => {
    render(<CommunityStats />)

    expect(screen.getByTestId('stats-attribution')).toHaveTextContent('Based on 87 reports')
  })

  it('renders top tip', () => {
    render(<CommunityStats />)

    expect(screen.getByTestId('top-tip')).toBeInTheDocument()
    expect(screen.getByText('Switch to off-peak hours')).toBeInTheDocument()
  })

  it('shows loading skeleton', () => {
    mockStatsLoading = true
    render(<CommunityStats />)

    expect(screen.getByTestId('community-stats-loading')).toBeInTheDocument()
  })

  it('hides gracefully on error', () => {
    mockStatsError = new Error('fail')
    const { container } = render(<CommunityStats />)

    expect(container.firstChild).toBeNull()
  })
})
