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
  getCurrentPrices: (...args: any[]) => mockGetCurrentPrices(...args),
  getPriceHistory: (...args: any[]) => mockGetPriceHistory(...args),
  getPriceForecast: (...args: any[]) => mockGetPriceForecast(...args),
  getOptimalPeriods: (...args: any[]) => mockGetOptimalPeriods(...args),
}))

// Reusable mock data
const mockPricesData = {
  prices: [
    { region: 'US_CT', price: 0.25, timestamp: '2026-02-24T12:00:00Z' },
  ],
}

const mockHistoryData = {
  prices: [
    { time: '2026-02-24T10:00:00Z', price: 0.28 },
    { time: '2026-02-24T11:00:00Z', price: 0.26 },
    { time: '2026-02-24T12:00:00Z', price: 0.25 },
  ],
}

const mockForecastData = {
  forecast: [
    { hour: 1, price: 0.23, confidence: [0.21, 0.25] },
    { hour: 2, price: 0.20, confidence: [0.18, 0.22] },
  ],
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
    expect(result.current.data?.prices[0].price).toBe(0.25)
    expect(mockGetCurrentPrices).toHaveBeenCalledWith('us_ct')
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
    expect(mockGetPriceHistory).toHaveBeenCalledWith('us_ct', 24)
  })

  it('usePriceHistory respects hours parameter', async () => {
    const { result } = renderHook(() => usePriceHistory('us_ct', 48), { wrapper })

    await waitFor(() => {
      expect(result.current.isSuccess).toBe(true)
    })

    expect(mockGetPriceHistory).toHaveBeenCalledWith('us_ct', 48)
  })

  it('usePriceForecast returns forecast data', async () => {
    const { result } = renderHook(() => usePriceForecast('us_ct', 24), { wrapper })

    await waitFor(() => {
      expect(result.current.isSuccess).toBe(true)
    })

    expect(result.current.data).toEqual(mockForecastData)
    expect(result.current.data?.forecast).toHaveLength(2)
    expect(result.current.data?.forecast[0].price).toBe(0.23)
    expect(mockGetPriceForecast).toHaveBeenCalledWith('us_ct', 24)
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

    expect(mockGetCurrentPrices).toHaveBeenCalledWith('us_ct')

    // Change region
    rerender({ region: 'us_ny' })

    await waitFor(() => {
      expect(mockGetCurrentPrices).toHaveBeenCalledWith('us_ny')
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
})
