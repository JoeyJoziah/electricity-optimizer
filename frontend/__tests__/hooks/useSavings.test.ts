import { renderHook, waitFor } from '@testing-library/react'
import React, { ReactNode } from 'react'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import '@testing-library/jest-dom'

// --- Mocks ---

const mockApiClientGet = jest.fn()

jest.mock('@/lib/api/client', () => ({
  apiClient: {
    get: (...args: unknown[]) => mockApiClientGet(...args),
  },
}))

import { useSavingsSummary, SavingsSummary } from '@/lib/hooks/useSavings'

// --- Helpers ---

function createWrapper() {
  const queryClient = new QueryClient({
    defaultOptions: {
      queries: { retry: false, gcTime: 0 },
    },
  })
  return {
    queryClient,
    wrapper: ({ children }: { children: ReactNode }) =>
      React.createElement(QueryClientProvider, { client: queryClient }, children),
  }
}

// --- Mock data ---

const mockSavingsSummary: SavingsSummary = {
  total: 124.50,
  weekly: 8.75,
  monthly: 35.00,
  streak_days: 14,
  currency: 'USD',
}

const mockSavingsSummaryGBP: SavingsSummary = {
  total: 98.20,
  weekly: 6.90,
  monthly: 27.60,
  streak_days: 7,
  currency: 'GBP',
}

// ==========================================================================
// useSavingsSummary
// ==========================================================================
describe('useSavingsSummary', () => {
  beforeEach(() => {
    jest.clearAllMocks()
    mockApiClientGet.mockResolvedValue(mockSavingsSummary)
  })

  it('fetches the savings summary successfully', async () => {
    const { wrapper } = createWrapper()

    const { result } = renderHook(() => useSavingsSummary(), { wrapper })

    await waitFor(() => {
      expect(result.current.isSuccess).toBe(true)
    })

    expect(result.current.data).toEqual(mockSavingsSummary)
    expect(mockApiClientGet).toHaveBeenCalledWith('/savings/summary', undefined, expect.objectContaining({ signal: expect.anything() }))
  })

  it('returns loading state before data arrives', () => {
    mockApiClientGet.mockReturnValue(new Promise(() => {}))

    const { wrapper } = createWrapper()
    const { result } = renderHook(() => useSavingsSummary(), { wrapper })

    expect(result.current.isLoading).toBe(true)
    expect(result.current.data).toBeUndefined()
  })

  it('returns all savings fields correctly', async () => {
    const { wrapper } = createWrapper()

    const { result } = renderHook(() => useSavingsSummary(), { wrapper })

    await waitFor(() => {
      expect(result.current.isSuccess).toBe(true)
    })

    expect(result.current.data?.total).toBe(124.50)
    expect(result.current.data?.weekly).toBe(8.75)
    expect(result.current.data?.monthly).toBe(35.00)
    expect(result.current.data?.streak_days).toBe(14)
    expect(result.current.data?.currency).toBe('USD')
  })

  it('returns savings data with GBP currency', async () => {
    mockApiClientGet.mockResolvedValue(mockSavingsSummaryGBP)

    const { wrapper } = createWrapper()

    const { result } = renderHook(() => useSavingsSummary(), { wrapper })

    await waitFor(() => {
      expect(result.current.isSuccess).toBe(true)
    })

    expect(result.current.data?.currency).toBe('GBP')
    expect(result.current.data?.total).toBe(98.20)
  })

  it('uses correct query key', async () => {
    const { wrapper, queryClient } = createWrapper()

    renderHook(() => useSavingsSummary(), { wrapper })

    await waitFor(() => {
      const keys = queryClient.getQueryCache().getAll().map((q) => q.queryKey)
      expect(keys).toContainEqual(['savings', 'summary'])
    })
  })

  it('handles 401 unauthorized error gracefully (unauthenticated user)', async () => {
    const authError = new Error('Unauthorized')
    // Hook uses retry: 1, so reject both the initial attempt and the retry
    mockApiClientGet.mockRejectedValue(authError)

    // Use retry: 0 at the QueryClient level to keep tests fast; the hook's
    // retry: 1 will override this, but both attempts will reject anyway.
    const queryClient = new QueryClient({
      defaultOptions: {
        queries: { retry: 0, retryDelay: 0, gcTime: 0 },
      },
    })
    const wrapper = ({ children }: { children: ReactNode }) =>
      React.createElement(QueryClientProvider, { client: queryClient }, children)

    const { result } = renderHook(() => useSavingsSummary(), { wrapper })

    await waitFor(
      () => {
        expect(result.current.isError).toBe(true)
      },
      { timeout: 5000 }
    )

    expect(result.current.data).toBeUndefined()
    expect(result.current.error?.message).toBe('Unauthorized')

    queryClient.clear()
  })

  it('handles network error', async () => {
    mockApiClientGet.mockRejectedValue(new Error('Network Error'))

    const queryClient = new QueryClient({
      defaultOptions: {
        queries: { retry: 0, retryDelay: 0, gcTime: 0 },
      },
    })
    const wrapper = ({ children }: { children: ReactNode }) =>
      React.createElement(QueryClientProvider, { client: queryClient }, children)

    const { result } = renderHook(() => useSavingsSummary(), { wrapper })

    await waitFor(
      () => {
        expect(result.current.isError).toBe(true)
      },
      { timeout: 5000 }
    )

    expect(result.current.error?.message).toBe('Network Error')

    queryClient.clear()
  })

  it('retries once on failure per retry: 1 setting', async () => {
    // First call fails, second succeeds — the hook has retry: 1
    mockApiClientGet
      .mockRejectedValueOnce(new Error('Transient error'))
      .mockResolvedValueOnce(mockSavingsSummary)

    const { wrapper: _wrapper } = createWrapper()
    // Override the wrapper to use retry: 1 (matching hook's own setting)
    const queryClient = new QueryClient({
      defaultOptions: {
        queries: { retry: 1, retryDelay: 0, gcTime: 0 },
      },
    })
    const retryWrapper = ({ children }: { children: ReactNode }) =>
      React.createElement(QueryClientProvider, { client: queryClient }, children)

    const { result } = renderHook(() => useSavingsSummary(), {
      wrapper: retryWrapper,
    })

    await waitFor(() => {
      expect(result.current.isSuccess).toBe(true)
    })

    expect(result.current.data).toEqual(mockSavingsSummary)
    expect(mockApiClientGet).toHaveBeenCalledTimes(2)

    queryClient.clear()
  })

  it('correctly passes endpoint path to apiClient.get', async () => {
    const { wrapper } = createWrapper()

    renderHook(() => useSavingsSummary(), { wrapper })

    await waitFor(() => {
      expect(mockApiClientGet).toHaveBeenCalledWith('/savings/summary', undefined, expect.objectContaining({ signal: expect.anything() }))
    })

    // Verify called once with 3 args (endpoint, undefined params, { signal })
    expect(mockApiClientGet).toHaveBeenCalledTimes(1)
    expect(mockApiClientGet.mock.calls[0]).toHaveLength(3)
  })

  it('returns zero values when all savings are zero', async () => {
    const zeroSavings: SavingsSummary = {
      total: 0,
      weekly: 0,
      monthly: 0,
      streak_days: 0,
      currency: 'USD',
    }
    mockApiClientGet.mockResolvedValue(zeroSavings)

    const { wrapper } = createWrapper()

    const { result } = renderHook(() => useSavingsSummary(), { wrapper })

    await waitFor(() => {
      expect(result.current.isSuccess).toBe(true)
    })

    expect(result.current.data?.total).toBe(0)
    expect(result.current.data?.streak_days).toBe(0)
  })

  it('does not refetch on re-render within staleTime window', async () => {
    const { wrapper } = createWrapper()

    const { rerender } = renderHook(() => useSavingsSummary(), { wrapper })

    await waitFor(() => {
      expect(mockApiClientGet).toHaveBeenCalledTimes(1)
    })

    // Re-render should not trigger another fetch within staleTime
    rerender()

    expect(mockApiClientGet).toHaveBeenCalledTimes(1)
  })
})
