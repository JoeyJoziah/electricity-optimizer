import { renderHook, waitFor } from '@testing-library/react'
import React, { ReactNode } from 'react'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import '@testing-library/jest-dom'

const mockExportRates = jest.fn()
const mockGetExportTypes = jest.fn()

jest.mock('@/lib/api/export', () => ({
  exportRates: (...args: unknown[]) => mockExportRates(...args),
  getExportTypes: (...args: unknown[]) => mockGetExportTypes(...args),
}))

import { useExportRates, useExportTypes } from '@/lib/hooks/useExport'

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

describe('useExportRates', () => {
  beforeEach(() => {
    jest.clearAllMocks()
    mockExportRates.mockResolvedValue({
      format: 'json',
      data: [{ rate: 0.18 }],
      count: 1,
      utility_type: 'electricity',
    })
  })

  it('is disabled by default', () => {
    const { wrapper } = createWrapper()
    const { result } = renderHook(() => useExportRates('electricity', 'json', 'CT'), { wrapper })
    expect(result.current.fetchStatus).toBe('idle')
  })

  it('fetches when enabled', async () => {
    const { wrapper } = createWrapper()
    const { result } = renderHook(
      () => useExportRates('electricity', 'json', 'CT', true),
      { wrapper }
    )

    await waitFor(() => expect(result.current.isSuccess).toBe(true))
    expect(result.current.data?.count).toBe(1)
  })

  it('stays disabled when no utilityType even if enabled=true', () => {
    const { wrapper } = createWrapper()
    const { result } = renderHook(
      () => useExportRates(undefined, 'json', undefined, true),
      { wrapper }
    )
    expect(result.current.fetchStatus).toBe('idle')
  })

  it('uses correct query key', async () => {
    const { wrapper, queryClient } = createWrapper()
    renderHook(() => useExportRates('electricity', 'csv', 'NY', true), { wrapper })

    await waitFor(() => {
      const keys = queryClient.getQueryCache().getAll().map((q) => q.queryKey)
      expect(keys).toContainEqual(['export', 'rates', 'electricity', 'csv', 'NY'])
    })
  })

  it('handles error', async () => {
    mockExportRates.mockRejectedValue(new Error('Export failed'))
    const { wrapper } = createWrapper()
    const { result } = renderHook(
      () => useExportRates('electricity', 'json', 'CT', true),
      { wrapper }
    )

    await waitFor(() => expect(result.current.isError).toBe(true))
  })
})

describe('useExportTypes', () => {
  beforeEach(() => {
    jest.clearAllMocks()
    mockGetExportTypes.mockResolvedValue({
      supported_types: ['electricity', 'natural_gas'],
      formats: ['json', 'csv'],
      max_days: 365,
      max_rows: 10000,
    })
  })

  it('fetches export types', async () => {
    const { wrapper } = createWrapper()
    const { result } = renderHook(() => useExportTypes(), { wrapper })

    await waitFor(() => expect(result.current.isSuccess).toBe(true))
    expect(result.current.data?.supported_types).toContain('electricity')
  })

  it('uses correct query key', async () => {
    const { wrapper, queryClient } = createWrapper()
    renderHook(() => useExportTypes(), { wrapper })

    await waitFor(() => {
      const keys = queryClient.getQueryCache().getAll().map((q) => q.queryKey)
      expect(keys).toContainEqual(['export', 'types'])
    })
  })
})
