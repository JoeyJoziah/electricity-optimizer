import { renderHook, waitFor, act } from '@testing-library/react'
import React, { ReactNode } from 'react'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import '@testing-library/jest-dom'

// --- Mocks ---

const mockGetOptimalSchedule = jest.fn()
const mockGetOptimizationResult = jest.fn()
const mockSaveAppliances = jest.fn()
const mockGetAppliances = jest.fn()
const mockCalculatePotentialSavings = jest.fn()

jest.mock('@/lib/api/optimization', () => ({
  getOptimalSchedule: (...args: unknown[]) => mockGetOptimalSchedule(...args),
  getOptimizationResult: (...args: unknown[]) =>
    mockGetOptimizationResult(...args),
  saveAppliances: (...args: unknown[]) => mockSaveAppliances(...args),
  getAppliances: (...args: unknown[]) => mockGetAppliances(...args),
  calculatePotentialSavings: (...args: unknown[]) =>
    mockCalculatePotentialSavings(...args),
}))

import {
  useOptimalSchedule,
  useOptimizationResult,
  useAppliances,
  useSaveAppliances,
  usePotentialSavings,
} from '@/lib/hooks/useOptimization'

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
      React.createElement(
        QueryClientProvider,
        { client: queryClient },
        children
      ),
  }
}

// --- Mock data ---

const mockAppliance = {
  id: 'app-1',
  name: 'Washing Machine',
  wattage: 500,
  averageUsageHours: 1.5,
  flexibleSchedule: true,
  preferredStartTime: '22:00',
  preferredEndTime: '06:00',
}

const mockScheduleResponse = {
  schedules: [
    {
      applianceId: 'app-1',
      startTime: '2026-02-25T02:00:00Z',
      endTime: '2026-02-25T03:30:00Z',
      estimatedCost: 0.12,
    },
  ],
  totalSavings: 0.15,
  totalCost: 0.12,
}

const mockOptimizationResult = {
  date: '2026-02-25',
  region: 'us_ct',
  optimalHours: [2, 3, 4],
  peakHours: [17, 18, 19],
  estimatedSavings: 1.2,
}

const mockAppliancesResponse = {
  appliances: [mockAppliance],
}

const mockSavingsResponse = {
  dailySavings: 0.15,
  weeklySavings: 1.05,
  monthlySavings: 4.5,
  annualSavings: 54.75,
}

// ==========================================================================
// useOptimalSchedule
// ==========================================================================
describe('useOptimalSchedule', () => {
  beforeEach(() => {
    jest.clearAllMocks()
    mockGetOptimalSchedule.mockResolvedValue(mockScheduleResponse)
  })

  it('fetches optimal schedule when appliances are provided', async () => {
    const { wrapper } = createWrapper()

    const request = {
      appliances: [mockAppliance],
      region: 'us_ct',
      date: '2026-02-25',
    }

    const { result } = renderHook(() => useOptimalSchedule(request), {
      wrapper,
    })

    await waitFor(() => {
      expect(result.current.isSuccess).toBe(true)
    })

    expect(result.current.data).toEqual(mockScheduleResponse)
    expect(mockGetOptimalSchedule).toHaveBeenCalledWith(request)
  })

  it('is disabled when appliances array is empty', () => {
    const { wrapper } = createWrapper()

    const request = {
      appliances: [] as typeof mockAppliance[],
      region: 'us_ct',
    }

    const { result } = renderHook(() => useOptimalSchedule(request), {
      wrapper,
    })

    expect(result.current.fetchStatus).toBe('idle')
    expect(mockGetOptimalSchedule).not.toHaveBeenCalled()
  })

  it('uses correct query key including request', async () => {
    const { wrapper, queryClient } = createWrapper()

    const request = {
      appliances: [mockAppliance],
      region: 'us_ct',
    }

    renderHook(() => useOptimalSchedule(request), { wrapper })

    await waitFor(() => {
      const queries = queryClient.getQueryCache().getAll()
      const keys = queries.map((q) => q.queryKey)
      expect(keys).toContainEqual(['optimization', 'schedule', request])
    })
  })

  it('handles API error', async () => {
    mockGetOptimalSchedule.mockRejectedValue(
      new Error('Schedule unavailable')
    )

    const { wrapper } = createWrapper()

    const request = { appliances: [mockAppliance] }

    const { result } = renderHook(() => useOptimalSchedule(request), {
      wrapper,
    })

    await waitFor(() => {
      expect(result.current.isError).toBe(true)
    })

    expect(result.current.error?.message).toBe('Schedule unavailable')
  })
})

// ==========================================================================
// useOptimizationResult
// ==========================================================================
describe('useOptimizationResult', () => {
  beforeEach(() => {
    jest.clearAllMocks()
    mockGetOptimizationResult.mockResolvedValue(mockOptimizationResult)
  })

  it('fetches optimization result for a date', async () => {
    const { wrapper } = createWrapper()

    const { result } = renderHook(
      () => useOptimizationResult('2026-02-25', 'us_ct'),
      { wrapper }
    )

    await waitFor(() => {
      expect(result.current.isSuccess).toBe(true)
    })

    expect(result.current.data).toEqual(mockOptimizationResult)
    expect(mockGetOptimizationResult).toHaveBeenCalledWith(
      '2026-02-25',
      'us_ct'
    )
  })

  it('passes region explicitly', async () => {
    const { wrapper } = createWrapper()

    renderHook(() => useOptimizationResult('2026-02-25', 'us_ny'), { wrapper })

    await waitFor(() => {
      expect(mockGetOptimizationResult).toHaveBeenCalledWith(
        '2026-02-25',
        'us_ny'
      )
    })
  })

  it('is disabled when date is empty', () => {
    const { wrapper } = createWrapper()

    const { result } = renderHook(() => useOptimizationResult(''), { wrapper })

    expect(result.current.fetchStatus).toBe('idle')
    expect(mockGetOptimizationResult).not.toHaveBeenCalled()
  })

  it('uses correct query key', async () => {
    const { wrapper, queryClient } = createWrapper()

    renderHook(() => useOptimizationResult('2026-02-25', 'us_ny'), { wrapper })

    await waitFor(() => {
      const queries = queryClient.getQueryCache().getAll()
      const keys = queries.map((q) => q.queryKey)
      expect(keys).toContainEqual([
        'optimization',
        'result',
        '2026-02-25',
        'us_ny',
      ])
    })
  })
})

// ==========================================================================
// useAppliances
// ==========================================================================
describe('useAppliances', () => {
  beforeEach(() => {
    jest.clearAllMocks()
    mockGetAppliances.mockResolvedValue(mockAppliancesResponse)
  })

  it('fetches saved appliances', async () => {
    const { wrapper } = createWrapper()

    const { result } = renderHook(() => useAppliances(), { wrapper })

    await waitFor(() => {
      expect(result.current.isSuccess).toBe(true)
    })

    expect(result.current.data).toEqual(mockAppliancesResponse)
    expect(result.current.data?.appliances).toHaveLength(1)
    expect(result.current.data?.appliances[0].name).toBe('Washing Machine')
    expect(mockGetAppliances).toHaveBeenCalled()
  })

  it('uses correct query key', async () => {
    const { wrapper, queryClient } = createWrapper()

    renderHook(() => useAppliances(), { wrapper })

    await waitFor(() => {
      const queries = queryClient.getQueryCache().getAll()
      const keys = queries.map((q) => q.queryKey)
      expect(keys).toContainEqual(['appliances'])
    })
  })

  it('handles error', async () => {
    mockGetAppliances.mockRejectedValue(new Error('Not authenticated'))

    const { wrapper } = createWrapper()

    const { result } = renderHook(() => useAppliances(), { wrapper })

    await waitFor(() => {
      expect(result.current.isError).toBe(true)
    })

    expect(result.current.error?.message).toBe('Not authenticated')
  })
})

// ==========================================================================
// useSaveAppliances
// ==========================================================================
describe('useSaveAppliances', () => {
  beforeEach(() => {
    jest.clearAllMocks()
    mockSaveAppliances.mockResolvedValue({ success: true })
  })

  it('saves appliances and invalidates queries', async () => {
    const { wrapper, queryClient } = createWrapper()
    const invalidateSpy = jest.spyOn(queryClient, 'invalidateQueries')

    const { result } = renderHook(() => useSaveAppliances(), { wrapper })

    await act(async () => {
      await result.current.mutateAsync([mockAppliance])
    })

    expect(mockSaveAppliances).toHaveBeenCalledWith([mockAppliance])
    expect(invalidateSpy).toHaveBeenCalledWith(
      expect.objectContaining({ queryKey: ['appliances'] })
    )
    expect(invalidateSpy).toHaveBeenCalledWith(
      expect.objectContaining({ queryKey: ['optimization'] })
    )
  })

  it('handles save failure', async () => {
    mockSaveAppliances.mockRejectedValue(new Error('Save failed'))

    const { wrapper } = createWrapper()

    const { result } = renderHook(() => useSaveAppliances(), { wrapper })

    await expect(
      act(async () => {
        await result.current.mutateAsync([mockAppliance])
      })
    ).rejects.toThrow('Save failed')
  })
})

// ==========================================================================
// usePotentialSavings
// ==========================================================================
describe('usePotentialSavings', () => {
  beforeEach(() => {
    jest.clearAllMocks()
    mockCalculatePotentialSavings.mockResolvedValue(mockSavingsResponse)
  })

  it('calculates potential savings', async () => {
    const { wrapper } = createWrapper()

    const { result } = renderHook(
      () => usePotentialSavings([mockAppliance], 'us_ct'),
      { wrapper }
    )

    await waitFor(() => {
      expect(result.current.isSuccess).toBe(true)
    })

    expect(result.current.data).toEqual(mockSavingsResponse)
    expect(result.current.data?.annualSavings).toBe(54.75)
    expect(mockCalculatePotentialSavings).toHaveBeenCalledWith(
      [mockAppliance],
      'us_ct'
    )
  })

  it('passes region explicitly', async () => {
    const { wrapper } = createWrapper()

    renderHook(() => usePotentialSavings([mockAppliance], 'us_ny'), { wrapper })

    await waitFor(() => {
      expect(mockCalculatePotentialSavings).toHaveBeenCalledWith(
        [mockAppliance],
        'us_ny'
      )
    })
  })

  it('is disabled when appliances array is empty', () => {
    const { wrapper } = createWrapper()

    const { result } = renderHook(() => usePotentialSavings([], 'us_ct'), { wrapper })

    expect(result.current.fetchStatus).toBe('idle')
    expect(mockCalculatePotentialSavings).not.toHaveBeenCalled()
  })

  it('uses correct query key', async () => {
    const { wrapper, queryClient } = createWrapper()

    renderHook(() => usePotentialSavings([mockAppliance], 'us_ny'), { wrapper })

    await waitFor(() => {
      const queries = queryClient.getQueryCache().getAll()
      const keys = queries.map((q) => q.queryKey)
      expect(keys).toContainEqual([
        'potential-savings',
        [mockAppliance],
        'us_ny',
      ])
    })
  })

  it('handles calculation error', async () => {
    mockCalculatePotentialSavings.mockRejectedValue(
      new Error('Calculation failed')
    )

    const { wrapper } = createWrapper()

    const { result } = renderHook(
      () => usePotentialSavings([mockAppliance], 'us_ct'),
      { wrapper }
    )

    await waitFor(() => {
      expect(result.current.isError).toBe(true)
    })

    expect(result.current.error?.message).toBe('Calculation failed')
  })
})
