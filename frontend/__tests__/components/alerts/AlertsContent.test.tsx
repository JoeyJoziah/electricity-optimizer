import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import '@testing-library/jest-dom'
import React from 'react'

// Mock the Header component to avoid sidebar context dependency
jest.mock('@/components/layout/Header', () => ({
  Header: ({ title }: { title: string }) => (
    <header data-testid="page-header">
      <h1>{title}</h1>
    </header>
  ),
}))

// Mock API modules
const mockGetAlerts = jest.fn()
const mockCreateAlert = jest.fn()
const mockUpdateAlert = jest.fn()
const mockDeleteAlert = jest.fn()
const mockGetAlertHistory = jest.fn()

jest.mock('@/lib/api/alerts', () => ({
  getAlerts: (...args: unknown[]) => mockGetAlerts(...args),
  createAlert: (...args: unknown[]) => mockCreateAlert(...args),
  updateAlert: (...args: unknown[]) => mockUpdateAlert(...args),
  deleteAlert: (...args: unknown[]) => mockDeleteAlert(...args),
  getAlertHistory: (...args: unknown[]) => mockGetAlertHistory(...args),
}))

// Import after mocks are set up
import AlertsContent from '@/components/alerts/AlertsContent'
import { ApiClientError } from '@/lib/api/client'

// Default mock data
const defaultAlertsResponse = {
  alerts: [
    {
      id: 'alert-1',
      user_id: 'user-1',
      region: 'us_ct',
      currency: 'USD',
      price_below: 0.2,
      price_above: null,
      notify_optimal_windows: true,
      is_active: true,
      created_at: '2026-03-01T10:00:00Z',
      updated_at: '2026-03-01T10:00:00Z',
    },
    {
      id: 'alert-2',
      user_id: 'user-1',
      region: 'us_ny',
      currency: 'USD',
      price_below: null,
      price_above: 0.35,
      notify_optimal_windows: false,
      is_active: false,
      created_at: '2026-03-02T10:00:00Z',
      updated_at: '2026-03-02T10:00:00Z',
    },
  ],
  total: 2,
}

const singleAlertResponse = {
  alerts: [
    {
      id: 'alert-1',
      user_id: 'user-1',
      region: 'us_ct',
      currency: 'USD',
      price_below: 0.2,
      price_above: null,
      notify_optimal_windows: true,
      is_active: true,
      created_at: '2026-03-01T10:00:00Z',
      updated_at: '2026-03-01T10:00:00Z',
    },
  ],
  total: 1,
}

const defaultHistoryResponse = {
  items: [
    {
      id: 'hist-1',
      user_id: 'user-1',
      alert_config_id: 'alert-1',
      alert_type: 'price_drop',
      current_price: 0.18,
      threshold: 0.2,
      region: 'us_ct',
      supplier: 'Eversource',
      currency: 'USD',
      optimal_window_start: null,
      optimal_window_end: null,
      estimated_savings: null,
      triggered_at: '2026-03-03T14:00:00Z',
      email_sent: true,
    },
    {
      id: 'hist-2',
      user_id: 'user-1',
      alert_config_id: 'alert-2',
      alert_type: 'price_spike',
      current_price: 0.38,
      threshold: 0.35,
      region: 'us_ny',
      supplier: 'ConEdison',
      currency: 'USD',
      optimal_window_start: null,
      optimal_window_end: null,
      estimated_savings: null,
      triggered_at: '2026-03-04T09:00:00Z',
      email_sent: true,
    },
  ],
  total: 2,
  page: 1,
  page_size: 20,
  pages: 1,
}

describe('AlertsContent', () => {
  let queryClient: QueryClient

  beforeEach(() => {
    queryClient = new QueryClient({
      defaultOptions: {
        queries: { retry: false, gcTime: 0 },
        mutations: { retry: false },
      },
    })

    mockGetAlerts.mockResolvedValue(defaultAlertsResponse)
    mockGetAlertHistory.mockResolvedValue(defaultHistoryResponse)
    mockCreateAlert.mockResolvedValue({
      id: 'alert-new',
      user_id: 'user-1',
      region: 'us_tx',
      currency: 'USD',
      price_below: 0.15,
      price_above: null,
      notify_optimal_windows: true,
      is_active: true,
      created_at: '2026-03-06T10:00:00Z',
      updated_at: '2026-03-06T10:00:00Z',
    })
    mockDeleteAlert.mockResolvedValue({ deleted: true, alert_id: 'alert-1' })
    mockUpdateAlert.mockResolvedValue({
      ...defaultAlertsResponse.alerts[0],
      is_active: false,
    })
  })

  afterEach(() => {
    queryClient.clear()
    jest.clearAllMocks()
  })

  const wrapper = ({ children }: { children: React.ReactNode }) => (
    <QueryClientProvider client={queryClient}>{children}</QueryClientProvider>
  )

  // --- Header ---

  it('renders page header with title', () => {
    render(<AlertsContent />, { wrapper })

    expect(screen.getByText('Alerts')).toBeInTheDocument()
  })

  // --- Tabs ---

  it('renders both tabs', () => {
    render(<AlertsContent />, { wrapper })

    expect(screen.getByText('My Alerts')).toBeInTheDocument()
    expect(screen.getByText('History')).toBeInTheDocument()
  })

  it('defaults to My Alerts tab', () => {
    render(<AlertsContent />, { wrapper })

    // The "My Alerts" tab button should be styled as active
    const myAlertsTab = screen.getByText('My Alerts')
    expect(myAlertsTab.className).toContain('border-primary-600')
  })

  // --- My Alerts: Loading ---

  it('renders loading skeletons while alerts are fetching', () => {
    mockGetAlerts.mockReturnValue(new Promise(() => {}))

    render(<AlertsContent />, { wrapper })

    const skeletons = document.querySelectorAll('.animate-pulse')
    expect(skeletons.length).toBeGreaterThan(0)
  })

  // --- My Alerts: Empty State ---

  it('shows empty state when no alerts exist', async () => {
    mockGetAlerts.mockResolvedValue({ alerts: [], total: 0 })

    render(<AlertsContent />, { wrapper })

    await waitFor(() => {
      expect(screen.getByTestId('empty-alerts')).toBeInTheDocument()
    })

    expect(screen.getByText('No alerts configured yet')).toBeInTheDocument()
    expect(
      screen.getByText('Create your first alert to get notified about price changes.')
    ).toBeInTheDocument()
  })

  // --- My Alerts: Alert List ---

  it('renders alert cards when alerts exist', async () => {
    render(<AlertsContent />, { wrapper })

    await waitFor(() => {
      const cards = screen.getAllByTestId('alert-card')
      expect(cards).toHaveLength(2)
    })
  })

  it('shows region name on alert cards', async () => {
    render(<AlertsContent />, { wrapper })

    await waitFor(() => {
      expect(screen.getByText('Connecticut')).toBeInTheDocument()
      expect(screen.getByText('New York')).toBeInTheDocument()
    })
  })

  it('shows Active badge for active alerts', async () => {
    render(<AlertsContent />, { wrapper })

    await waitFor(() => {
      expect(screen.getByText('Active')).toBeInTheDocument()
    })
  })

  it('shows Paused badge for inactive alerts', async () => {
    render(<AlertsContent />, { wrapper })

    await waitFor(() => {
      expect(screen.getByText('Paused')).toBeInTheDocument()
    })
  })

  it('shows threshold values on alert cards', async () => {
    render(<AlertsContent />, { wrapper })

    await waitFor(() => {
      expect(screen.getByText(/Below: \$0\.2000\/kWh/)).toBeInTheDocument()
      expect(screen.getByText(/Above: \$0\.3500\/kWh/)).toBeInTheDocument()
    })
  })

  // --- My Alerts: Delete ---

  it('calls delete when delete button is clicked', async () => {
    const user = userEvent.setup()
    render(<AlertsContent />, { wrapper })

    await waitFor(() => {
      expect(screen.getAllByTestId('delete-alert').length).toBe(2)
    })

    await user.click(screen.getAllByTestId('delete-alert')[0])

    await waitFor(() => {
      expect(mockDeleteAlert).toHaveBeenCalledWith('alert-1')
    })
  })

  // --- My Alerts: Add Alert Form ---

  it('shows form when Add Alert button is clicked', async () => {
    const user = userEvent.setup()
    render(<AlertsContent />, { wrapper })

    await waitFor(() => {
      expect(screen.getByText('Add Alert')).toBeInTheDocument()
    })

    await user.click(screen.getByText('Add Alert'))

    expect(screen.getByTestId('alert-form')).toBeInTheDocument()
    expect(screen.getByText('Create New Alert')).toBeInTheDocument()
  })

  // --- My Alerts: Error State ---

  it('shows error state when alerts fetch fails', async () => {
    mockGetAlerts.mockRejectedValue(new Error('API error'))

    render(<AlertsContent />, { wrapper })

    await waitFor(() => {
      expect(
        screen.getByText('Failed to load alerts. Please try again.')
      ).toBeInTheDocument()
    })
  })

  // --- My Alerts: Free Tier Note ---

  it('shows free-tier note when user has alerts', async () => {
    render(<AlertsContent />, { wrapper })

    await waitFor(() => {
      expect(screen.getByTestId('free-tier-note')).toBeInTheDocument()
    })

    expect(screen.getByText(/Free plan: 1 alert\./)).toBeInTheDocument()
    const upgradeLink = screen.getByText('Upgrade for unlimited')
    expect(upgradeLink).toBeInTheDocument()
    expect(upgradeLink.closest('a')).toHaveAttribute('href', '/pricing')
  })

  it('does not show free-tier note when no alerts exist', async () => {
    mockGetAlerts.mockResolvedValue({ alerts: [], total: 0 })

    render(<AlertsContent />, { wrapper })

    await waitFor(() => {
      expect(screen.getByTestId('empty-alerts')).toBeInTheDocument()
    })

    expect(screen.queryByTestId('free-tier-note')).not.toBeInTheDocument()
  })

  // --- My Alerts: 403 Tier Limit in Form ---

  it('shows tier limit upgrade banner when create returns 403', async () => {
    mockGetAlerts.mockResolvedValue(singleAlertResponse)
    mockCreateAlert.mockRejectedValue(
      new ApiClientError({
        message: 'Free plan limited to 1 alert. Upgrade to Pro for unlimited.',
        status: 403,
      })
    )

    const user = userEvent.setup()
    render(<AlertsContent />, { wrapper })

    // Wait for alerts to load
    await waitFor(() => {
      expect(screen.getAllByTestId('alert-card')).toHaveLength(1)
    })

    // Open form
    await user.click(screen.getByText('Add Alert'))
    expect(screen.getByTestId('alert-form')).toBeInTheDocument()

    // Fill form minimally
    await user.selectOptions(screen.getByTestId('region-select'), 'us_tx')

    // Submit
    await user.click(screen.getByTestId('submit-alert'))

    // Should show the amber tier-limit banner
    await waitFor(() => {
      expect(screen.getByTestId('tier-limit-error')).toBeInTheDocument()
    })

    expect(screen.getByText(/Free plan is limited to 1 alert\./)).toBeInTheDocument()
    const upgradeLink = screen.getByText('Upgrade to Pro')
    expect(upgradeLink.closest('a')).toHaveAttribute('href', '/pricing')
  })

  it('shows generic error for non-403 create failures', async () => {
    mockGetAlerts.mockResolvedValue(singleAlertResponse)
    mockCreateAlert.mockRejectedValue(
      new ApiClientError({
        message: 'Internal server error',
        status: 500,
      })
    )

    const user = userEvent.setup()
    render(<AlertsContent />, { wrapper })

    await waitFor(() => {
      expect(screen.getAllByTestId('alert-card')).toHaveLength(1)
    })

    await user.click(screen.getByText('Add Alert'))
    await user.selectOptions(screen.getByTestId('region-select'), 'us_tx')
    await user.click(screen.getByTestId('submit-alert'))

    await waitFor(() => {
      expect(screen.getByText('Internal server error')).toBeInTheDocument()
    })

    // Should NOT show the tier-limit banner
    expect(screen.queryByTestId('tier-limit-error')).not.toBeInTheDocument()
  })

  // --- History Tab ---

  it('switches to History tab and shows history items', async () => {
    const user = userEvent.setup()
    render(<AlertsContent />, { wrapper })

    await user.click(screen.getByText('History'))

    await waitFor(() => {
      const rows = screen.getAllByTestId('history-row')
      expect(rows).toHaveLength(2)
    })
  })

  it('shows alert type badges in history', async () => {
    const user = userEvent.setup()
    render(<AlertsContent />, { wrapper })

    await user.click(screen.getByText('History'))

    await waitFor(() => {
      expect(screen.getByText('Price Drop')).toBeInTheDocument()
      expect(screen.getByText('Price Spike')).toBeInTheDocument()
    })
  })

  it('shows empty history state when no history exists', async () => {
    mockGetAlertHistory.mockResolvedValue({
      items: [],
      total: 0,
      page: 1,
      page_size: 20,
      pages: 1,
    })

    const user = userEvent.setup()
    render(<AlertsContent />, { wrapper })

    await user.click(screen.getByText('History'))

    await waitFor(() => {
      expect(screen.getByTestId('empty-history')).toBeInTheDocument()
    })

    expect(screen.getByText('No alert history')).toBeInTheDocument()
  })
})
