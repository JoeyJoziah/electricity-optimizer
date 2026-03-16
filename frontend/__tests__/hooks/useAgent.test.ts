import { renderHook, waitFor, act } from '@testing-library/react'
import React, { ReactNode } from 'react'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import '@testing-library/jest-dom'

// --- Mocks ---

const mockQueryAgent = jest.fn()
const mockGetAgentUsage = jest.fn()

jest.mock('@/lib/api/agent', () => ({
  queryAgent: (...args: unknown[]) => mockQueryAgent(...args),
  getAgentUsage: (...args: unknown[]) => mockGetAgentUsage(...args),
}))

import { useAgentQuery, useAgentStatus } from '@/lib/hooks/useAgent'

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

describe('useAgentStatus', () => {
  beforeEach(() => {
    jest.clearAllMocks()
    mockGetAgentUsage.mockResolvedValue({
      used: 5,
      limit: 20,
      remaining: 15,
      tier: 'pro',
    })
  })

  it('fetches usage data', async () => {
    const { wrapper } = createWrapper()
    const { result } = renderHook(() => useAgentStatus(), { wrapper })

    await waitFor(() => {
      expect(result.current.isSuccess).toBe(true)
    })

    expect(result.current.data).toEqual({
      used: 5,
      limit: 20,
      remaining: 15,
      tier: 'pro',
    })
  })

  it('uses correct query key', async () => {
    const { wrapper, queryClient } = createWrapper()
    renderHook(() => useAgentStatus(), { wrapper })

    await waitFor(() => {
      const keys = queryClient.getQueryCache().getAll().map((q) => q.queryKey)
      expect(keys).toContainEqual(['agent', 'usage'])
    })
  })

  it('handles error', async () => {
    mockGetAgentUsage.mockRejectedValue(new Error('Unauthorized'))
    const { wrapper } = createWrapper()
    const { result } = renderHook(() => useAgentStatus(), { wrapper })

    await waitFor(() => {
      expect(result.current.isError).toBe(true)
    })
    expect(result.current.error?.message).toBe('Unauthorized')
  })
})

describe('useAgentQuery', () => {
  beforeEach(() => {
    jest.clearAllMocks()
  })

  it('starts with empty state', () => {
    const { result } = renderHook(() => useAgentQuery())

    expect(result.current.messages).toEqual([])
    expect(result.current.isStreaming).toBe(false)
    expect(result.current.error).toBeNull()
  })

  it('reset clears messages', () => {
    const { result } = renderHook(() => useAgentQuery())

    act(() => {
      result.current.reset()
    })

    expect(result.current.messages).toEqual([])
    expect(result.current.error).toBeNull()
  })
})
