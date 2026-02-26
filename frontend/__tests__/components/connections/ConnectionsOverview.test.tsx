import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { ConnectionsOverview } from '@/components/connections/ConnectionsOverview'
import '@testing-library/jest-dom'

// Mock cn utility
jest.mock('@/lib/utils/cn', () => ({
  cn: (...args: unknown[]) => args.filter(Boolean).join(' '),
}))

// Mock lucide-react icons
jest.mock('lucide-react', () => ({
  Link2: (props: React.SVGAttributes<SVGElement>) => <svg data-testid="icon-link" {...props} />,
  ArrowLeft: (props: React.SVGAttributes<SVGElement>) => <svg data-testid="icon-back" {...props} />,
  Loader2: (props: React.SVGAttributes<SVGElement>) => <svg data-testid="icon-loader" {...props} />,
  KeyRound: (props: React.SVGAttributes<SVGElement>) => <svg data-testid="icon-key" {...props} />,
  Mail: (props: React.SVGAttributes<SVGElement>) => <svg data-testid="icon-mail" {...props} />,
  Upload: (props: React.SVGAttributes<SVGElement>) => <svg data-testid="icon-upload" {...props} />,
  ArrowRight: (props: React.SVGAttributes<SVGElement>) => <svg data-testid="icon-arrow" {...props} />,
  Trash2: (props: React.SVGAttributes<SVGElement>) => <svg data-testid="icon-trash" {...props} />,
  RefreshCw: (props: React.SVGAttributes<SVGElement>) => <svg data-testid="icon-refresh" {...props} />,
  AlertTriangle: (props: React.SVGAttributes<SVGElement>) => <svg data-testid="icon-alert" {...props} />,
  Zap: (props: React.SVGAttributes<SVGElement>) => <svg data-testid="icon-zap" {...props} />,
  ChevronRight: (props: React.SVGAttributes<SVGElement>) => <svg data-testid="icon-chevron" {...props} />,
  Pencil: (props: React.SVGAttributes<SVGElement>) => <svg data-testid="icon-pencil" {...props} />,
  Check: (props: React.SVGAttributes<SVGElement>) => <svg data-testid="icon-check" {...props} />,
  X: (props: React.SVGAttributes<SVGElement>) => <svg data-testid="icon-x" {...props} />,
  // ConnectionAnalytics icons
  TrendingUp: (props: React.SVGAttributes<SVGElement>) => <svg data-testid="icon-trending-up" {...props} />,
  TrendingDown: (props: React.SVGAttributes<SVGElement>) => <svg data-testid="icon-trending-down" {...props} />,
  DollarSign: (props: React.SVGAttributes<SVGElement>) => <svg data-testid="icon-dollar" {...props} />,
  BarChart3: (props: React.SVGAttributes<SVGElement>) => <svg data-testid="icon-barchart" {...props} />,
  CheckCircle: (props: React.SVGAttributes<SVGElement>) => <svg data-testid="icon-checkcircle" {...props} />,
  XCircle: (props: React.SVGAttributes<SVGElement>) => <svg data-testid="icon-xcircle" {...props} />,
  Clock: (props: React.SVGAttributes<SVGElement>) => <svg data-testid="icon-clock" {...props} />,
  // DirectLoginForm icons
  ExternalLink: (props: React.SVGAttributes<SVGElement>) => <svg data-testid="icon-ext" {...props} />,
  CheckCircle2: (props: React.SVGAttributes<SVGElement>) => <svg data-testid="icon-check2" {...props} />,
  // EmailConnectionFlow icons
  Search: (props: React.SVGAttributes<SVGElement>) => <svg data-testid="icon-search" {...props} />,
  FileText: (props: React.SVGAttributes<SVGElement>) => <svg data-testid="icon-filetext" {...props} />,
  // BillUploadForm icons
  AlertCircle: (props: React.SVGAttributes<SVGElement>) => <svg data-testid="icon-alertcircle" {...props} />,
  RotateCcw: (props: React.SVGAttributes<SVGElement>) => <svg data-testid="icon-rotate" {...props} />,
  Image: (props: React.SVGAttributes<SVGElement>) => <svg data-testid="icon-image" {...props} />,
  File: (props: React.SVGAttributes<SVGElement>) => <svg data-testid="icon-file" {...props} />,
  Calendar: (props: React.SVGAttributes<SVGElement>) => <svg data-testid="icon-calendar" {...props} />,
  Gauge: (props: React.SVGAttributes<SVGElement>) => <svg data-testid="icon-gauge" {...props} />,
}))

const mockFetch = global.fetch as jest.Mock

const mockConnections = [
  {
    id: 'conn-1',
    method: 'direct_login',
    status: 'active',
    supplier_name: 'Eversource Energy',
    email_provider: null,
    last_sync_at: '2026-02-20T10:00:00Z',
    last_sync_error: null,
    current_rate: 0.25,
    created_at: '2026-02-15T10:00:00Z',
  },
  {
    id: 'conn-2',
    method: 'email_scan',
    status: 'active',
    supplier_name: null,
    email_provider: 'Gmail',
    last_sync_at: '2026-02-19T08:00:00Z',
    last_sync_error: null,
    current_rate: null,
    created_at: '2026-02-14T10:00:00Z',
  },
]

describe('ConnectionsOverview', () => {
  beforeEach(() => {
    jest.clearAllMocks()
    mockFetch.mockReset()
  })

  it('shows loading state initially', () => {
    mockFetch.mockImplementation(() => new Promise(() => {}))
    render(<ConnectionsOverview />)

    expect(screen.getByText('Loading connections...')).toBeInTheDocument()
  })

  it('shows error state on fetch failure', async () => {
    mockFetch.mockResolvedValueOnce({ ok: false, status: 500 })
    render(<ConnectionsOverview />)

    await waitFor(() => {
      expect(
        screen.getByText('Failed to load connections')
      ).toBeInTheDocument()
    })

    expect(screen.getByText('Try again')).toBeInTheDocument()
  })

  it('shows paid feature gate on 403 error', async () => {
    mockFetch.mockResolvedValueOnce({ ok: false, status: 403 })
    render(<ConnectionsOverview />)

    await waitFor(() => {
      expect(screen.getByText('Upgrade to Connect')).toBeInTheDocument()
    })

    expect(
      screen.getByText(
        /utility connections are available on pro and business plans/i
      )
    ).toBeInTheDocument()
    expect(screen.getByText('View Plans')).toBeInTheDocument()
  })

  it('renders connection list when connections exist', async () => {
    mockFetch.mockResolvedValueOnce({
      ok: true,
      json: () => Promise.resolve({ connections: mockConnections }),
    })

    render(<ConnectionsOverview />)

    await waitFor(() => {
      expect(screen.getByText('Eversource Energy')).toBeInTheDocument()
    })

    expect(screen.getByText('Gmail')).toBeInTheDocument()
    expect(screen.getByText('Active Connections')).toBeInTheDocument()
  })

  it('renders empty state with "Get Started" heading when no connections', async () => {
    mockFetch.mockResolvedValueOnce({
      ok: true,
      json: () => Promise.resolve({ connections: [] }),
    })

    render(<ConnectionsOverview />)

    await waitFor(() => {
      expect(screen.getByText('Get Started')).toBeInTheDocument()
    })

    // Should show method picker
    expect(screen.getByText('Utility Account')).toBeInTheDocument()
    expect(screen.getByText('Email Inbox')).toBeInTheDocument()
    expect(screen.getByText('Upload Bills')).toBeInTheDocument()
  })

  it('shows "Add Another Connection" heading when connections exist', async () => {
    mockFetch.mockResolvedValueOnce({
      ok: true,
      json: () => Promise.resolve({ connections: mockConnections }),
    })

    render(<ConnectionsOverview />)

    await waitFor(() => {
      expect(screen.getByText('Add Another Connection')).toBeInTheDocument()
    })
  })

  it('renders tab navigation with Connections and Analytics tabs', async () => {
    mockFetch.mockResolvedValueOnce({
      ok: true,
      json: () => Promise.resolve({ connections: [] }),
    })

    render(<ConnectionsOverview />)

    const tablist = screen.getByRole('tablist', { name: /connection views/i })
    expect(tablist).toBeInTheDocument()

    expect(
      screen.getByRole('tab', { name: /connections/i })
    ).toBeInTheDocument()
    expect(
      screen.getByRole('tab', { name: /analytics/i })
    ).toBeInTheDocument()
  })

  it('connections tab is selected by default', async () => {
    mockFetch.mockResolvedValueOnce({
      ok: true,
      json: () => Promise.resolve({ connections: [] }),
    })

    render(<ConnectionsOverview />)

    const connectionsTab = screen.getByRole('tab', { name: /connections/i })
    expect(connectionsTab).toHaveAttribute('aria-selected', 'true')

    const analyticsTab = screen.getByRole('tab', { name: /analytics/i })
    expect(analyticsTab).toHaveAttribute('aria-selected', 'false')
  })

  it('switches to analytics tab when clicked', async () => {
    const user = userEvent.setup()

    // Mock connections fetch + all analytics fetches
    mockFetch.mockImplementation((url: string) => {
      if (url.includes('/api/v1/connections') && !url.includes('/analytics')) {
        return Promise.resolve({
          ok: true,
          json: () => Promise.resolve({ connections: [] }),
        })
      }
      // Analytics sub-endpoints
      return Promise.resolve({
        ok: true,
        json: () => Promise.resolve({
          user_rate: 0.25,
          market_average: 0.22,
          delta: 0.03,
          percentage_difference: 13.6,
          is_above_average: true,
          estimated_annual_savings_vs_best: 300,
          estimated_monthly_savings_vs_best: 25,
          current_annual_cost: 2700,
          data_points: [],
          stale_connections: [],
          rate_change_alerts: [],
        }),
      })
    })

    render(<ConnectionsOverview />)

    await waitFor(() => {
      expect(screen.getByText('Get Started')).toBeInTheDocument()
    })

    const analyticsTab = screen.getByRole('tab', { name: /analytics/i })
    await user.click(analyticsTab)

    expect(analyticsTab).toHaveAttribute('aria-selected', 'true')
    expect(screen.getByText('Connection Analytics')).toBeInTheDocument()
  })

  it('retries fetching connections when Try again is clicked', async () => {
    const user = userEvent.setup()

    // First call fails, second succeeds
    mockFetch
      .mockResolvedValueOnce({ ok: false, status: 500 })
      .mockResolvedValueOnce({
        ok: true,
        json: () => Promise.resolve({ connections: mockConnections }),
      })

    render(<ConnectionsOverview />)

    await waitFor(() => {
      expect(
        screen.getByText('Failed to load connections')
      ).toBeInTheDocument()
    })

    await user.click(screen.getByText('Try again'))

    await waitFor(() => {
      expect(screen.getByText('Eversource Energy')).toBeInTheDocument()
    })
  })

  it('renders connections tab panel with correct aria attributes', async () => {
    mockFetch.mockResolvedValueOnce({
      ok: true,
      json: () => Promise.resolve({ connections: [] }),
    })

    render(<ConnectionsOverview />)

    await waitFor(() => {
      const tabpanel = screen.getByRole('tabpanel')
      expect(tabpanel).toHaveAttribute('id', 'panel-connections')
      expect(tabpanel).toHaveAttribute(
        'aria-labelledby',
        'tab-connections'
      )
    })
  })
})
