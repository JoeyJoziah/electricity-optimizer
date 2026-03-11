import { renderHook, waitFor } from '@testing-library/react'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { useUtilityDiscovery, useUtilityCompletion } from '@/lib/hooks/useUtilityDiscovery'
import '@testing-library/jest-dom'
import React from 'react'

const mockDiscoverUtilities = jest.fn()
const mockGetUtilityCompletion = jest.fn()

jest.mock('@/lib/api/utility-discovery', () => ({
  discoverUtilities: (...args: unknown[]) => mockDiscoverUtilities(...args),
  getUtilityCompletion: (...args: unknown[]) => mockGetUtilityCompletion(...args),
}))

const mockDiscoveryData = {
  state: 'NY',
  count: 4,
  utilities: [
    { utility_type: 'electricity', label: 'Electricity', status: 'deregulated', description: 'Choose your supplier.' },
    { utility_type: 'natural_gas', label: 'Natural Gas', status: 'deregulated', description: 'Compare gas.' },
    { utility_type: 'heating_oil', label: 'Heating Oil', status: 'available', description: 'Compare oil.' },
    { utility_type: 'community_solar', label: 'Community Solar', status: 'available', description: 'Browse solar.' },
  ],
}

const mockCompletionData = {
  state: 'NY',
  tracked: 1,
  available: 4,
  percent: 25,
  missing: [
    { utility_type: 'natural_gas', label: 'Natural Gas', status: 'deregulated', description: 'Compare gas.' },
    { utility_type: 'heating_oil', label: 'Heating Oil', status: 'available', description: 'Compare oil.' },
    { utility_type: 'community_solar', label: 'Community Solar', status: 'available', description: 'Browse solar.' },
  ],
}

describe('useUtilityDiscovery hooks', () => {
  let queryClient: QueryClient

  beforeEach(() => {
    queryClient = new QueryClient({
      defaultOptions: { queries: { retry: false, gcTime: 0 } },
    })
    mockDiscoverUtilities.mockResolvedValue(mockDiscoveryData)
    mockGetUtilityCompletion.mockResolvedValue(mockCompletionData)
  })

  afterEach(() => {
    queryClient.clear()
    jest.clearAllMocks()
  })

  const wrapper = ({ children }: { children: React.ReactNode }) => (
    <QueryClientProvider client={queryClient}>{children}</QueryClientProvider>
  )

  it('useUtilityDiscovery returns discovered utilities', async () => {
    const { result } = renderHook(() => useUtilityDiscovery('NY'), { wrapper })

    await waitFor(() => expect(result.current.isSuccess).toBe(true))

    expect(result.current.data?.count).toBe(4)
    expect(result.current.data?.utilities).toHaveLength(4)
    expect(mockDiscoverUtilities).toHaveBeenCalledWith('NY')
  })

  it('useUtilityDiscovery(null) is disabled', () => {
    const { result } = renderHook(() => useUtilityDiscovery(null), { wrapper })
    expect(result.current.fetchStatus).toBe('idle')
    expect(mockDiscoverUtilities).not.toHaveBeenCalled()
  })

  it('useUtilityCompletion returns completion status', async () => {
    const { result } = renderHook(
      () => useUtilityCompletion('NY', ['electricity']),
      { wrapper }
    )

    await waitFor(() => expect(result.current.isSuccess).toBe(true))

    expect(result.current.data?.tracked).toBe(1)
    expect(result.current.data?.available).toBe(4)
    expect(result.current.data?.percent).toBe(25)
    expect(result.current.data?.missing).toHaveLength(3)
  })

  it('useUtilityCompletion(null, []) is disabled', () => {
    const { result } = renderHook(
      () => useUtilityCompletion(null, []),
      { wrapper }
    )
    expect(result.current.fetchStatus).toBe('idle')
  })

  it('useUtilityCompletion(state, []) is disabled when tracked is empty', () => {
    const { result } = renderHook(
      () => useUtilityCompletion('NY', []),
      { wrapper }
    )
    expect(result.current.fetchStatus).toBe('idle')
  })

  it('hooks use correct query keys', async () => {
    renderHook(() => useUtilityDiscovery('NY'), { wrapper })
    renderHook(() => useUtilityCompletion('NY', ['electricity']), { wrapper })

    await waitFor(() => {
      const queries = queryClient.getQueryCache().getAll()
      const keys = queries.map((q) => q.queryKey)

      expect(keys).toContainEqual(['utility-discovery', 'NY'])
      expect(keys).toContainEqual(['utility-completion', 'NY', 'electricity'])
    })
  })

  it('handles API errors', async () => {
    mockDiscoverUtilities.mockRejectedValue(new Error('Discovery API error'))

    const { result } = renderHook(() => useUtilityDiscovery('NY'), { wrapper })

    await waitFor(() => expect(result.current.isError).toBe(true))
    expect(result.current.error?.message).toBe('Discovery API error')
  })
})
