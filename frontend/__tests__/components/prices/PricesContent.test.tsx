import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import '@testing-library/jest-dom'
import React from 'react'

// Mock next/dynamic to resolve dynamic imports synchronously
jest.mock('next/dynamic', () => {
  return (loader: () => Promise<any>, options?: { loading?: () => React.ReactNode }) => {
    const DynamicComponent = (props: any) => {
      const [Comp, setComp] = React.useState<React.ComponentType<any> | null>(null)

      React.useEffect(() => {
        loader().then((mod: any) => {
          setComp(() => mod.default || mod.PriceLineChart || mod.ForecastChart || mod)
        })
      }, [])

      if (!Comp && options?.loading) {
        return options.loading()
      }
      if (!Comp) return null
      return <Comp {...props} />
    }
    DynamicComponent.displayName = 'DynamicComponent'
    return DynamicComponent
  }
})

// Mock chart components
jest.mock('@/components/charts/PriceLineChart', () => ({
  PriceLineChart: ({ data, timeRange, onTimeRangeChange, loading }: any) => (
    <div data-testid="price-line-chart">
      {loading && <div data-testid="chart-loading">Loading chart...</div>}
      <span data-testid="chart-time-range">{timeRange}</span>
      <span data-testid="chart-data-points">{data?.length ?? 0}</span>
      {onTimeRangeChange && (
        <select
          data-testid="time-range-selector"
          value={timeRange}
          onChange={(e) => onTimeRangeChange(e.target.value)}
        >
          <option value="6h">6h</option>
          <option value="12h">12h</option>
          <option value="24h">24h</option>
          <option value="48h">48h</option>
          <option value="7d">7d</option>
        </select>
      )}
    </div>
  ),
}))

jest.mock('@/components/charts/ForecastChart', () => ({
  ForecastChart: ({ forecast, currentPrice }: any) => (
    <div data-testid="forecast-chart">
      <span data-testid="forecast-points">
        {Array.isArray(forecast) ? forecast.length : 0}
      </span>
      {currentPrice && (
        <span data-testid="forecast-current">{currentPrice}</span>
      )}
    </div>
  ),
}))

// Mock the Header component to avoid sidebar context dependency
jest.mock('@/components/layout/Header', () => ({
  Header: ({ title }: { title: string }) => (
    <header data-testid="page-header">
      <h1>{title}</h1>
    </header>
  ),
}))

// Mock settings store with configurable state
const mockAddPriceAlert = jest.fn()
const mockRemovePriceAlert = jest.fn()
let mockPriceAlerts: any[] = []

jest.mock('@/lib/store/settings', () => ({
  useSettingsStore: (selector: (state: any) => any) =>
    selector({
      region: 'us_ct',
      priceAlerts: mockPriceAlerts,
      addPriceAlert: mockAddPriceAlert,
      removePriceAlert: mockRemovePriceAlert,
    }),
}))

// Mock API modules
const mockGetCurrentPrices = jest.fn()
const mockGetPriceHistory = jest.fn()
const mockGetPriceForecast = jest.fn()
const mockGetOptimalPeriods = jest.fn()

jest.mock('@/lib/api/prices', () => ({
  getCurrentPrices: (...args: any[]) => mockGetCurrentPrices(...args),
  getPriceHistory: (...args: any[]) => mockGetPriceHistory(...args),
  getPriceForecast: (...args: any[]) => mockGetPriceForecast(...args),
  getOptimalPeriods: (...args: any[]) => mockGetOptimalPeriods(...args),
}))

// Import after mocks are set up
import PricesContent from '@/components/prices/PricesContent'

// Default mock data
const defaultPricesResponse = {
  prices: [
    {
      region: 'US_CT',
      price: 0.25,
      timestamp: '2026-02-24T12:00:00Z',
      trend: 'stable',
      changePercent: -1.2,
    },
  ],
}

const defaultHistoryResponse = {
  prices: [
    { time: '2026-02-24T08:00:00Z', price: 0.28 },
    { time: '2026-02-24T09:00:00Z', price: 0.22 },
    { time: '2026-02-24T10:00:00Z', price: 0.19 },
    { time: '2026-02-24T11:00:00Z', price: 0.26 },
    { time: '2026-02-24T12:00:00Z', price: 0.25 },
  ],
}

const defaultForecastResponse = {
  forecast: [
    { hour: 1, price: 0.23, confidence: [0.21, 0.25], timestamp: '2026-02-24T13:00:00Z' },
    { hour: 2, price: 0.20, confidence: [0.18, 0.22], timestamp: '2026-02-24T14:00:00Z' },
    { hour: 3, price: 0.18, confidence: [0.16, 0.20], timestamp: '2026-02-24T15:00:00Z' },
  ],
}

const defaultOptimalResponse = {
  periods: [
    { start: '2026-02-24T02:00:00Z', end: '2026-02-24T05:00:00Z', avgPrice: 0.15 },
    { start: '2026-02-24T13:00:00Z', end: '2026-02-24T15:00:00Z', avgPrice: 0.18 },
  ],
}

describe('PricesContent', () => {
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

    mockPriceAlerts = []
    mockGetCurrentPrices.mockResolvedValue(defaultPricesResponse)
    mockGetPriceHistory.mockResolvedValue(defaultHistoryResponse)
    mockGetPriceForecast.mockResolvedValue(defaultForecastResponse)
    mockGetOptimalPeriods.mockResolvedValue(defaultOptimalResponse)
  })

  afterEach(() => {
    queryClient.clear()
    jest.clearAllMocks()
  })

  const wrapper = ({ children }: { children: React.ReactNode }) => (
    <QueryClientProvider client={queryClient}>{children}</QueryClientProvider>
  )

  // --- Loading State Tests ---

  it('renders loading skeletons while data is fetching', () => {
    mockGetCurrentPrices.mockReturnValue(new Promise(() => {}))
    mockGetPriceHistory.mockReturnValue(new Promise(() => {}))
    mockGetPriceForecast.mockReturnValue(new Promise(() => {}))
    mockGetOptimalPeriods.mockReturnValue(new Promise(() => {}))

    render(<PricesContent />, { wrapper })

    // Skeletons use animate-pulse class
    const skeletons = document.querySelectorAll('.animate-pulse')
    expect(skeletons.length).toBeGreaterThan(0)
  })

  it('renders stat card labels during loading', () => {
    mockGetCurrentPrices.mockReturnValue(new Promise(() => {}))
    mockGetPriceHistory.mockReturnValue(new Promise(() => {}))
    mockGetPriceForecast.mockReturnValue(new Promise(() => {}))
    mockGetOptimalPeriods.mockReturnValue(new Promise(() => {}))

    render(<PricesContent />, { wrapper })

    expect(screen.getByText('Current Price')).toBeInTheDocument()
    expect(screen.getByText("Today's Low")).toBeInTheDocument()
    expect(screen.getByText("Today's High")).toBeInTheDocument()
    expect(screen.getByText('Average')).toBeInTheDocument()
  })

  // --- Data Rendering Tests ---

  it('renders current price when data is loaded', async () => {
    render(<PricesContent />, { wrapper })

    await waitFor(() => {
      expect(screen.getByText(/0\.25/)).toBeInTheDocument()
    })
  })

  it('renders today low and high from history data', async () => {
    render(<PricesContent />, { wrapper })

    await waitFor(() => {
      // Low = 0.19, High = 0.28
      expect(screen.getByText(/0\.19/)).toBeInTheDocument()
      expect(screen.getByText(/0\.28/)).toBeInTheDocument()
    })
  })

  it('renders average price from history data', async () => {
    render(<PricesContent />, { wrapper })

    await waitFor(() => {
      // Average = (0.28 + 0.22 + 0.19 + 0.26 + 0.25) / 5 = 0.24
      expect(screen.getByText(/0\.24/)).toBeInTheDocument()
    })
  })

  it('renders page header with title', async () => {
    render(<PricesContent />, { wrapper })

    expect(screen.getByText('Electricity Prices')).toBeInTheDocument()
  })

  it('renders the kWh unit labels', async () => {
    render(<PricesContent />, { wrapper })

    await waitFor(() => {
      const kwhLabels = screen.getAllByText('/kWh')
      expect(kwhLabels.length).toBeGreaterThanOrEqual(1)
    })
  })

  // --- Chart Section Tests ---

  it('renders price history and forecast chart section', async () => {
    render(<PricesContent />, { wrapper })

    await waitFor(() => {
      expect(screen.getByText('Price History & Forecast')).toBeInTheDocument()
      expect(screen.getByTestId('price-line-chart')).toBeInTheDocument()
    })
  })

  it('renders live updates badge', async () => {
    render(<PricesContent />, { wrapper })

    await waitFor(() => {
      expect(screen.getByText('Live updates')).toBeInTheDocument()
    })
  })

  it('default time range is 24h', async () => {
    render(<PricesContent />, { wrapper })

    await waitFor(() => {
      expect(screen.getByTestId('chart-time-range')).toHaveTextContent('24h')
    })
  })

  it('time range selector changes chart data', async () => {
    const user = userEvent.setup()
    render(<PricesContent />, { wrapper })

    await waitFor(() => {
      expect(screen.getByTestId('price-line-chart')).toBeInTheDocument()
    })

    const selector = screen.getByTestId('time-range-selector')
    await user.selectOptions(selector, '48h')

    await waitFor(() => {
      expect(screen.getByTestId('chart-time-range')).toHaveTextContent('48h')
    })
  })

  it('passes chart data with correct number of data points', async () => {
    render(<PricesContent />, { wrapper })

    await waitFor(() => {
      // 5 history points + 3 forecast points = 8
      expect(screen.getByTestId('chart-data-points')).toHaveTextContent('8')
    })
  })

  // --- Optimal Periods Tests ---

  it('renders optimal time periods section', async () => {
    render(<PricesContent />, { wrapper })

    await waitFor(() => {
      expect(screen.getByText('Optimal Time Periods')).toBeInTheDocument()
    })
  })

  it('renders Best Time badges for each optimal period', async () => {
    render(<PricesContent />, { wrapper })

    await waitFor(() => {
      const badges = screen.getAllByText(/Best Time/)
      expect(badges).toHaveLength(2)
    })
  })

  it('shows "No optimal periods found" when no periods exist', async () => {
    mockGetOptimalPeriods.mockResolvedValue({ periods: [] })

    render(<PricesContent />, { wrapper })

    await waitFor(() => {
      expect(screen.getByText(/No optimal periods found/)).toBeInTheDocument()
    })
  })

  // --- Price Alerts Tests ---

  it('renders price alerts section', async () => {
    render(<PricesContent />, { wrapper })

    await waitFor(() => {
      expect(screen.getByText('Price Alerts')).toBeInTheDocument()
    })
  })

  it('shows both preset alert options', async () => {
    render(<PricesContent />, { wrapper })

    await waitFor(() => {
      expect(screen.getByText(/Price below \$0\.20/)).toBeInTheDocument()
      expect(screen.getByText(/Price above \$0\.30/)).toBeInTheDocument()
    })
  })

  it('shows "Set Alert" buttons when no alerts are active', async () => {
    render(<PricesContent />, { wrapper })

    await waitFor(() => {
      const setAlertButtons = screen.getAllByText(/Set Alert/)
      expect(setAlertButtons).toHaveLength(2)
    })
  })

  it('shows "Active" buttons when alerts are enabled', async () => {
    mockPriceAlerts = [
      { id: '1', type: 'below', threshold: 0.20, enabled: true },
      { id: '2', type: 'above', threshold: 0.30, enabled: true },
    ]

    render(<PricesContent />, { wrapper })

    await waitFor(() => {
      const activeButtons = screen.getAllByText('Active')
      expect(activeButtons).toHaveLength(2)
    })
  })

  it('calls addPriceAlert when "Set Alert" is clicked', async () => {
    const user = userEvent.setup()
    render(<PricesContent />, { wrapper })

    await waitFor(() => {
      expect(screen.getAllByText(/Set Alert/).length).toBe(2)
    })

    const setAlertButtons = screen.getAllByText(/Set Alert/)
    await user.click(setAlertButtons[0])

    expect(mockAddPriceAlert).toHaveBeenCalledWith(
      expect.objectContaining({
        type: 'below',
        threshold: 0.20,
        enabled: true,
      })
    )
  })

  it('calls removePriceAlert when "Active" button is clicked', async () => {
    mockPriceAlerts = [
      { id: 'existing-alert', type: 'below', threshold: 0.20, enabled: true },
    ]

    const user = userEvent.setup()
    render(<PricesContent />, { wrapper })

    await waitFor(() => {
      expect(screen.getByText('Active')).toBeInTheDocument()
    })

    await user.click(screen.getByText('Active'))

    expect(mockRemovePriceAlert).toHaveBeenCalledWith('existing-alert')
  })

  it('shows settings link text', async () => {
    render(<PricesContent />, { wrapper })

    await waitFor(() => {
      expect(screen.getByText(/Configure more alerts in Settings/)).toBeInTheDocument()
    })
  })

  // --- 48-Hour Forecast Tests ---

  it('renders 48-hour forecast section', async () => {
    render(<PricesContent />, { wrapper })

    await waitFor(() => {
      expect(screen.getByText('48-Hour Forecast')).toBeInTheDocument()
    })
  })

  it('renders forecast chart when forecast data is available', async () => {
    render(<PricesContent />, { wrapper })

    await waitFor(() => {
      expect(screen.getByTestId('forecast-chart')).toBeInTheDocument()
    })
  })

  it('shows forecast loading skeleton while forecast loads', () => {
    mockGetCurrentPrices.mockResolvedValue(defaultPricesResponse)
    mockGetPriceHistory.mockResolvedValue(defaultHistoryResponse)
    mockGetPriceForecast.mockReturnValue(new Promise(() => {}))
    mockGetOptimalPeriods.mockResolvedValue(defaultOptimalResponse)

    render(<PricesContent />, { wrapper })

    // At least one skeleton should appear for the forecast area
    const skeletons = document.querySelectorAll('.animate-pulse')
    expect(skeletons.length).toBeGreaterThan(0)
  })

  it('shows "Forecast unavailable" when forecast API fails', async () => {
    mockGetPriceForecast.mockRejectedValue(new Error('Forecast API Error'))

    render(<PricesContent />, { wrapper })

    await waitFor(() => {
      expect(screen.getByText('Forecast unavailable')).toBeInTheDocument()
    })
  })

  // --- Trend Indicator Tests ---

  it('shows stable trend by default', async () => {
    render(<PricesContent />, { wrapper })

    await waitFor(() => {
      expect(screen.getByText(/vs last hour/)).toBeInTheDocument()
    })
  })

  it('displays negative change percent', async () => {
    render(<PricesContent />, { wrapper })

    await waitFor(() => {
      expect(screen.getByText(/-1\.2%/)).toBeInTheDocument()
    })
  })

  it('displays positive change percent with + sign', async () => {
    mockGetCurrentPrices.mockResolvedValue({
      prices: [
        {
          region: 'US_CT',
          price: 0.31,
          timestamp: '2026-02-24T12:00:00Z',
          trend: 'increasing',
          changePercent: 5.3,
        },
      ],
    })

    render(<PricesContent />, { wrapper })

    await waitFor(() => {
      expect(screen.getByText(/\+5\.3%/)).toBeInTheDocument()
    })
  })

  // --- Empty / Error State Tests ---

  it('handles empty price data gracefully', async () => {
    mockGetCurrentPrices.mockResolvedValue({ prices: [] })
    mockGetPriceHistory.mockResolvedValue({ prices: [] })
    mockGetOptimalPeriods.mockResolvedValue({ periods: [] })

    render(<PricesContent />, { wrapper })

    await waitFor(() => {
      const dashes = screen.getAllByText('--')
      expect(dashes.length).toBeGreaterThan(0)
    })
  })

  it('handles all API errors without crashing', async () => {
    mockGetCurrentPrices.mockRejectedValue(new Error('API Error'))
    mockGetPriceHistory.mockRejectedValue(new Error('API Error'))
    mockGetPriceForecast.mockRejectedValue(new Error('API Error'))
    mockGetOptimalPeriods.mockRejectedValue(new Error('API Error'))

    render(<PricesContent />, { wrapper })

    await waitFor(() => {
      expect(screen.getByText('Current Price')).toBeInTheDocument()
      expect(screen.getAllByText('--').length).toBeGreaterThan(0)
      expect(screen.getByText('Forecast unavailable')).toBeInTheDocument()
    })
  })

  it('handles backend field names (price_per_kwh) in history data', async () => {
    // Use values that do not collide with alert thresholds ($0.20 / $0.30)
    mockGetPriceHistory.mockResolvedValue({
      prices: [
        { timestamp: '2026-02-24T08:00:00Z', price_per_kwh: '0.21' },
        { timestamp: '2026-02-24T09:00:00Z', price_per_kwh: '0.33' },
      ],
    })

    render(<PricesContent />, { wrapper })

    await waitFor(() => {
      // Low = 0.21, High = 0.33
      expect(screen.getByText(/0\.21/)).toBeInTheDocument()
      expect(screen.getByText(/0\.33/)).toBeInTheDocument()
    })
  })

  it('handles backend field names (current_price) for current price', async () => {
    mockGetCurrentPrices.mockResolvedValue({
      prices: [
        {
          region: 'US_CT',
          current_price: 0.27,
          timestamp: '2026-02-24T12:00:00Z',
        },
      ],
    })

    render(<PricesContent />, { wrapper })

    await waitFor(() => {
      expect(screen.getByText(/0\.27/)).toBeInTheDocument()
    })
  })
})
