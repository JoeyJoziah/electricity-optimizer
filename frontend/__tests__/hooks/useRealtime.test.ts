import { renderHook, act, waitFor } from '@testing-library/react'
import React, { ReactNode } from 'react'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import '@testing-library/jest-dom'

// --- Mock fetchEventSource ---

// Capture the callbacks so tests can invoke them
let capturedCallbacks: {
  onopen?: (response: { ok: boolean; status: number }) => Promise<void>
  onmessage?: (event: { data: string }) => void
  onerror?: (err: Error) => number | void
  onclose?: () => void
  signal?: AbortSignal
} = {}

const mockFetchEventSource = jest.fn(
  async (_url: string, options: Record<string, unknown>) => {
    capturedCallbacks = {
      onopen: options.onopen as typeof capturedCallbacks.onopen,
      onmessage: options.onmessage as typeof capturedCallbacks.onmessage,
      onerror: options.onerror as typeof capturedCallbacks.onerror,
      onclose: options.onclose as typeof capturedCallbacks.onclose,
      signal: options.signal as AbortSignal,
    }
    // Simulate a successful connection by default
    if (capturedCallbacks.onopen) {
      await capturedCallbacks.onopen({ ok: true, status: 200 })
    }
  }
)

jest.mock('@microsoft/fetch-event-source', () => ({
  fetchEventSource: (...args: unknown[]) =>
    mockFetchEventSource(...(args as Parameters<typeof mockFetchEventSource>)),
}))

// Import hooks after mocks
import {
  useRealtimePrices,
  useRealtimeOptimization,
  useRealtimeSubscription,
  useRealtimeBroadcast,
} from '@/lib/hooks/useRealtime'

// --- Test helpers ---

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

// ==========================================================================
// useRealtimePrices
// ==========================================================================
describe('useRealtimePrices', () => {
  beforeEach(() => {
    jest.clearAllMocks()
    capturedCallbacks = {}
    jest.useFakeTimers()
  })

  afterEach(() => {
    jest.useRealTimers()
  })

  it('connects to SSE endpoint with correct URL', async () => {
    const { wrapper } = createWrapper()

    renderHook(() => useRealtimePrices('us_ct', 30), { wrapper })

    // fetchEventSource is called asynchronously in useEffect
    await waitFor(() => {
      expect(mockFetchEventSource).toHaveBeenCalledTimes(1)
    })

    const url = mockFetchEventSource.mock.calls[0][0]
    expect(url).toContain('/prices/stream')
    expect(url).toContain('region=us_ct')
    expect(url).toContain('interval=30')
  })

  it('sets isConnected to true on successful connection', async () => {
    const { wrapper } = createWrapper()

    const { result } = renderHook(() => useRealtimePrices(), { wrapper })

    await waitFor(() => {
      expect(result.current.isConnected).toBe(true)
    })
  })

  it('starts with lastPrice as null', async () => {
    const { wrapper } = createWrapper()

    const { result } = renderHook(() => useRealtimePrices(), { wrapper })

    expect(result.current.lastPrice).toBeNull()
  })

  it('updates lastPrice when a message arrives', async () => {
    const { wrapper, queryClient } = createWrapper()
    const invalidateSpy = jest.spyOn(queryClient, 'invalidateQueries')

    const { result } = renderHook(() => useRealtimePrices('us_ct'), { wrapper })

    await waitFor(() => {
      expect(capturedCallbacks.onmessage).toBeDefined()
    })

    const priceData = {
      region: 'us_ct',
      supplier: 'Eversource',
      price_per_kwh: '0.25',
      currency: 'USD',
      is_peak: true,
      timestamp: '2026-02-25T12:00:00Z',
    }

    act(() => {
      capturedCallbacks.onmessage!({ data: JSON.stringify(priceData) })
    })

    expect(result.current.lastPrice).toEqual(priceData)

    // Should invalidate price queries
    expect(invalidateSpy).toHaveBeenCalledWith(
      expect.objectContaining({
        queryKey: ['prices', 'current', 'us_ct'],
      })
    )
    expect(invalidateSpy).toHaveBeenCalledWith(
      expect.objectContaining({
        queryKey: ['prices', 'history', 'us_ct'],
      })
    )
  })

  it('ignores messages with empty data', async () => {
    const { wrapper } = createWrapper()

    const { result } = renderHook(() => useRealtimePrices(), { wrapper })

    await waitFor(() => {
      expect(capturedCallbacks.onmessage).toBeDefined()
    })

    act(() => {
      capturedCallbacks.onmessage!({ data: '' })
    })

    expect(result.current.lastPrice).toBeNull()
  })

  it('ignores non-JSON messages (heartbeats)', async () => {
    const { wrapper } = createWrapper()

    const { result } = renderHook(() => useRealtimePrices(), { wrapper })

    await waitFor(() => {
      expect(capturedCallbacks.onmessage).toBeDefined()
    })

    act(() => {
      capturedCallbacks.onmessage!({ data: ':heartbeat' })
    })

    expect(result.current.lastPrice).toBeNull()
  })

  it('sets isConnected to false on error', async () => {
    const { wrapper } = createWrapper()

    const { result } = renderHook(() => useRealtimePrices(), { wrapper })

    await waitFor(() => {
      expect(result.current.isConnected).toBe(true)
    })

    act(() => {
      capturedCallbacks.onerror!(new Error('connection lost'))
    })

    expect(result.current.isConnected).toBe(false)
  })

  it('returns exponential backoff delay on retryable error', async () => {
    const { wrapper } = createWrapper()

    renderHook(() => useRealtimePrices(), { wrapper })

    await waitFor(() => {
      expect(capturedCallbacks.onerror).toBeDefined()
    })

    // First retry: 1000ms
    const delay1 = capturedCallbacks.onerror!(new Error('server error'))
    expect(delay1).toBe(1000)

    // Second retry: 2000ms
    const delay2 = capturedCallbacks.onerror!(new Error('server error'))
    expect(delay2).toBe(2000)

    // Third retry: 4000ms
    const delay3 = capturedCallbacks.onerror!(new Error('server error'))
    expect(delay3).toBe(4000)
  })

  it('stops retrying on auth failure', async () => {
    const { wrapper } = createWrapper()

    renderHook(() => useRealtimePrices(), { wrapper })

    await waitFor(() => {
      expect(capturedCallbacks.onerror).toBeDefined()
    })

    expect(() => {
      capturedCallbacks.onerror!(new Error('Auth failed: 401'))
    }).toThrow('Auth failed: 401')
  })

  it('sets isConnected to false on close', async () => {
    const { wrapper } = createWrapper()

    const { result } = renderHook(() => useRealtimePrices(), { wrapper })

    await waitFor(() => {
      expect(result.current.isConnected).toBe(true)
    })

    act(() => {
      capturedCallbacks.onclose!()
    })

    expect(result.current.isConnected).toBe(false)
  })

  it('disconnect aborts the connection', async () => {
    const { wrapper } = createWrapper()

    const { result } = renderHook(() => useRealtimePrices(), { wrapper })

    await waitFor(() => {
      expect(result.current.isConnected).toBe(true)
    })

    act(() => {
      result.current.disconnect()
    })

    expect(result.current.isConnected).toBe(false)
  })

  it('aborts connection on unmount (cleanup)', async () => {
    const { wrapper } = createWrapper()

    const { unmount } = renderHook(() => useRealtimePrices(), { wrapper })

    await waitFor(() => {
      expect(mockFetchEventSource).toHaveBeenCalled()
    })

    // Capture the abort controller from the signal
    const signal = capturedCallbacks.signal
    expect(signal).toBeDefined()

    unmount()

    // After unmount, the signal should be aborted
    expect(signal!.aborted).toBe(true)
  })

  it('reconnects when region changes', async () => {
    const { wrapper } = createWrapper()

    const { rerender } = renderHook(
      ({ region }: { region: string }) => useRealtimePrices(region),
      {
        wrapper,
        initialProps: { region: 'us_ct' },
      }
    )

    await waitFor(() => {
      expect(mockFetchEventSource).toHaveBeenCalledTimes(1)
    })

    const firstUrl = mockFetchEventSource.mock.calls[0][0]
    expect(firstUrl).toContain('region=us_ct')

    rerender({ region: 'us_ny' })

    await waitFor(() => {
      expect(mockFetchEventSource).toHaveBeenCalledTimes(2)
    })

    const secondUrl = mockFetchEventSource.mock.calls[1][0]
    expect(secondUrl).toContain('region=us_ny')
  })

  it('handles auth failure on open (non-OK response)', async () => {
    // Override the default mock to simulate auth failure
    mockFetchEventSource.mockImplementationOnce(
      async (_url: string, options: Record<string, unknown>) => {
        const onopen = options.onopen as (
          response: { ok: boolean; status: number }
        ) => Promise<void>
        try {
          await onopen({ ok: false, status: 401 })
        } catch {
          // Expected - auth failure throws
        }
      }
    )

    const { wrapper } = createWrapper()

    const { result } = renderHook(() => useRealtimePrices(), { wrapper })

    // Should NOT be connected after auth failure
    await waitFor(() => {
      expect(mockFetchEventSource).toHaveBeenCalled()
    })

    expect(result.current.isConnected).toBe(false)
  })

  it('uses credentials: include for cookie auth', async () => {
    const { wrapper } = createWrapper()

    renderHook(() => useRealtimePrices(), { wrapper })

    await waitFor(() => {
      expect(mockFetchEventSource).toHaveBeenCalledTimes(1)
    })

    const options = mockFetchEventSource.mock.calls[0][1]
    expect(options.credentials).toBe('include')
  })
})

// ==========================================================================
// useRealtimeOptimization
// ==========================================================================
describe('useRealtimeOptimization', () => {
  beforeEach(() => {
    jest.useFakeTimers()
  })

  afterEach(() => {
    jest.useRealTimers()
  })

  it('returns isConnected true immediately', () => {
    const { wrapper, queryClient } = createWrapper()

    const { result } = renderHook(() => useRealtimeOptimization(), { wrapper })

    expect(result.current.isConnected).toBe(true)
  })

  it('invalidates optimization queries every 60 seconds', () => {
    const { wrapper, queryClient } = createWrapper()
    const invalidateSpy = jest.spyOn(queryClient, 'invalidateQueries')

    renderHook(() => useRealtimeOptimization(), { wrapper })

    // No invalidation yet
    expect(invalidateSpy).not.toHaveBeenCalled()

    // Advance 60 seconds
    act(() => {
      jest.advanceTimersByTime(60_000)
    })

    expect(invalidateSpy).toHaveBeenCalledWith(
      expect.objectContaining({ queryKey: ['optimization'] })
    )

    // Another 60 seconds
    act(() => {
      jest.advanceTimersByTime(60_000)
    })

    expect(invalidateSpy).toHaveBeenCalledTimes(2)
  })

  it('cleans up interval on unmount', () => {
    const { wrapper } = createWrapper()

    const { result, unmount } = renderHook(() => useRealtimeOptimization(), {
      wrapper,
    })

    expect(result.current.isConnected).toBe(true)

    unmount()

    // After unmount, isConnected cleanup runs
    // (We can't directly check state after unmount, but we verify no errors)
  })
})

// ==========================================================================
// useRealtimeSubscription
// ==========================================================================
describe('useRealtimeSubscription', () => {
  beforeEach(() => {
    jest.useFakeTimers()
  })

  afterEach(() => {
    jest.useRealTimers()
  })

  it('returns isConnected true', () => {
    const { wrapper } = createWrapper()

    const { result } = renderHook(
      () =>
        useRealtimeSubscription({
          table: 'electricity_prices',
          event: 'INSERT',
        }),
      { wrapper }
    )

    expect(result.current.isConnected).toBe(true)
    expect(result.current.lastUpdate).toBeNull()
  })

  it('calls onUpdate callback every 30 seconds', () => {
    const { wrapper } = createWrapper()
    const onUpdate = jest.fn()

    renderHook(
      () =>
        useRealtimeSubscription(
          { table: 'electricity_prices', event: '*' },
          onUpdate
        ),
      { wrapper }
    )

    expect(onUpdate).not.toHaveBeenCalled()

    act(() => {
      jest.advanceTimersByTime(30_000)
    })

    expect(onUpdate).toHaveBeenCalledTimes(1)
    expect(onUpdate).toHaveBeenCalledWith({
      table: 'electricity_prices',
      event: '*',
    })

    act(() => {
      jest.advanceTimersByTime(30_000)
    })

    expect(onUpdate).toHaveBeenCalledTimes(2)
  })

  it('updates lastUpdate timestamp on poll', () => {
    const { wrapper } = createWrapper()

    const { result } = renderHook(
      () => useRealtimeSubscription({ table: 'users' }),
      { wrapper }
    )

    expect(result.current.lastUpdate).toBeNull()

    act(() => {
      jest.advanceTimersByTime(30_000)
    })

    expect(result.current.lastUpdate).toBeInstanceOf(Date)
  })

  it('cleans up on unmount', () => {
    const { wrapper } = createWrapper()
    const onUpdate = jest.fn()

    const { unmount } = renderHook(
      () =>
        useRealtimeSubscription(
          { table: 'electricity_prices' },
          onUpdate
        ),
      { wrapper }
    )

    unmount()

    // Advancing time after unmount should not call onUpdate
    act(() => {
      jest.advanceTimersByTime(60_000)
    })

    expect(onUpdate).not.toHaveBeenCalled()
  })
})

// ==========================================================================
// useRealtimeBroadcast
// ==========================================================================
describe('useRealtimeBroadcast', () => {
  it('returns isConnected true', () => {
    const { wrapper } = createWrapper()

    const { result } = renderHook(() => useRealtimeBroadcast('test-channel'), {
      wrapper,
    })

    expect(result.current.isConnected).toBe(true)
    expect(typeof result.current.broadcast).toBe('function')
  })

  it('broadcast function is callable (placeholder)', () => {
    const { wrapper } = createWrapper()

    const { result } = renderHook(
      () => useRealtimeBroadcast('price-updates'),
      { wrapper }
    )

    // Should not throw
    expect(() => {
      result.current.broadcast('price_change', { price: 0.25 })
    }).not.toThrow()
  })

  it('reconnects when channel name changes', () => {
    const { wrapper } = createWrapper()

    const { result, rerender } = renderHook(
      ({ channel }: { channel: string }) => useRealtimeBroadcast(channel),
      {
        wrapper,
        initialProps: { channel: 'channel-1' },
      }
    )

    expect(result.current.isConnected).toBe(true)

    rerender({ channel: 'channel-2' })

    expect(result.current.isConnected).toBe(true)
  })
})
