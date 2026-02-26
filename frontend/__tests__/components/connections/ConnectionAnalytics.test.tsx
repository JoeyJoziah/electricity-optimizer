import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { ConnectionAnalytics } from '@/components/connections/ConnectionAnalytics'
import '@testing-library/jest-dom'

// Mock cn utility
jest.mock('@/lib/utils/cn', () => ({
  cn: (...args: unknown[]) => args.filter(Boolean).join(' '),
}))

// Mock lucide-react icons (includes Loader2 needed by Button component)
jest.mock('lucide-react', () => ({
  TrendingUp: (props: React.SVGAttributes<SVGElement>) => <svg data-testid="icon-trending-up" {...props} />,
  TrendingDown: (props: React.SVGAttributes<SVGElement>) => <svg data-testid="icon-trending-down" {...props} />,
  DollarSign: (props: React.SVGAttributes<SVGElement>) => <svg data-testid="icon-dollar" {...props} />,
  AlertTriangle: (props: React.SVGAttributes<SVGElement>) => <svg data-testid="icon-alert" {...props} />,
  BarChart3: (props: React.SVGAttributes<SVGElement>) => <svg data-testid="icon-barchart" {...props} />,
  RefreshCw: (props: React.SVGAttributes<SVGElement>) => <svg data-testid="icon-refresh" {...props} />,
  Loader2: (props: React.SVGAttributes<SVGElement>) => <svg data-testid="icon-loader" {...props} />,
  CheckCircle: (props: React.SVGAttributes<SVGElement>) => <svg data-testid="icon-check" {...props} />,
  XCircle: (props: React.SVGAttributes<SVGElement>) => <svg data-testid="icon-xcircle" {...props} />,
  Clock: (props: React.SVGAttributes<SVGElement>) => <svg data-testid="icon-clock" {...props} />,
}))

const mockFetch = global.fetch as jest.Mock

// Helper to mock all 4 fetch calls (comparison, savings, history, health)
function mockAllAnalyticsFetches({
  comparison,
  savings,
  history,
  health,
}: {
  comparison?: object
  savings?: object
  history?: object
  health?: object
} = {}) {
  const defaultComparison = {
    user_rate: 0.25,
    market_average: 0.22,
    delta: 0.03,
    percentage_difference: 13.6,
    is_above_average: true,
  }

  const defaultSavings = {
    estimated_annual_savings_vs_best: 324,
    estimated_monthly_savings_vs_best: 27,
    current_annual_cost: 2700,
  }

  const defaultHistory = {
    data_points: [
      { date: '2026-02-01', rate: 0.25, supplier: 'Eversource' },
      { date: '2026-01-01', rate: 0.23, supplier: 'Eversource' },
    ],
  }

  const defaultHealth = {
    stale_connections: [],
    rate_change_alerts: [],
  }

  mockFetch.mockImplementation((url: string) => {
    if (url.includes('comparison')) {
      return Promise.resolve({
        ok: true,
        json: () => Promise.resolve(comparison || defaultComparison),
      })
    }
    if (url.includes('savings')) {
      return Promise.resolve({
        ok: true,
        json: () => Promise.resolve(savings || defaultSavings),
      })
    }
    if (url.includes('history')) {
      return Promise.resolve({
        ok: true,
        json: () => Promise.resolve(history || defaultHistory),
      })
    }
    if (url.includes('health')) {
      return Promise.resolve({
        ok: true,
        json: () => Promise.resolve(health || defaultHealth),
      })
    }
    return Promise.resolve({ ok: true, json: () => Promise.resolve({}) })
  })
}

describe('ConnectionAnalytics', () => {
  beforeEach(() => {
    jest.clearAllMocks()
    mockFetch.mockReset()
  })

  it('renders the analytics container and heading', async () => {
    mockAllAnalyticsFetches()
    render(<ConnectionAnalytics />)

    expect(screen.getByTestId('connection-analytics')).toBeInTheDocument()
    expect(screen.getByText('Connection Analytics')).toBeInTheDocument()
    expect(
      screen.getByText(/insights into your electricity rates/i)
    ).toBeInTheDocument()
  })

  it('renders the refresh button', async () => {
    mockAllAnalyticsFetches()
    render(<ConnectionAnalytics />)

    expect(screen.getByTestId('refresh-analytics')).toBeInTheDocument()
    expect(screen.getByText('Refresh')).toBeInTheDocument()
  })

  it('shows loading states initially', () => {
    mockFetch.mockImplementation(() => new Promise(() => {}))
    render(<ConnectionAnalytics />)

    expect(screen.getByTestId('rate-comparison-loading')).toBeInTheDocument()
    expect(screen.getByTestId('savings-estimate-loading')).toBeInTheDocument()
    expect(screen.getByTestId('rate-history-loading')).toBeInTheDocument()
    expect(screen.getByTestId('connection-health-loading')).toBeInTheDocument()
  })

  it('displays rate comparison data after loading', async () => {
    mockAllAnalyticsFetches()
    render(<ConnectionAnalytics />)

    await waitFor(() => {
      expect(screen.getByText('Your Rate')).toBeInTheDocument()
    })

    expect(screen.getByText('Market Average')).toBeInTheDocument()
    expect(screen.getByText('25.00')).toBeInTheDocument()
    expect(screen.getByText('22.00')).toBeInTheDocument()
    expect(screen.getByText('Above market average')).toBeInTheDocument()
  })

  it('displays below average when user rate is lower', async () => {
    mockAllAnalyticsFetches({
      comparison: {
        user_rate: 0.19,
        market_average: 0.22,
        delta: -0.03,
        percentage_difference: -13.6,
        is_above_average: false,
      },
    })
    render(<ConnectionAnalytics />)

    await waitFor(() => {
      expect(screen.getByText('Below market average')).toBeInTheDocument()
    })
  })

  it('displays savings estimate card after loading', async () => {
    mockAllAnalyticsFetches()
    render(<ConnectionAnalytics />)

    await waitFor(() => {
      expect(screen.getByTestId('annual-savings-amount')).toBeInTheDocument()
    })

    expect(screen.getByText('Savings Estimate')).toBeInTheDocument()
  })

  it('displays rate history table after loading', async () => {
    mockAllAnalyticsFetches()
    render(<ConnectionAnalytics />)

    await waitFor(() => {
      expect(screen.getByTestId('rate-history-table')).toBeInTheDocument()
    })

    expect(screen.getByText('Rate History')).toBeInTheDocument()
  })

  it('shows empty state when rate history has no data points', async () => {
    mockAllAnalyticsFetches({
      history: { data_points: [] },
    })
    render(<ConnectionAnalytics />)

    await waitFor(() => {
      expect(
        screen.getByText('No rate history available yet.')
      ).toBeInTheDocument()
    })
  })

  it('displays connection health as healthy when no issues', async () => {
    mockAllAnalyticsFetches()
    render(<ConnectionAnalytics />)

    await waitFor(() => {
      expect(
        screen.getByText('All connections are healthy and up to date.')
      ).toBeInTheDocument()
    })
  })

  it('displays stale connection warnings', async () => {
    mockAllAnalyticsFetches({
      health: {
        stale_connections: [
          {
            id: 'conn-1',
            supplier_name: 'UI Company',
            last_sync_at: '2026-02-10T00:00:00Z',
            days_since_sync: 15,
          },
        ],
        rate_change_alerts: [],
      },
    })
    render(<ConnectionAnalytics />)

    await waitFor(() => {
      expect(screen.getByTestId('stale-connection-conn-1')).toBeInTheDocument()
    })

    expect(screen.getByText('UI Company')).toBeInTheDocument()
    expect(screen.getByText('Last synced 15 days ago')).toBeInTheDocument()
  })

  it('displays rate change alerts with rate change badge', async () => {
    // Use different percentage than the comparison card to avoid duplicate text
    mockAllAnalyticsFetches({
      comparison: {
        user_rate: 0.25,
        market_average: 0.22,
        delta: 0.03,
        percentage_difference: 13.6,
        is_above_average: true,
      },
      health: {
        stale_connections: [],
        rate_change_alerts: [
          {
            id: 'alert-1',
            supplier_name: 'United Illuminating',
            old_rate: 0.22,
            new_rate: 0.28,
            change_percentage: 27.3,
            detected_at: '2026-02-20T00:00:00Z',
          },
        ],
      },
    })
    render(<ConnectionAnalytics />)

    await waitFor(() => {
      expect(screen.getByTestId('rate-alert-alert-1')).toBeInTheDocument()
    })

    expect(
      screen.getByText(/united illuminating rate increased/i)
    ).toBeInTheDocument()
    expect(screen.getByText('+27.3%')).toBeInTheDocument()
  })

  it('shows issue count badge when health has issues', async () => {
    mockAllAnalyticsFetches({
      health: {
        stale_connections: [
          { id: 'c1', supplier_name: 'S1', last_sync_at: null, days_since_sync: 30 },
        ],
        rate_change_alerts: [
          {
            id: 'a1',
            supplier_name: 'S2',
            old_rate: 0.2,
            new_rate: 0.25,
            change_percentage: 25,
            detected_at: '2026-02-20T00:00:00Z',
          },
        ],
      },
    })
    render(<ConnectionAnalytics />)

    await waitFor(() => {
      expect(screen.getByText('2 issues')).toBeInTheDocument()
    })
  })

  it('handles API errors gracefully', async () => {
    mockFetch.mockImplementation(() =>
      Promise.resolve({ ok: false, status: 500 })
    )
    render(<ConnectionAnalytics />)

    await waitFor(() => {
      const tryAgainButtons = screen.getAllByText('Try again')
      expect(tryAgainButtons.length).toBeGreaterThanOrEqual(1)
    })
  })

  it('monthly kWh input is rendered with default value', async () => {
    mockAllAnalyticsFetches()
    render(<ConnectionAnalytics />)

    await waitFor(() => {
      expect(screen.getByTestId('annual-savings-amount')).toBeInTheDocument()
    })

    const input = screen.getByLabelText(
      /monthly electricity usage in kilowatt hours/i
    )
    expect(input).toBeInTheDocument()
    expect(input).toHaveValue(900)
  })

  it('renders all four analytics cards', () => {
    mockAllAnalyticsFetches()
    render(<ConnectionAnalytics />)

    expect(screen.getByTestId('rate-comparison-card')).toBeInTheDocument()
    expect(screen.getByTestId('savings-estimate-card')).toBeInTheDocument()
    expect(screen.getByTestId('rate-history-card')).toBeInTheDocument()
    expect(screen.getByTestId('connection-health-card')).toBeInTheDocument()
  })

  it('renders card headings', () => {
    mockAllAnalyticsFetches()
    render(<ConnectionAnalytics />)

    expect(screen.getByText('Rate Comparison')).toBeInTheDocument()
    expect(screen.getByText('Savings Estimate')).toBeInTheDocument()
    expect(screen.getByText('Rate History')).toBeInTheDocument()
    expect(screen.getByText('Connection Health')).toBeInTheDocument()
  })
})
