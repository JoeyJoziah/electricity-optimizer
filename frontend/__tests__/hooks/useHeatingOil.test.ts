import { renderHook, waitFor } from '@testing-library/react'
import React, { ReactNode } from 'react'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import '@testing-library/jest-dom'

const mockGetPrices = jest.fn()
const mockGetHistory = jest.fn()
const mockGetDealers = jest.fn()
const mockGetComparison = jest.fn()

jest.mock('@/lib/api/heating-oil', () => ({
  getHeatingOilPrices: (...args: unknown[]) => mockGetPrices(...args),
  getHeatingOilHistory: (...args: unknown[]) => mockGetHistory(...args),
  getHeatingOilDealers: (...args: unknown[]) => mockGetDealers(...args),
  getHeatingOilComparison: (...args: unknown[]) => mockGetComparison(...args),
}))

import {
  useHeatingOilPrices,
  useHeatingOilHistory,
  useHeatingOilDealers,
  useHeatingOilComparison,
} from '@/lib/hooks/useHeatingOil'

function createWrapper() {
  const queryClient = new QueryClient({
    defaultOptions: { queries: { retry: false, gcTime: 0 } },
  })
  return {
    queryClient,
    wrapper: ({ children }: { children: ReactNode }) =>
      React.createElement(QueryClientProvider, { client: queryClient }, children),
  }
}

describe('useHeatingOilPrices', () => {
  beforeEach(() => {
    jest.clearAllMocks()
    mockGetPrices.mockResolvedValue({ prices: [{ state: 'CT', price_per_gallon: 3.25 }], tracked_states: ['CT'] })
  })

  it('fetches prices', async () => {
    const { wrapper } = createWrapper()
    const { result } = renderHook(() => useHeatingOilPrices('CT'), { wrapper })

    await waitFor(() => expect(result.current.isSuccess).toBe(true))
    expect(result.current.data?.prices).toHaveLength(1)
  })

  it('uses correct query key', async () => {
    const { wrapper, queryClient } = createWrapper()
    renderHook(() => useHeatingOilPrices('MA'), { wrapper })

    await waitFor(() => {
      const keys = queryClient.getQueryCache().getAll().map((q) => q.queryKey)
      expect(keys).toContainEqual(['heating-oil', 'prices', 'MA'])
    })
  })

  it('handles error', async () => {
    mockGetPrices.mockRejectedValue(new Error('API error'))
    const { wrapper } = createWrapper()
    const { result } = renderHook(() => useHeatingOilPrices('CT'), { wrapper })

    await waitFor(() => expect(result.current.isError).toBe(true))
  })
})

describe('useHeatingOilHistory', () => {
  beforeEach(() => {
    jest.clearAllMocks()
    mockGetHistory.mockResolvedValue({ state: 'CT', weeks: 12, history: [] })
  })

  it('is disabled when state is undefined', () => {
    const { wrapper } = createWrapper()
    const { result } = renderHook(() => useHeatingOilHistory(undefined), { wrapper })
    expect(result.current.fetchStatus).toBe('idle')
  })

  it('fetches when state is provided', async () => {
    const { wrapper } = createWrapper()
    const { result } = renderHook(() => useHeatingOilHistory('CT', 12), { wrapper })

    await waitFor(() => expect(result.current.isSuccess).toBe(true))
  })

  it('uses correct query key with weeks', async () => {
    const { wrapper, queryClient } = createWrapper()
    renderHook(() => useHeatingOilHistory('NY', 8), { wrapper })

    await waitFor(() => {
      const keys = queryClient.getQueryCache().getAll().map((q) => q.queryKey)
      expect(keys).toContainEqual(['heating-oil', 'history', 'NY', 8])
    })
  })
})

describe('useHeatingOilDealers', () => {
  beforeEach(() => {
    jest.clearAllMocks()
    mockGetDealers.mockResolvedValue([{ name: 'Discount Oil', state: 'CT' }])
  })

  it('is disabled when state is undefined', () => {
    const { wrapper } = createWrapper()
    const { result } = renderHook(() => useHeatingOilDealers(undefined), { wrapper })
    expect(result.current.fetchStatus).toBe('idle')
  })

  it('fetches dealers when state provided', async () => {
    const { wrapper } = createWrapper()
    const { result } = renderHook(() => useHeatingOilDealers('CT'), { wrapper })

    await waitFor(() => expect(result.current.isSuccess).toBe(true))
  })
})

describe('useHeatingOilComparison', () => {
  beforeEach(() => {
    jest.clearAllMocks()
    mockGetComparison.mockResolvedValue({ state: 'CT', price_per_gallon: 3.25, national_avg: 3.10 })
  })

  it('is disabled when state is undefined', () => {
    const { wrapper } = createWrapper()
    const { result } = renderHook(() => useHeatingOilComparison(undefined), { wrapper })
    expect(result.current.fetchStatus).toBe('idle')
  })

  it('fetches comparison when state provided', async () => {
    const { wrapper } = createWrapper()
    const { result } = renderHook(() => useHeatingOilComparison('CT'), { wrapper })

    await waitFor(() => expect(result.current.isSuccess).toBe(true))
    expect(result.current.data?.national_avg).toBe(3.10)
  })
})
