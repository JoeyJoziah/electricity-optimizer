import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import DashboardPage from '@/app/dashboard/page'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import '@testing-library/jest-dom'

// Mock API modules
jest.mock('@/lib/api/prices', () => ({
  getCurrentPrices: jest.fn(() =>
    Promise.resolve({
      prices: [
        { region: 'UK', price: 0.25, timestamp: '2026-02-06T12:00:00Z' },
      ],
    })
  ),
  getPriceForecast: jest.fn(() =>
    Promise.resolve({
      forecast: [
        { hour: 1, price: 0.23, confidence: [0.21, 0.25] },
        { hour: 2, price: 0.20, confidence: [0.18, 0.22] },
        { hour: 3, price: 0.18, confidence: [0.16, 0.20] },
      ],
    })
  ),
  getPriceHistory: jest.fn(() =>
    Promise.resolve({
      prices: [
        { time: '2026-02-06T10:00:00Z', price: 0.28 },
        { time: '2026-02-06T11:00:00Z', price: 0.26 },
        { time: '2026-02-06T12:00:00Z', price: 0.25 },
      ],
    })
  ),
}))

jest.mock('@/lib/api/suppliers', () => ({
  getSuppliers: jest.fn(() =>
    Promise.resolve({
      suppliers: [
        {
          id: '1',
          name: 'Octopus Energy',
          avgPricePerKwh: 0.25,
          estimatedAnnualCost: 1200,
          greenEnergy: true,
          rating: 4.5,
        },
        {
          id: '2',
          name: 'Bulb Energy',
          avgPricePerKwh: 0.22,
          estimatedAnnualCost: 1050,
          greenEnergy: true,
          rating: 4.3,
        },
      ],
    })
  ),
}))

jest.mock('@/lib/api/optimization', () => ({
  getOptimalSchedule: jest.fn(() =>
    Promise.resolve({
      schedules: [
        {
          applianceId: '1',
          applianceName: 'Washing Machine',
          scheduledStart: '2026-02-06T02:00:00Z',
          scheduledEnd: '2026-02-06T04:00:00Z',
          savings: 0.15,
        },
      ],
      totalSavings: 0.15,
    })
  ),
}))

describe('Dashboard Integration', () => {
  let queryClient: QueryClient

  beforeEach(() => {
    queryClient = new QueryClient({
      defaultOptions: {
        queries: {
          retry: false,
          gcTime: 0,
        },
      },
    })
  })

  afterEach(() => {
    queryClient.clear()
    jest.clearAllMocks()
  })

  const wrapper = ({ children }: { children: React.ReactNode }) => (
    <QueryClientProvider client={queryClient}>{children}</QueryClientProvider>
  )

  it('renders dashboard with all main widgets', async () => {
    render(<DashboardPage />, { wrapper })

    await waitFor(() => {
      // Price monitor widget
      expect(screen.getByText(/current price/i)).toBeInTheDocument()

      // Savings tracker
      expect(screen.getByText(/total saved/i)).toBeInTheDocument()

      // Price chart
      expect(screen.getByRole('img', { name: /price chart/i })).toBeInTheDocument()

      // Supplier section
      expect(screen.getByText(/suppliers/i)).toBeInTheDocument()
    })
  })

  it('displays current price and price trend', async () => {
    render(<DashboardPage />, { wrapper })

    await waitFor(() => {
      expect(screen.getByText(/0\.25/)).toBeInTheDocument()
      expect(screen.getByTestId('price-trend')).toBeInTheDocument()
    })
  })

  it('shows 24-hour forecast section', async () => {
    render(<DashboardPage />, { wrapper })

    await waitFor(() => {
      expect(screen.getByText(/24-hour forecast/i)).toBeInTheDocument()
    })
  })

  it('displays optimal scheduling recommendations', async () => {
    render(<DashboardPage />, { wrapper })

    await waitFor(() => {
      expect(screen.getByText(/optimal times/i)).toBeInTheDocument()
    })
  })

  it('handles API errors gracefully', async () => {
    const { getCurrentPrices } = require('@/lib/api/prices')
    getCurrentPrices.mockRejectedValueOnce(new Error('API Error'))

    render(<DashboardPage />, { wrapper })

    await waitFor(() => {
      expect(screen.getByText(/failed to load/i)).toBeInTheDocument()
    })
  })

  it('shows loading states while fetching data', () => {
    render(<DashboardPage />, { wrapper })

    // Should show loading indicators before data loads
    expect(screen.getByTestId('dashboard-loading')).toBeInTheDocument()
  })

  it('allows navigation to detailed views', async () => {
    const user = userEvent.setup()
    render(<DashboardPage />, { wrapper })

    await waitFor(() => {
      expect(screen.getByText(/current price/i)).toBeInTheDocument()
    })

    // Click on price chart to see details
    const viewDetailsLink = screen.getByRole('link', { name: /view all prices/i })
    expect(viewDetailsLink).toHaveAttribute('href', '/prices')
  })

  it('displays supplier comparison widget', async () => {
    render(<DashboardPage />, { wrapper })

    await waitFor(() => {
      expect(screen.getByText('Octopus Energy')).toBeInTheDocument()
      expect(screen.getByText('Bulb Energy')).toBeInTheDocument()
    })
  })

  it('shows schedule timeline for today', async () => {
    render(<DashboardPage />, { wrapper })

    await waitFor(() => {
      expect(screen.getByText('Washing Machine')).toBeInTheDocument()
    })
  })

  it('updates data when refresh button is clicked', async () => {
    const { getCurrentPrices } = require('@/lib/api/prices')
    const user = userEvent.setup()

    render(<DashboardPage />, { wrapper })

    await waitFor(() => {
      expect(screen.getByText(/0\.25/)).toBeInTheDocument()
    })

    // Click refresh
    await user.click(screen.getByRole('button', { name: /refresh/i }))

    // Should call API again
    expect(getCurrentPrices).toHaveBeenCalledTimes(2)
  })

  it('is responsive on mobile devices', async () => {
    // Mock mobile viewport
    Object.defineProperty(window, 'innerWidth', { value: 375 })
    window.dispatchEvent(new Event('resize'))

    render(<DashboardPage />, { wrapper })

    await waitFor(() => {
      const container = screen.getByTestId('dashboard-container')
      expect(container).toHaveClass('flex-col')
    })
  })

  it('shows real-time update indicator', async () => {
    render(<DashboardPage />, { wrapper })

    await waitFor(() => {
      expect(screen.getByTestId('realtime-indicator')).toBeInTheDocument()
    })
  })

  it('displays notification banner for price alerts', async () => {
    render(<DashboardPage />, { wrapper })

    await waitFor(() => {
      // With price at 0.25 and forecast dropping to 0.18
      expect(screen.getByText(/prices dropping/i)).toBeInTheDocument()
    })
  })
})

describe('Dashboard Error Boundaries', () => {
  let queryClient: QueryClient

  beforeEach(() => {
    queryClient = new QueryClient({
      defaultOptions: {
        queries: {
          retry: false,
        },
      },
    })
  })

  const wrapper = ({ children }: { children: React.ReactNode }) => (
    <QueryClientProvider client={queryClient}>{children}</QueryClientProvider>
  )

  it('recovers from widget errors without crashing entire dashboard', async () => {
    const { getPriceForecast } = require('@/lib/api/prices')
    getPriceForecast.mockRejectedValueOnce(new Error('Forecast API Error'))

    render(<DashboardPage />, { wrapper })

    await waitFor(() => {
      // Current price should still load
      expect(screen.getByText(/current price/i)).toBeInTheDocument()
      // Forecast widget should show error state
      expect(screen.getByText(/forecast unavailable/i)).toBeInTheDocument()
    })
  })
})
