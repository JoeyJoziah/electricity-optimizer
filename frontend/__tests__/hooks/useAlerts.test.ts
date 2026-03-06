import { renderHook, waitFor, act } from '@testing-library/react'
import React, { ReactNode } from 'react'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import '@testing-library/jest-dom'

// --- Mocks ---

const mockGetAlerts = jest.fn()
const mockCreateAlert = jest.fn()
const mockUpdateAlert = jest.fn()
const mockDeleteAlert = jest.fn()
const mockGetAlertHistory = jest.fn()

jest.mock('@/lib/api/alerts', () => ({
  getAlerts: (...args: unknown[]) => mockGetAlerts(...args),
  createAlert: (...args: unknown[]) => mockCreateAlert(...args),
  updateAlert: (...args: unknown[]) => mockUpdateAlert(...args),
  deleteAlert: (...args: unknown[]) => mockDeleteAlert(...args),
  getAlertHistory: (...args: unknown[]) => mockGetAlertHistory(...args),
}))

import {
  useAlerts,
  useAlertHistory,
  useCreateAlert,
  useUpdateAlert,
  useDeleteAlert,
} from '@/lib/hooks/useAlerts'

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

const mockAlertsResponse = {
  alerts: [
    {
      id: 'alert-1',
      user_id: 'user-1',
      region: 'us_ct',
      currency: 'USD',
      price_below: 0.2,
      price_above: null,
      notify_optimal_windows: true,
      is_active: true,
      created_at: '2026-03-01T10:00:00Z',
      updated_at: '2026-03-01T10:00:00Z',
    },
    {
      id: 'alert-2',
      user_id: 'user-1',
      region: 'us_ny',
      currency: 'USD',
      price_below: null,
      price_above: 0.35,
      notify_optimal_windows: false,
      is_active: true,
      created_at: '2026-03-02T10:00:00Z',
      updated_at: '2026-03-02T10:00:00Z',
    },
  ],
  total: 2,
}

const mockHistoryResponse = {
  items: [
    {
      id: 'hist-1',
      user_id: 'user-1',
      alert_config_id: 'alert-1',
      alert_type: 'price_drop',
      current_price: 0.18,
      threshold: 0.2,
      region: 'us_ct',
      supplier: 'Eversource',
      currency: 'USD',
      optimal_window_start: null,
      optimal_window_end: null,
      estimated_savings: null,
      triggered_at: '2026-03-03T14:00:00Z',
      email_sent: true,
    },
  ],
  total: 1,
  page: 1,
  page_size: 20,
  pages: 1,
}

// ==========================================================================
// useAlerts
// ==========================================================================
describe('useAlerts', () => {
  beforeEach(() => {
    jest.clearAllMocks()
    mockGetAlerts.mockResolvedValue(mockAlertsResponse)
  })

  it('fetches alert configurations', async () => {
    const { wrapper } = createWrapper()

    const { result } = renderHook(() => useAlerts(), { wrapper })

    await waitFor(() => {
      expect(result.current.isSuccess).toBe(true)
    })

    expect(result.current.data).toEqual(mockAlertsResponse)
    expect(result.current.data?.alerts).toHaveLength(2)
    expect(mockGetAlerts).toHaveBeenCalledTimes(1)
  })

  it('uses correct query key', async () => {
    const { wrapper, queryClient } = createWrapper()

    renderHook(() => useAlerts(), { wrapper })

    await waitFor(() => {
      const queries = queryClient.getQueryCache().getAll()
      const keys = queries.map((q) => q.queryKey)
      expect(keys).toContainEqual(['alerts'])
    })
  })

  it('handles fetch error', async () => {
    mockGetAlerts.mockRejectedValue(new Error('Network error'))

    const { wrapper } = createWrapper()

    const { result } = renderHook(() => useAlerts(), { wrapper })

    await waitFor(() => {
      expect(result.current.isError).toBe(true)
    })

    expect(result.current.error?.message).toBe('Network error')
  })
})

// ==========================================================================
// useAlertHistory
// ==========================================================================
describe('useAlertHistory', () => {
  beforeEach(() => {
    jest.clearAllMocks()
    mockGetAlertHistory.mockResolvedValue(mockHistoryResponse)
  })

  it('fetches alert history with default page', async () => {
    const { wrapper } = createWrapper()

    const { result } = renderHook(() => useAlertHistory(), { wrapper })

    await waitFor(() => {
      expect(result.current.isSuccess).toBe(true)
    })

    expect(result.current.data?.items).toHaveLength(1)
    expect(result.current.data?.total).toBe(1)
    expect(mockGetAlertHistory).toHaveBeenCalledWith(1, 20)
  })

  it('fetches alert history with custom page', async () => {
    const { wrapper } = createWrapper()

    renderHook(() => useAlertHistory(3), { wrapper })

    await waitFor(() => {
      expect(mockGetAlertHistory).toHaveBeenCalledWith(3, 20)
    })
  })

  it('uses page-specific query key', async () => {
    const { wrapper, queryClient } = createWrapper()

    renderHook(() => useAlertHistory(2), { wrapper })

    await waitFor(() => {
      const queries = queryClient.getQueryCache().getAll()
      const keys = queries.map((q) => q.queryKey)
      expect(keys).toContainEqual(['alerts', 'history', 2])
    })
  })
})

// ==========================================================================
// useCreateAlert
// ==========================================================================
describe('useCreateAlert', () => {
  beforeEach(() => {
    jest.clearAllMocks()
    mockCreateAlert.mockResolvedValue({
      id: 'alert-new',
      user_id: 'user-1',
      region: 'us_tx',
      currency: 'USD',
      price_below: 0.15,
      price_above: null,
      notify_optimal_windows: true,
      is_active: true,
      created_at: '2026-03-06T10:00:00Z',
      updated_at: '2026-03-06T10:00:00Z',
    })
  })

  it('creates an alert and invalidates queries on success', async () => {
    const { wrapper, queryClient } = createWrapper()
    const invalidateSpy = jest.spyOn(queryClient, 'invalidateQueries')

    const { result } = renderHook(() => useCreateAlert(), { wrapper })

    await act(async () => {
      await result.current.mutateAsync({
        region: 'us_tx',
        price_below: 0.15,
        notify_optimal_windows: true,
      })
    })

    expect(mockCreateAlert).toHaveBeenCalledWith({
      region: 'us_tx',
      price_below: 0.15,
      notify_optimal_windows: true,
    })

    expect(invalidateSpy).toHaveBeenCalledWith(
      expect.objectContaining({ queryKey: ['alerts'] })
    )
  })

  it('handles creation failure', async () => {
    mockCreateAlert.mockRejectedValue(new Error('Validation failed'))

    const { wrapper } = createWrapper()
    const { result } = renderHook(() => useCreateAlert(), { wrapper })

    await expect(
      act(async () => {
        await result.current.mutateAsync({
          region: 'us_ct',
          price_below: 0.20,
        })
      })
    ).rejects.toThrow('Validation failed')
  })
})

// ==========================================================================
// useUpdateAlert
// ==========================================================================
describe('useUpdateAlert', () => {
  beforeEach(() => {
    jest.clearAllMocks()
    mockUpdateAlert.mockResolvedValue({
      id: 'alert-1',
      user_id: 'user-1',
      region: 'us_ct',
      currency: 'USD',
      price_below: 0.2,
      price_above: null,
      notify_optimal_windows: true,
      is_active: false,
      created_at: '2026-03-01T10:00:00Z',
      updated_at: '2026-03-06T10:00:00Z',
    })
  })

  it('updates an alert and invalidates queries on success', async () => {
    const { wrapper, queryClient } = createWrapper()
    const invalidateSpy = jest.spyOn(queryClient, 'invalidateQueries')

    const { result } = renderHook(() => useUpdateAlert(), { wrapper })

    await act(async () => {
      await result.current.mutateAsync({
        id: 'alert-1',
        body: { is_active: false },
      })
    })

    expect(mockUpdateAlert).toHaveBeenCalledWith('alert-1', { is_active: false })

    expect(invalidateSpy).toHaveBeenCalledWith(
      expect.objectContaining({ queryKey: ['alerts'] })
    )
  })
})

// ==========================================================================
// useDeleteAlert
// ==========================================================================
describe('useDeleteAlert', () => {
  beforeEach(() => {
    jest.clearAllMocks()
    mockDeleteAlert.mockResolvedValue({ deleted: true, alert_id: 'alert-1' })
  })

  it('deletes an alert and invalidates queries on success', async () => {
    const { wrapper, queryClient } = createWrapper()
    const invalidateSpy = jest.spyOn(queryClient, 'invalidateQueries')

    const { result } = renderHook(() => useDeleteAlert(), { wrapper })

    await act(async () => {
      await result.current.mutateAsync('alert-1')
    })

    expect(mockDeleteAlert).toHaveBeenCalledWith('alert-1')

    expect(invalidateSpy).toHaveBeenCalledWith(
      expect.objectContaining({ queryKey: ['alerts'] })
    )
  })

  it('handles deletion failure', async () => {
    mockDeleteAlert.mockRejectedValue(new Error('Alert not found'))

    const { wrapper } = createWrapper()
    const { result } = renderHook(() => useDeleteAlert(), { wrapper })

    await expect(
      act(async () => {
        await result.current.mutateAsync('nonexistent')
      })
    ).rejects.toThrow('Alert not found')
  })
})
