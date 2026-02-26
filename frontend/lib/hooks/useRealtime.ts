'use client'

import { useEffect, useState, useCallback, useRef } from 'react'
import { useQueryClient } from '@tanstack/react-query'
import { fetchEventSource } from '@microsoft/fetch-event-source'

const API_URL = process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000/api/v1'

export interface RealtimeConfig {
  table: string
  event?: 'INSERT' | 'UPDATE' | 'DELETE' | '*'
  filter?: string
}

export interface PriceUpdate {
  region: string
  supplier: string
  price_per_kwh: string
  currency: string
  is_peak: boolean
  timestamp: string
  source?: string
}

/**
 * Hook for subscribing to real-time price updates via Server-Sent Events.
 *
 * Uses @microsoft/fetch-event-source instead of native EventSource so that
 * session cookies (httpOnly `better-auth.session_token`) are included in the
 * request. Native EventSource doesn't support credentials or custom headers.
 *
 * Connects to the SSE endpoint and invalidates React Query caches
 * when new price data arrives.
 */
export function useRealtimePrices(region: string, interval: number = 30) {
  const queryClient = useQueryClient()
  const [isConnected, setIsConnected] = useState(false)
  const [lastPrice, setLastPrice] = useState<PriceUpdate | null>(null)
  const abortRef = useRef<AbortController | null>(null)
  const retryDelayRef = useRef(1000)
  const mountedRef = useRef(true)

  useEffect(() => {
    mountedRef.current = true
    if (typeof window === 'undefined') return

    const url = `${API_URL}/prices/stream?region=${region}&interval=${interval}`
    const MAX_RETRY_DELAY = 30_000

    const ctrl = new AbortController()
    abortRef.current = ctrl

    fetchEventSource(url, {
      credentials: 'include',
      signal: ctrl.signal,

      onopen: async (response) => {
        if (response.ok) {
          if (!mountedRef.current) return
          setIsConnected(true)
          retryDelayRef.current = 1000 // Reset backoff on successful connect
        } else if (response.status === 401 || response.status === 403) {
          // Auth failure — don't retry
          throw new Error(`Auth failed: ${response.status}`)
        } else {
          throw new Error(`SSE open failed: ${response.status}`)
        }
      },

      onmessage: (event) => {
        if (!event.data) return
        try {
          const data: PriceUpdate = JSON.parse(event.data)
          if (!mountedRef.current) return
          setLastPrice(data)
          queryClient.invalidateQueries({ queryKey: ['prices', 'current', region] })
          queryClient.invalidateQueries({ queryKey: ['prices', 'history', region] })
        } catch {
          // Ignore parse errors for non-JSON events (heartbeats)
        }
      },

      onerror: (err) => {
        if (!mountedRef.current) return
        setIsConnected(false)

        // Exponential backoff: 1s, 2s, 4s, 8s, 16s, 30s cap
        const delay = retryDelayRef.current
        retryDelayRef.current = Math.min(delay * 2, MAX_RETRY_DELAY)

        // Return the delay so fetchEventSource retries after that many ms.
        // Throwing would stop retrying entirely.
        if (err instanceof Error && err.message.startsWith('Auth failed')) {
          throw err // Stop retrying on auth failures
        }

        return delay
      },

      onclose: () => {
        if (!mountedRef.current) return
        setIsConnected(false)
      },

      // Pause SSE when browser tab is hidden to save bandwidth and server connections
      openWhenHidden: false,
    }).catch(() => {
      // fetchEventSource promise rejects when we throw from onerror or abort
      if (mountedRef.current) setIsConnected(false)
    })

    return () => {
      mountedRef.current = false
      ctrl.abort()
      setIsConnected(false)
    }
  }, [region, interval, queryClient])

  const disconnect = useCallback(() => {
    mountedRef.current = false
    if (abortRef.current) {
      abortRef.current.abort()
      abortRef.current = null
      setIsConnected(false)
    }
  }, [])

  return { isConnected, lastPrice, disconnect }
}

/**
 * Hook for subscribing to realtime optimization updates.
 * Falls back to polling if SSE is not available.
 */
export function useRealtimeOptimization() {
  const queryClient = useQueryClient()
  const [isConnected, setIsConnected] = useState(false)

  useEffect(() => {
    // Poll for optimization updates every 60 seconds
    const timer = setInterval(() => {
      queryClient.invalidateQueries({ queryKey: ['optimization'] })
    }, 60_000)

    setIsConnected(true)

    return () => {
      clearInterval(timer)
      setIsConnected(false)
    }
  }, [queryClient])

  return { isConnected }
}

/**
 * Generic hook for subscribing to any table changes.
 * Uses polling as a universal fallback.
 */
export function useRealtimeSubscription(
  config: RealtimeConfig,
  onUpdate?: (payload: unknown) => void
) {
  const queryClient = useQueryClient()
  const [isConnected, setIsConnected] = useState(false)
  const [lastUpdate, setLastUpdate] = useState<Date | null>(null)

  useEffect(() => {
    // Poll every 30 seconds as fallback
    const timer = setInterval(() => {
      setLastUpdate(new Date())
      onUpdate?.({ table: config.table, event: config.event })
    }, 30_000)

    setIsConnected(true)

    return () => {
      clearInterval(timer)
      setIsConnected(false)
    }
  }, [config.table, config.event, config.filter, onUpdate, queryClient])

  return { isConnected, lastUpdate }
}

/**
 * Hook for broadcasting updates to other clients.
 * Placeholder for future WebSocket implementation.
 */
export function useRealtimeBroadcast(channelName: string) {
  const [isConnected, setIsConnected] = useState(false)

  useEffect(() => {
    setIsConnected(true)
    return () => setIsConnected(false)
  }, [channelName])

  const broadcast = useCallback(
    (_event: string, _payload: unknown) => {
      // Future: implement via WebSocket or shared worker
    },
    []
  )

  return { isConnected, broadcast }
}
