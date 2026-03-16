import { renderHook, waitFor } from '@testing-library/react'
import React, { ReactNode } from 'react'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import '@testing-library/jest-dom'

const mockDetectCCA = jest.fn()
const mockCompareCCARate = jest.fn()
const mockGetCCAInfo = jest.fn()
const mockListCCAPrograms = jest.fn()

jest.mock('@/lib/api/cca', () => ({
  detectCCA: (...args: unknown[]) => mockDetectCCA(...args),
  compareCCARate: (...args: unknown[]) => mockCompareCCARate(...args),
  getCCAInfo: (...args: unknown[]) => mockGetCCAInfo(...args),
  listCCAPrograms: (...args: unknown[]) => mockListCCAPrograms(...args),
}))

import { useCCADetect, useCCACompare, useCCAInfo, useCCAPrograms } from '@/lib/hooks/useCCA'

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

describe('useCCADetect', () => {
  beforeEach(() => {
    jest.clearAllMocks()
    mockDetectCCA.mockResolvedValue({ in_cca: true, program: { id: 'cca-1', program_name: 'Green CT' } })
  })

  it('fetches detection when zipCode provided', async () => {
    const { wrapper } = createWrapper()
    const { result } = renderHook(() => useCCADetect('06510'), { wrapper })

    await waitFor(() => expect(result.current.isSuccess).toBe(true))
    expect(result.current.data?.in_cca).toBe(true)
  })

  it('is disabled when no zipCode or state', () => {
    const { wrapper } = createWrapper()
    const { result } = renderHook(() => useCCADetect(), { wrapper })

    expect(result.current.fetchStatus).toBe('idle')
  })

  it('uses correct query key', async () => {
    const { wrapper, queryClient } = createWrapper()
    renderHook(() => useCCADetect('06510', 'CT'), { wrapper })

    await waitFor(() => {
      const keys = queryClient.getQueryCache().getAll().map((q) => q.queryKey)
      expect(keys).toContainEqual(['cca', 'detect', '06510', 'CT'])
    })
  })

  it('handles error', async () => {
    mockDetectCCA.mockRejectedValue(new Error('Not found'))
    const { wrapper } = createWrapper()
    const { result } = renderHook(() => useCCADetect('00000'), { wrapper })

    await waitFor(() => expect(result.current.isError).toBe(true))
    expect(result.current.error?.message).toBe('Not found')
  })
})

describe('useCCACompare', () => {
  beforeEach(() => {
    jest.clearAllMocks()
    mockCompareCCARate.mockResolvedValue({ is_cheaper: true, savings_per_kwh: 0.02 })
  })

  it('fetches comparison when both params provided', async () => {
    const { wrapper } = createWrapper()
    const { result } = renderHook(() => useCCACompare('cca-1', 0.18), { wrapper })

    await waitFor(() => expect(result.current.isSuccess).toBe(true))
    expect(result.current.data?.is_cheaper).toBe(true)
  })

  it('is disabled when ccaId missing', () => {
    const { wrapper } = createWrapper()
    const { result } = renderHook(() => useCCACompare(undefined, 0.18), { wrapper })
    expect(result.current.fetchStatus).toBe('idle')
  })

  it('is disabled when defaultRate is 0', () => {
    const { wrapper } = createWrapper()
    const { result } = renderHook(() => useCCACompare('cca-1', 0), { wrapper })
    expect(result.current.fetchStatus).toBe('idle')
  })
})

describe('useCCAInfo', () => {
  beforeEach(() => {
    jest.clearAllMocks()
    mockGetCCAInfo.mockResolvedValue({ id: 'cca-1', program_name: 'Green CT' })
  })

  it('fetches info when ccaId provided', async () => {
    const { wrapper } = createWrapper()
    const { result } = renderHook(() => useCCAInfo('cca-1'), { wrapper })

    await waitFor(() => expect(result.current.isSuccess).toBe(true))
    expect(result.current.data?.program_name).toBe('Green CT')
  })

  it('is disabled when no ccaId', () => {
    const { wrapper } = createWrapper()
    const { result } = renderHook(() => useCCAInfo(), { wrapper })
    expect(result.current.fetchStatus).toBe('idle')
  })
})

describe('useCCAPrograms', () => {
  beforeEach(() => {
    jest.clearAllMocks()
    mockListCCAPrograms.mockResolvedValue([{ id: 'cca-1' }, { id: 'cca-2' }])
  })

  it('fetches programs list', async () => {
    const { wrapper } = createWrapper()
    const { result } = renderHook(() => useCCAPrograms('CT'), { wrapper })

    await waitFor(() => expect(result.current.isSuccess).toBe(true))
    expect(result.current.data).toHaveLength(2)
  })

  it('uses correct query key', async () => {
    const { wrapper, queryClient } = createWrapper()
    renderHook(() => useCCAPrograms('NY'), { wrapper })

    await waitFor(() => {
      const keys = queryClient.getQueryCache().getAll().map((q) => q.queryKey)
      expect(keys).toContainEqual(['cca', 'programs', 'NY'])
    })
  })
})
