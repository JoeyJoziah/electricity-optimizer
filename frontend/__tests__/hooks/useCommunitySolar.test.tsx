import { renderHook, waitFor } from '@testing-library/react'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import {
  useCommunitySolarPrograms,
  useCommunitySolarSavings,
  useCommunitySolarProgram,
  useCommunitySolarStates,
} from '@/lib/hooks/useCommunitySolar'
import '@testing-library/jest-dom'
import React from 'react'

const mockGetPrograms = jest.fn()
const mockGetSavings = jest.fn()
const mockGetProgram = jest.fn()
const mockGetStates = jest.fn()

jest.mock('@/lib/api/community-solar', () => ({
  getCommunitySolarPrograms: (...args: unknown[]) => mockGetPrograms(...args),
  getCommunitySolarSavings: (...args: unknown[]) => mockGetSavings(...args),
  getCommunitySolarProgram: (...args: unknown[]) => mockGetProgram(...args),
  getCommunitySolarStates: (...args: unknown[]) => mockGetStates(...args),
}))

const mockProgramsData = {
  state: 'NY',
  count: 1,
  programs: [
    {
      id: '1',
      state: 'NY',
      program_name: 'NY Community Solar',
      provider: 'Nexamp',
      savings_percent: '10.00',
      capacity_kw: '5000.00',
      spots_available: 150,
      enrollment_url: 'https://example.com',
      enrollment_status: 'open',
      description: 'Save on your bill.',
      min_bill_amount: '50.00',
      contract_months: 12,
      updated_at: '2026-03-10T00:00:00Z',
    },
  ],
}

const mockSavingsData = {
  current_monthly_bill: '150.00',
  savings_percent: '10',
  monthly_savings: '15.00',
  annual_savings: '180.00',
  five_year_savings: '900.00',
  new_monthly_bill: '135.00',
}

const mockStatesData = {
  total_states: 2,
  states: [
    { state: 'NY', program_count: 3 },
    { state: 'MA', program_count: 2 },
  ],
}

describe('useCommunitySolar hooks', () => {
  let queryClient: QueryClient

  beforeEach(() => {
    queryClient = new QueryClient({
      defaultOptions: { queries: { retry: false, gcTime: 0 } },
    })

    mockGetPrograms.mockResolvedValue(mockProgramsData)
    mockGetSavings.mockResolvedValue(mockSavingsData)
    mockGetProgram.mockResolvedValue(mockProgramsData.programs[0])
    mockGetStates.mockResolvedValue(mockStatesData)
  })

  afterEach(() => {
    queryClient.clear()
    jest.clearAllMocks()
  })

  const wrapper = ({ children }: { children: React.ReactNode }) => (
    <QueryClientProvider client={queryClient}>{children}</QueryClientProvider>
  )

  it('useCommunitySolarPrograms returns programs', async () => {
    const { result } = renderHook(() => useCommunitySolarPrograms('NY'), { wrapper })

    await waitFor(() => expect(result.current.isSuccess).toBe(true))

    expect(result.current.data?.count).toBe(1)
    expect(result.current.data?.programs[0].program_name).toBe('NY Community Solar')
    expect(mockGetPrograms).toHaveBeenCalledWith({ state: 'NY', enrollment_status: undefined }, expect.anything())
  })

  it('useCommunitySolarPrograms(null) is disabled', () => {
    const { result } = renderHook(() => useCommunitySolarPrograms(null), { wrapper })
    expect(result.current.fetchStatus).toBe('idle')
    expect(mockGetPrograms).not.toHaveBeenCalled()
  })

  it('useCommunitySolarPrograms passes enrollment filter', async () => {
    const { result } = renderHook(
      () => useCommunitySolarPrograms('NY', 'open'),
      { wrapper }
    )

    await waitFor(() => expect(result.current.isSuccess).toBe(true))
    expect(mockGetPrograms).toHaveBeenCalledWith({ state: 'NY', enrollment_status: 'open' }, expect.anything())
  })

  it('useCommunitySolarSavings returns savings data', async () => {
    const { result } = renderHook(
      () => useCommunitySolarSavings('150', '10'),
      { wrapper }
    )

    await waitFor(() => expect(result.current.isSuccess).toBe(true))

    expect(result.current.data?.monthly_savings).toBe('15.00')
    expect(result.current.data?.annual_savings).toBe('180.00')
  })

  it('useCommunitySolarSavings(null, null) is disabled', () => {
    const { result } = renderHook(
      () => useCommunitySolarSavings(null, null),
      { wrapper }
    )
    expect(result.current.fetchStatus).toBe('idle')
  })

  it('useCommunitySolarProgram returns a single program', async () => {
    const { result } = renderHook(
      () => useCommunitySolarProgram('1'),
      { wrapper }
    )

    await waitFor(() => expect(result.current.isSuccess).toBe(true))
    expect(result.current.data?.program_name).toBe('NY Community Solar')
  })

  it('useCommunitySolarProgram(null) is disabled', () => {
    const { result } = renderHook(
      () => useCommunitySolarProgram(null),
      { wrapper }
    )
    expect(result.current.fetchStatus).toBe('idle')
  })

  it('useCommunitySolarStates returns states data', async () => {
    const { result } = renderHook(() => useCommunitySolarStates(), { wrapper })

    await waitFor(() => expect(result.current.isSuccess).toBe(true))

    expect(result.current.data?.total_states).toBe(2)
    expect(result.current.data?.states[0].state).toBe('NY')
  })

  it('hooks use correct query keys', async () => {
    renderHook(() => useCommunitySolarPrograms('NY'), { wrapper })
    renderHook(() => useCommunitySolarSavings('150', '10'), { wrapper })
    renderHook(() => useCommunitySolarProgram('1'), { wrapper })
    renderHook(() => useCommunitySolarStates(), { wrapper })

    await waitFor(() => {
      const queries = queryClient.getQueryCache().getAll()
      const keys = queries.map((q) => q.queryKey)

      expect(keys).toContainEqual(['community-solar', 'programs', 'NY', undefined])
      expect(keys).toContainEqual(['community-solar', 'savings', '150', '10'])
      expect(keys).toContainEqual(['community-solar', 'program', '1'])
      expect(keys).toContainEqual(['community-solar', 'states'])
    })
  })

  it('handles API errors', async () => {
    mockGetPrograms.mockRejectedValue(new Error('Solar API error'))

    const { result } = renderHook(() => useCommunitySolarPrograms('NY'), { wrapper })

    await waitFor(() => expect(result.current.isError).toBe(true))
    expect(result.current.error?.message).toBe('Solar API error')
  })
})
