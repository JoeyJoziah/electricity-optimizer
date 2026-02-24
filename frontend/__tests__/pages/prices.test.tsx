import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import PricesPage from '@/app/(app)/prices/page'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import '@testing-library/jest-dom'

// Mock next/dynamic to render loading fallbacks or passthrough
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

import React from 'react'

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
      <span data-testid="forecast-points">{Array.isArray(forecast) ? forecast.length : 0}</span>
      {currentPrice && <span data-testid="forecast-current">{currentPrice}</span>}
    </div>
  ),
}))

// Mock settings store with all fields the prices page uses
const mockAddPriceAlert = jest.fn()
const mockRemovePriceAlert = jest.fn()

jest.mock('@/lib/store/settings', () => ({
  useSettingsStore: (selector: (state: any) => any) =>
    selector({
      region: 'us_ct',
      priceAlerts: [],
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

// Default mock responses
const defaultPricesResponse = {
  prices: [
    { region: 'US_CT', price: 0.25, timestamp: '2026-02-24T12:00:00Z', trend: 'stable', changePercent: -1.2 },
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

describe('PricesPage', () => {
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

  it('renders current price card', async () => {
    render(<PricesPage />, { wrapper })

    await waitFor(() => {
      expect(screen.getByText('Current Price')).toBeInTheDocument()
      expect(screen.getByText(/0\.25/)).toBeInTheDocument()
    })
  })

  it('renders today low/high/average stats', async () => {
    render(<PricesPage />, { wrapper })

    await waitFor(() => {
      expect(screen.getByText("Today's Low")).toBeInTheDocument()
      expect(screen.getByText("Today's High")).toBeInTheDocument()
      expect(screen.getByText('Average')).toBeInTheDocument()
      // Low = 0.19, High = 0.28
      expect(screen.getByText(/0\.19/)).toBeInTheDocument()
      expect(screen.getByText(/0\.28/)).toBeInTheDocument()
    })
  })

  it('renders loading skeletons while data loads', () => {
    mockGetCurrentPrices.mockReturnValue(new Promise(() => {}))
    mockGetPriceHistory.mockReturnValue(new Promise(() => {}))
    mockGetPriceForecast.mockReturnValue(new Promise(() => {}))
    mockGetOptimalPeriods.mockReturnValue(new Promise(() => {}))

    render(<PricesPage />, { wrapper })

    // Should show skeleton placeholders while loading
    const skeletons = document.querySelectorAll('.animate-pulse')
    expect(skeletons.length).toBeGreaterThan(0)
  })

  it('renders price chart section', async () => {
    render(<PricesPage />, { wrapper })

    await waitFor(() => {
      expect(screen.getByText('Price History & Forecast')).toBeInTheDocument()
      expect(screen.getByTestId('price-line-chart')).toBeInTheDocument()
    })
  })

  it('renders optimal periods section', async () => {
    render(<PricesPage />, { wrapper })

    await waitFor(() => {
      expect(screen.getByText('Optimal Time Periods')).toBeInTheDocument()
      // Two optimal periods should each show a "Best Time" badge
      expect(screen.getAllByText(/Best Time/).length).toBe(2)
    })
  })

  it('renders price alerts section', async () => {
    render(<PricesPage />, { wrapper })

    await waitFor(() => {
      expect(screen.getByText('Price Alerts')).toBeInTheDocument()
      expect(screen.getByText(/Price below \$0\.20/)).toBeInTheDocument()
      expect(screen.getByText(/Price above \$0\.30/)).toBeInTheDocument()
      expect(screen.getAllByText(/Set Alert/).length).toBe(2)
    })
  })

  it('handles empty price data gracefully', async () => {
    mockGetCurrentPrices.mockResolvedValue({ prices: [] })
    mockGetPriceHistory.mockResolvedValue({ prices: [] })
    mockGetOptimalPeriods.mockResolvedValue({ periods: [] })

    render(<PricesPage />, { wrapper })

    await waitFor(() => {
      // Should show dashes when no price data
      expect(screen.getAllByText('--').length).toBeGreaterThan(0)
      // Should show "no optimal periods" message
      expect(screen.getByText(/No optimal periods found/)).toBeInTheDocument()
    })
  })

  it('time range selector changes chart data', async () => {
    const user = userEvent.setup()
    render(<PricesPage />, { wrapper })

    await waitFor(() => {
      expect(screen.getByTestId('price-line-chart')).toBeInTheDocument()
    })

    // Default is 24h
    expect(screen.getByTestId('chart-time-range')).toHaveTextContent('24h')

    // Change time range to 48h
    const selector = screen.getByTestId('time-range-selector')
    await user.selectOptions(selector, '48h')

    await waitFor(() => {
      expect(screen.getByTestId('chart-time-range')).toHaveTextContent('48h')
    })
  })

  it('displays 48-hour forecast section', async () => {
    render(<PricesPage />, { wrapper })

    await waitFor(() => {
      expect(screen.getByText('48-Hour Forecast')).toBeInTheDocument()
      expect(screen.getByTestId('forecast-chart')).toBeInTheDocument()
    })
  })

  it('handles API errors gracefully', async () => {
    mockGetCurrentPrices.mockRejectedValue(new Error('API Error'))
    mockGetPriceHistory.mockRejectedValue(new Error('API Error'))
    mockGetPriceForecast.mockRejectedValue(new Error('API Error'))
    mockGetOptimalPeriods.mockRejectedValue(new Error('API Error'))

    render(<PricesPage />, { wrapper })

    await waitFor(() => {
      // Page should still render without crashing
      expect(screen.getByText('Current Price')).toBeInTheDocument()
      // Should show dashes for missing data
      expect(screen.getAllByText('--').length).toBeGreaterThan(0)
      // Forecast unavailable message
      expect(screen.getByText('Forecast unavailable')).toBeInTheDocument()
    })
  })
})
