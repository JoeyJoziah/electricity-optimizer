import { renderHook, waitFor, act } from '@testing-library/react'
import React, { ReactNode } from 'react'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import '@testing-library/jest-dom'

const mockGetNotifications = jest.fn()
const mockGetNotificationCount = jest.fn()
const mockMarkNotificationRead = jest.fn()
const mockMarkAllRead = jest.fn()

jest.mock('@/lib/api/notifications', () => ({
  getNotifications: (...args: unknown[]) => mockGetNotifications(...args),
  getNotificationCount: (...args: unknown[]) => mockGetNotificationCount(...args),
  markNotificationRead: (...args: unknown[]) => mockMarkNotificationRead(...args),
  markAllRead: (...args: unknown[]) => mockMarkAllRead(...args),
}))

import {
  useNotifications,
  useNotificationCount,
  useMarkRead,
  useMarkAllRead,
  notificationKeys,
} from '@/lib/hooks/useNotifications'

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

describe('useNotifications', () => {
  beforeEach(() => {
    jest.clearAllMocks()
    mockGetNotifications.mockResolvedValue({
      notifications: [{ id: 'n-1', type: 'rate_drop', title: 'Rate dropped!', body: null, created_at: '2026-03-10' }],
      total: 1,
    })
  })

  it('fetches notifications', async () => {
    const { wrapper } = createWrapper()
    const { result } = renderHook(() => useNotifications(), { wrapper })

    await waitFor(() => expect(result.current.isSuccess).toBe(true))
    expect(result.current.data?.notifications).toHaveLength(1)
  })

  it('uses correct query key', async () => {
    const { wrapper, queryClient } = createWrapper()
    renderHook(() => useNotifications(), { wrapper })

    await waitFor(() => {
      const keys = queryClient.getQueryCache().getAll().map((q) => q.queryKey)
      expect(keys).toContainEqual(notificationKeys.all)
    })
  })

  it('handles error', async () => {
    mockGetNotifications.mockRejectedValue(new Error('Auth required'))
    const { wrapper } = createWrapper()
    const { result } = renderHook(() => useNotifications(), { wrapper })

    await waitFor(() => expect(result.current.isError).toBe(true))
  })
})

describe('useNotificationCount', () => {
  beforeEach(() => {
    jest.clearAllMocks()
    mockGetNotificationCount.mockResolvedValue({ unread: 3 })
  })

  it('fetches unread count', async () => {
    const { wrapper } = createWrapper()
    const { result } = renderHook(() => useNotificationCount(), { wrapper })

    await waitFor(() => expect(result.current.isSuccess).toBe(true))
    expect(result.current.data?.unread).toBe(3)
  })

  it('uses correct query key', async () => {
    const { wrapper, queryClient } = createWrapper()
    renderHook(() => useNotificationCount(), { wrapper })

    await waitFor(() => {
      const keys = queryClient.getQueryCache().getAll().map((q) => q.queryKey)
      expect(keys).toContainEqual(notificationKeys.count)
    })
  })
})

describe('useMarkRead', () => {
  beforeEach(() => {
    jest.clearAllMocks()
    mockMarkNotificationRead.mockResolvedValue({ success: true })
  })

  it('marks notification as read and invalidates queries', async () => {
    const { wrapper, queryClient } = createWrapper()
    const invalidateSpy = jest.spyOn(queryClient, 'invalidateQueries')

    const { result } = renderHook(() => useMarkRead(), { wrapper })

    await act(async () => {
      await result.current.mutateAsync('n-1')
    })

    expect(mockMarkNotificationRead).toHaveBeenCalledWith('n-1')
    expect(invalidateSpy).toHaveBeenCalledWith(
      expect.objectContaining({ queryKey: notificationKeys.all })
    )
    expect(invalidateSpy).toHaveBeenCalledWith(
      expect.objectContaining({ queryKey: notificationKeys.count })
    )
  })
})

describe('useMarkAllRead', () => {
  beforeEach(() => {
    jest.clearAllMocks()
    mockMarkAllRead.mockResolvedValue({ success: true })
  })

  it('marks all as read and invalidates queries', async () => {
    const { wrapper, queryClient } = createWrapper()
    const invalidateSpy = jest.spyOn(queryClient, 'invalidateQueries')

    const { result } = renderHook(() => useMarkAllRead(), { wrapper })

    await act(async () => {
      await result.current.mutateAsync()
    })

    expect(mockMarkAllRead).toHaveBeenCalled()
    expect(invalidateSpy).toHaveBeenCalledWith(
      expect.objectContaining({ queryKey: notificationKeys.all })
    )
    expect(invalidateSpy).toHaveBeenCalledWith(
      expect.objectContaining({ queryKey: notificationKeys.count })
    )
  })
})
