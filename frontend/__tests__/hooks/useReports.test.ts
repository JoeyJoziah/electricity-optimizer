import { renderHook, waitFor } from '@testing-library/react'
import React, { ReactNode } from 'react'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import '@testing-library/jest-dom'

const mockGetOptimizationReport = jest.fn()

jest.mock('@/lib/api/reports', () => ({
  getOptimizationReport: (...args: unknown[]) => mockGetOptimizationReport(...args),
}))

import { useOptimizationReport } from '@/lib/hooks/useReports'

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

const mockReport = {
  state: 'CT',
  generated_at: '2026-01-01T00:00:00Z',
  utilities: [],
  total_monthly_spend: 150,
  total_annual_spend: 1800,
  savings_opportunities: [
    { utility_type: 'electricity', action: 'Switch supplier', monthly_savings: 150, annual_savings: 1800, difficulty: 'easy' as const },
  ],
  total_potential_monthly_savings: 250,
  total_potential_annual_savings: 3000,
  utility_count: 1,
}

describe('useOptimizationReport', () => {
  beforeEach(() => {
    jest.clearAllMocks()
    mockGetOptimizationReport.mockResolvedValue(mockReport)
  })

  it('fetches report when state provided', async () => {
    const { wrapper } = createWrapper()
    const { result } = renderHook(() => useOptimizationReport('CT'), { wrapper })

    await waitFor(() => expect(result.current.isSuccess).toBe(true))
    expect(result.current.data?.total_potential_monthly_savings).toBe(250)
  })

  it('is disabled when state is undefined', () => {
    const { wrapper } = createWrapper()
    const { result } = renderHook(() => useOptimizationReport(undefined), { wrapper })
    expect(result.current.fetchStatus).toBe('idle')
  })

  it('uses correct query key', async () => {
    const { wrapper, queryClient } = createWrapper()
    renderHook(() => useOptimizationReport('NY'), { wrapper })

    await waitFor(() => {
      const keys = queryClient.getQueryCache().getAll().map((q) => q.queryKey)
      expect(keys).toContainEqual(['reports', 'optimization', 'NY'])
    })
  })

  it('handles error', async () => {
    mockGetOptimizationReport.mockRejectedValue(new Error('Report generation failed'))
    const { wrapper } = createWrapper()
    const { result } = renderHook(() => useOptimizationReport('CT'), { wrapper })

    await waitFor(() => expect(result.current.isError).toBe(true))
    expect(result.current.error?.message).toBe('Report generation failed')
  })

  it('passes AbortSignal', async () => {
    const { wrapper } = createWrapper()
    renderHook(() => useOptimizationReport('CT'), { wrapper })

    await waitFor(() => expect(mockGetOptimizationReport).toHaveBeenCalled())
    expect(mockGetOptimizationReport).toHaveBeenCalledWith('CT', expect.any(AbortSignal))
  })
})
