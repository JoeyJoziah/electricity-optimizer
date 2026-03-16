import { renderHook, waitFor } from '@testing-library/react'
import React, { ReactNode } from 'react'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import '@testing-library/jest-dom'

const mockGetWaterRates = jest.fn()
const mockGetWaterBenchmark = jest.fn()
const mockGetWaterTips = jest.fn()

jest.mock('@/lib/api/water', () => ({
  getWaterRates: (...args: unknown[]) => mockGetWaterRates(...args),
  getWaterBenchmark: (...args: unknown[]) => mockGetWaterBenchmark(...args),
  getWaterTips: (...args: unknown[]) => mockGetWaterTips(...args),
}))

import { useWaterRates, useWaterBenchmark, useWaterTips } from '@/lib/hooks/useWater'

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

describe('useWaterRates', () => {
  beforeEach(() => {
    jest.clearAllMocks()
    mockGetWaterRates.mockResolvedValue({
      rates: [{ id: 'wr-1', municipality: 'Hartford', state: 'CT', rate_tiers: [], base_charge: 15 }],
      count: 1,
    })
  })

  it('fetches water rates', async () => {
    const { wrapper } = createWrapper()
    const { result } = renderHook(() => useWaterRates('CT'), { wrapper })

    await waitFor(() => expect(result.current.isSuccess).toBe(true))
    expect(result.current.data?.rates).toHaveLength(1)
  })

  it('uses correct query key', async () => {
    const { wrapper, queryClient } = createWrapper()
    renderHook(() => useWaterRates('NY'), { wrapper })

    await waitFor(() => {
      const keys = queryClient.getQueryCache().getAll().map((q) => q.queryKey)
      expect(keys).toContainEqual(['water', 'rates', 'NY'])
    })
  })

  it('handles error', async () => {
    mockGetWaterRates.mockRejectedValue(new Error('Not available'))
    const { wrapper } = createWrapper()
    const { result } = renderHook(() => useWaterRates('CT'), { wrapper })

    await waitFor(() => expect(result.current.isError).toBe(true))
  })
})

describe('useWaterBenchmark', () => {
  beforeEach(() => {
    jest.clearAllMocks()
    mockGetWaterBenchmark.mockResolvedValue({
      state: 'CT',
      avg_cost: 45,
      user_cost: 52,
      percentile: 65,
    })
  })

  it('is disabled when state is undefined', () => {
    const { wrapper } = createWrapper()
    const { result } = renderHook(() => useWaterBenchmark(undefined), { wrapper })
    expect(result.current.fetchStatus).toBe('idle')
  })

  it('fetches benchmark when state provided', async () => {
    const { wrapper } = createWrapper()
    const { result } = renderHook(() => useWaterBenchmark('CT', 5000), { wrapper })

    await waitFor(() => expect(result.current.isSuccess).toBe(true))
    expect(result.current.data?.percentile).toBe(65)
  })

  it('uses correct query key with usage', async () => {
    const { wrapper, queryClient } = createWrapper()
    renderHook(() => useWaterBenchmark('CT', 8000), { wrapper })

    await waitFor(() => {
      const keys = queryClient.getQueryCache().getAll().map((q) => q.queryKey)
      expect(keys).toContainEqual(['water', 'benchmark', 'CT', 8000])
    })
  })
})

describe('useWaterTips', () => {
  beforeEach(() => {
    jest.clearAllMocks()
    mockGetWaterTips.mockResolvedValue([
      { id: 'tip-1', title: 'Fix leaky faucets', savings_gallons: 3000 },
    ])
  })

  it('fetches tips', async () => {
    const { wrapper } = createWrapper()
    const { result } = renderHook(() => useWaterTips(), { wrapper })

    await waitFor(() => expect(result.current.isSuccess).toBe(true))
    expect(result.current.data).toHaveLength(1)
  })

  it('uses correct query key', async () => {
    const { wrapper, queryClient } = createWrapper()
    renderHook(() => useWaterTips(), { wrapper })

    await waitFor(() => {
      const keys = queryClient.getQueryCache().getAll().map((q) => q.queryKey)
      expect(keys).toContainEqual(['water', 'tips'])
    })
  })

  it('passes AbortSignal', async () => {
    const { wrapper } = createWrapper()
    renderHook(() => useWaterTips(), { wrapper })

    await waitFor(() => expect(mockGetWaterTips).toHaveBeenCalled())
    expect(mockGetWaterTips).toHaveBeenCalledWith(expect.any(AbortSignal))
  })
})
