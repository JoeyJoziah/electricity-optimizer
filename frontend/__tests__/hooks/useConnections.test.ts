import { renderHook, waitFor } from '@testing-library/react'
import React, { ReactNode } from 'react'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import '@testing-library/jest-dom'

const mockGet = jest.fn()

jest.mock('@/lib/api/client', () => ({
  apiClient: {
    get: (...args: unknown[]) => mockGet(...args),
  },
  ApiClientError: class ApiClientError extends Error {
    status: number
    constructor(message: string, status: number) {
      super(message)
      this.status = status
    }
  },
}))

import { useConnections } from '@/lib/hooks/useConnections'

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

const mockConnectionsResponse = {
  connections: [
    {
      id: 'conn-1',
      method: 'direct',
      connection_type: 'direct',
      status: 'active',
      supplier_name: 'Eversource',
      email_provider: null,
      last_sync_at: '2026-03-10T10:00:00Z',
      last_sync_error: null,
      current_rate: 0.18,
      created_at: '2026-03-01T10:00:00Z',
      label: null,
    },
  ],
}

describe('useConnections', () => {
  beforeEach(() => {
    jest.clearAllMocks()
    mockGet.mockResolvedValue(mockConnectionsResponse)
  })

  it('fetches connections', async () => {
    const { wrapper } = createWrapper()
    const { result } = renderHook(() => useConnections(), { wrapper })

    await waitFor(() => expect(result.current.isSuccess).toBe(true))

    expect(result.current.data?.connections).toHaveLength(1)
    expect(result.current.data?.connections[0].supplier_name).toBe('Eversource')
  })

  it('maps connection_type to method', async () => {
    mockGet.mockResolvedValue({
      connections: [{
        id: 'conn-2',
        method: 'old_method',
        connection_type: 'email_import',
        status: 'active',
        supplier_name: null,
        email_provider: 'gmail',
        last_sync_at: null,
        last_sync_error: null,
        current_rate: null,
        created_at: '2026-03-01T10:00:00Z',
      }],
    })

    const { wrapper } = createWrapper()
    const { result } = renderHook(() => useConnections(), { wrapper })

    await waitFor(() => expect(result.current.isSuccess).toBe(true))

    // connection_type should override method
    expect(result.current.data?.connections[0].method).toBe('email_import')
  })

  it('uses correct query key', async () => {
    const { wrapper, queryClient } = createWrapper()
    renderHook(() => useConnections(), { wrapper })

    await waitFor(() => {
      const keys = queryClient.getQueryCache().getAll().map((q) => q.queryKey)
      expect(keys).toContainEqual(['connections'])
    })
  })

  it('handles 403 error with upgrade message', async () => {
    const { ApiClientError } = jest.requireMock('@/lib/api/client')
    mockGet.mockRejectedValue(new ApiClientError('Forbidden', 403))

    const { wrapper } = createWrapper()
    const { result } = renderHook(() => useConnections(), { wrapper })

    await waitFor(() => expect(result.current.isError).toBe(true))
    expect(result.current.error?.message).toBe('upgrade')
  })

  it('handles generic network error', async () => {
    mockGet.mockRejectedValue(new Error('Network error'))

    const { wrapper } = createWrapper()
    const { result } = renderHook(() => useConnections(), { wrapper })

    await waitFor(() => expect(result.current.isError).toBe(true))
    expect(result.current.error?.message).toBe('Network error')
  })
})
