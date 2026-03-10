import { renderHook, waitFor } from '@testing-library/react'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import {
  useCurrentPrices,
  usePriceHistory,
  usePriceForecast,
  useOptimalPeriods,
} from '@/lib/hooks/usePrices'
import '@testing-library/jest-dom'
import React from 'react'

// Mock API module
const mockGetCurrentPrices = jest.fn()
const mockGetPriceHistory = jest.fn()
const mockGetPriceForecast = jest.fn()
const mockGetOptimalPeriods = jest.fn()

jest.mock('@/lib/api/prices', () => ({
  getCurrentPrices: (...args: unknown[]) => mockGetCurrentPrices(...args),
  getPriceHistory: (...args: unknown[]) => mockGetPriceHistory(...args),
  getPriceForecast: (...args: unknown[]) => mockGetPriceForecast(...args),
  getOptimalPeriods: (...args: unknown[]) => mockGetOptimalPeriods(...args),
}))

// Reusable mock data — shapes match backend API types (snake_case, Decimal strings)
const mockPricesData = {
  prices: [
    {
      ticker: 'ELEC-US_CT',
      current_price: '0.2500',
      currency: 'USD',
      region: 'us_ct',
      supplier: 'Eversource Energy',
      updated_at: '2026-02-24T12:00:00Z',
      is_peak: false,
      carbon_intensity: null,
      price_change_24h: null,
    },
  ],
  price: null,
  region: 'us_ct',
  timestamp: '2026-02-24T12:00:00Z',
  source: 'live',
}

const mockHistoryData = {
  region: 'us_ct',
  supplier: null,
  start_date: '2026-02-24T10:00:00Z',
  end_date: '2026-02-24T12:00:00Z',
  prices: [
    { id: '1', region: 'us_ct', supplier: 'Eversource Energy', price_per_kwh: '0.2800', timestamp: '2026-02-24T10:00:00Z', currency: 'USD', utility_type: 'electricity', unit: 'kwh', is_peak: null, carbon_intensity: null, energy_source: null, tariff_name: null, energy_cost: null, network_cost: null, taxes: null, levies: null, source_api: null, created_at: '2026-02-24T10:00:00Z' },
    { id: '2', region: 'us_ct', supplier: 'Eversource Energy', price_per_kwh: '0.2600', timestamp: '2026-02-24T11:00:00Z', currency: 'USD', utility_type: 'electricity', unit: 'kwh', is_peak: null, carbon_intensity: null, energy_source: null, tariff_name: null, energy_cost: null, network_cost: null, taxes: null, levies: null, source_api: null, created_at: '2026-02-24T11:00:00Z' },
    { id: '3', region: 'us_ct', supplier: 'Eversource Energy', price_per_kwh: '0.2500', timestamp: '2026-02-24T12:00:00Z', currency: 'USD', utility_type: 'electricity', unit: 'kwh', is_peak: null, carbon_intensity: null, energy_source: null, tariff_name: null, energy_cost: null, network_cost: null, taxes: null, levies: null, source_api: null, created_at: '2026-02-24T12:00:00Z' },
  ],
  average_price: '0.2633',
  min_price: '0.2500',
  max_price: '0.2800',
  source: 'live',
  total: 3,
  page: 1,
  page_size: 24,
  pages: 1,
}

const mockForecastData = {
  region: 'us_ct',
  forecast: {
    id: 'abc',
    region: 'us_ct',
    generated_at: '2026-02-24T12:00:00Z',
    horizon_hours: 24,
    prices: [
      { id: '1', region: 'us_ct', supplier: 'Eversource Energy', price_per_kwh: '0.2300', timestamp: '2026-02-24T13:00:00Z', currency: 'USD', utility_type: 'electricity', unit: 'kwh', is_peak: null, carbon_intensity: null, energy_source: null, tariff_name: null, energy_cost: null, network_cost: null, taxes: null, levies: null, source_api: null, created_at: '2026-02-24T12:00:00Z' },
      { id: '2', region: 'us_ct', supplier: 'Eversource Energy', price_per_kwh: '0.2000', timestamp: '2026-02-24T14:00:00Z', currency: 'USD', utility_type: 'electricity', unit: 'kwh', is_peak: null, carbon_intensity: null, energy_source: null, tariff_name: null, energy_cost: null, network_cost: null, taxes: null, levies: null, source_api: null, created_at: '2026-02-24T12:00:00Z' },
    ],
    confidence: 0.85,
    model_version: 'v1',
    source_api: null,
  },
  generated_at: '2026-02-24T12:00:00Z',
  horizon_hours: 24,
  confidence: 0.85,
  source: 'live',
}

const mockOptimalData = {
  periods: [
    { start: '2026-02-24T02:00:00Z', end: '2026-02-24T05:00:00Z', avgPrice: 0.15 },
  ],
}

describe('usePrices hooks', () => {
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

    mockGetCurrentPrices.mockResolvedValue(mockPricesData)
    mockGetPriceHistory.mockResolvedValue(mockHistoryData)
    mockGetPriceForecast.mockResolvedValue(mockForecastData)
    mockGetOptimalPeriods.mockResolvedValue(mockOptimalData)
  })

  afterEach(() => {
    queryClient.clear()
    jest.clearAllMocks()
  })

  const wrapper = ({ children }: { children: React.ReactNode }) => (
    <QueryClientProvider client={queryClient}>{children}</QueryClientProvider>
  )

  it('useCurrentPrices returns price data', async () => {
    const { result } = renderHook(() => useCurrentPrices('us_ct'), { wrapper })

    await waitFor(() => {
      expect(result.current.isSuccess).toBe(true)
    })

    expect(result.current.data).toEqual(mockPricesData)
    // current_price is a Decimal string from the backend
    expect(result.current.data?.prices?.[0].current_price).toBe('0.2500')
    expect(mockGetCurrentPrices).toHaveBeenCalledWith({ region: 'us_ct' })
  })

  it('useCurrentPrices handles error', async () => {
    mockGetCurrentPrices.mockRejectedValue(new Error('Failed to fetch prices'))

    const { result } = renderHook(() => useCurrentPrices('us_ct'), { wrapper })

    await waitFor(() => {
      expect(result.current.isError).toBe(true)
    })

    expect(result.current.error).toBeInstanceOf(Error)
    expect(result.current.error?.message).toBe('Failed to fetch prices')
    expect(result.current.data).toBeUndefined()
  })

  it('usePriceHistory returns historical data', async () => {
    const { result } = renderHook(() => usePriceHistory('us_ct', 24), { wrapper })

    await waitFor(() => {
      expect(result.current.isSuccess).toBe(true)
    })

    expect(result.current.data).toEqual(mockHistoryData)
    expect(result.current.data?.prices).toHaveLength(3)
    // Hook converts hours→days: 24h = 1 day
    expect(mockGetPriceHistory).toHaveBeenCalledWith({ region: 'us_ct', days: 1 })
  })

  it('usePriceHistory respects hours parameter', async () => {
    const { result } = renderHook(() => usePriceHistory('us_ct', 48), { wrapper })

    await waitFor(() => {
      expect(result.current.isSuccess).toBe(true)
    })

    // Hook converts hours→days: 48h = 2 days
    expect(mockGetPriceHistory).toHaveBeenCalledWith({ region: 'us_ct', days: 2 })
  })

  it('usePriceForecast returns forecast data', async () => {
    const { result } = renderHook(() => usePriceForecast('us_ct', 24), { wrapper })

    await waitFor(() => {
      expect(result.current.isSuccess).toBe(true)
    })

    expect(result.current.data).toEqual(mockForecastData)
    // forecast is now an ApiPriceForecastModel object, not an array
    expect(result.current.data?.forecast.prices).toHaveLength(2)
    expect(result.current.data?.forecast.prices[0].price_per_kwh).toBe('0.2300')
    expect(mockGetPriceForecast).toHaveBeenCalledWith({ region: 'us_ct', hours: 24 })
  })

  it('usePriceForecast handles missing forecast', async () => {
    mockGetPriceForecast.mockRejectedValue(new Error('Forecast unavailable'))

    const { result } = renderHook(() => usePriceForecast('us_ct', 24), { wrapper })

    await waitFor(() => {
      expect(result.current.isError).toBe(true)
    })

    expect(result.current.data).toBeUndefined()
    expect(result.current.error?.message).toBe('Forecast unavailable')
  })

  it('useOptimalPeriods returns periods', async () => {
    const { result } = renderHook(() => useOptimalPeriods('us_ct', 24), { wrapper })

    await waitFor(() => {
      expect(result.current.isSuccess).toBe(true)
    })

    expect(result.current.data).toEqual(mockOptimalData)
    expect(result.current.data?.periods).toHaveLength(1)
    expect(result.current.data?.periods[0].avgPrice).toBe(0.15)
    expect(mockGetOptimalPeriods).toHaveBeenCalledWith('us_ct', 24)
  })

  it('useCurrentPrices refetches on region change', async () => {
    const { result, rerender } = renderHook(
      ({ region }: { region: string }) => useCurrentPrices(region),
      {
        wrapper,
        initialProps: { region: 'us_ct' },
      }
    )

    await waitFor(() => {
      expect(result.current.isSuccess).toBe(true)
    })

    expect(mockGetCurrentPrices).toHaveBeenCalledWith({ region: 'us_ct' })

    // Change region
    rerender({ region: 'us_ny' })

    await waitFor(() => {
      expect(mockGetCurrentPrices).toHaveBeenCalledWith({ region: 'us_ny' })
    })

    // Should have been called with both regions
    expect(mockGetCurrentPrices).toHaveBeenCalledTimes(2)
  })

  it('hooks use correct query keys', async () => {
    renderHook(() => useCurrentPrices('us_ct'), { wrapper })
    renderHook(() => usePriceHistory('us_ct', 24), { wrapper })
    renderHook(() => usePriceForecast('us_ct', 48), { wrapper })
    renderHook(() => useOptimalPeriods('us_ct', 24), { wrapper })

    await waitFor(() => {
      // Verify query cache contains the expected keys
      const queries = queryClient.getQueryCache().getAll()
      const keys = queries.map((q) => q.queryKey)

      expect(keys).toContainEqual(['prices', 'current', 'us_ct'])
      expect(keys).toContainEqual(['prices', 'history', 'us_ct', 24])
      expect(keys).toContainEqual(['prices', 'forecast', 'us_ct', 48])
      expect(keys).toContainEqual(['prices', 'optimal', 'us_ct', 24])
    })
  })

  it('hooks retry on transient failures', async () => {
    // Create a query client that retries once
    const retryClient = new QueryClient({
      defaultOptions: {
        queries: {
          retry: 1,
          retryDelay: 0,
          gcTime: 0,
        },
      },
    })

    const retryWrapper = ({ children }: { children: React.ReactNode }) => (
      <QueryClientProvider client={retryClient}>{children}</QueryClientProvider>
    )

    // First call fails, second succeeds
    mockGetCurrentPrices
      .mockRejectedValueOnce(new Error('Transient error'))
      .mockResolvedValueOnce(mockPricesData)

    const { result } = renderHook(() => useCurrentPrices('us_ct'), {
      wrapper: retryWrapper,
    })

    await waitFor(() => {
      expect(result.current.isSuccess).toBe(true)
    })

    expect(result.current.data).toEqual(mockPricesData)
    expect(mockGetCurrentPrices).toHaveBeenCalledTimes(2)

    retryClient.clear()
  })

  // ========================================================================
  // Null-region guard tests (enabled: !!region)
  // ========================================================================

  it('useCurrentPrices(null) is disabled — no API call', () => {
    const { result } = renderHook(() => useCurrentPrices(null), { wrapper })

    expect(result.current.fetchStatus).toBe('idle')
    expect(mockGetCurrentPrices).not.toHaveBeenCalled()
  })

  it('usePriceHistory(null) is disabled — no API call', () => {
    const { result } = renderHook(() => usePriceHistory(null, 24), { wrapper })

    expect(result.current.fetchStatus).toBe('idle')
    expect(mockGetPriceHistory).not.toHaveBeenCalled()
  })

  it('usePriceForecast(null) is disabled — no API call', () => {
    const { result } = renderHook(() => usePriceForecast(null, 24), { wrapper })

    expect(result.current.fetchStatus).toBe('idle')
    expect(mockGetPriceForecast).not.toHaveBeenCalled()
  })

  it('useOptimalPeriods(null) is disabled — no API call', () => {
    const { result } = renderHook(() => useOptimalPeriods(null, 24), { wrapper })

    expect(result.current.fetchStatus).toBe('idle')
    expect(mockGetOptimalPeriods).not.toHaveBeenCalled()
  })

  it('useCurrentPrices activates when region transitions from null to string', async () => {
    const { result, rerender } = renderHook(
      ({ region }: { region: string | null }) => useCurrentPrices(region),
      {
        wrapper,
        initialProps: { region: null as string | null },
      }
    )

    // Initially disabled
    expect(result.current.fetchStatus).toBe('idle')
    expect(mockGetCurrentPrices).not.toHaveBeenCalled()

    // Transition to a real region
    rerender({ region: 'us_ct' })

    await waitFor(() => {
      expect(result.current.isSuccess).toBe(true)
    })

    expect(mockGetCurrentPrices).toHaveBeenCalledWith({ region: 'us_ct' })
  })
})
