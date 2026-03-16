import { renderHook, waitFor } from '@testing-library/react'
import React, { ReactNode } from 'react'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import '@testing-library/jest-dom'

const mockGetCombinedSavings = jest.fn()

jest.mock('@/lib/api/savings', () => ({
  getCombinedSavings: (...args: unknown[]) => mockGetCombinedSavings(...args),
}))

import { useCombinedSavings } from '@/lib/hooks/useCombinedSavings'

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

const mockResponse = {
  total_monthly_savings: 42.5,
  breakdown: [
    { utility_type: 'electricity', monthly_savings: 30 },
    { utility_type: 'natural_gas', monthly_savings: 12.5 },
  ],
  savings_rank_pct: 85,
}

describe('useCombinedSavings', () => {
  beforeEach(() => {
    jest.clearAllMocks()
    mockGetCombinedSavings.mockResolvedValue(mockResponse)
  })

  it('fetches combined savings', async () => {
    const { wrapper } = createWrapper()
    const { result } = renderHook(() => useCombinedSavings(), { wrapper })

    await waitFor(() => expect(result.current.isSuccess).toBe(true))

    expect(result.current.data?.total_monthly_savings).toBe(42.5)
    expect(result.current.data?.breakdown).toHaveLength(2)
  })

  it('uses correct query key', async () => {
    const { wrapper, queryClient } = createWrapper()
    renderHook(() => useCombinedSavings(), { wrapper })

    await waitFor(() => {
      const keys = queryClient.getQueryCache().getAll().map((q) => q.queryKey)
      expect(keys).toContainEqual(['savings', 'combined'])
    })
  })

  it('handles error', async () => {
    mockGetCombinedSavings.mockRejectedValue(new Error('Service unavailable'))
    const { wrapper } = createWrapper()
    const { result } = renderHook(() => useCombinedSavings(), { wrapper })

    await waitFor(() => expect(result.current.isError).toBe(true))
    expect(result.current.error?.message).toBe('Service unavailable')
  })

  it('passes AbortSignal to API function', async () => {
    const { wrapper } = createWrapper()
    renderHook(() => useCombinedSavings(), { wrapper })

    await waitFor(() => expect(mockGetCombinedSavings).toHaveBeenCalled())
    expect(mockGetCombinedSavings).toHaveBeenCalledWith(expect.any(AbortSignal))
  })
})
