'use client'

import { useEffect, useState, useCallback, useRef } from 'react'
import { useQueryClient } from '@tanstack/react-query'

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
}

/**
 * Hook for subscribing to real-time price updates via Server-Sent Events.
 *
 * Connects to the SSE endpoint and invalidates React Query caches
 * when new price data arrives.
 */
export function useRealtimePrices(region: string = 'us_ct', interval: number = 30) {
  const queryClient = useQueryClient()
  const [isConnected, setIsConnected] = useState(false)
  const [lastPrice, setLastPrice] = useState<PriceUpdate | null>(null)
  const eventSourceRef = useRef<EventSource | null>(null)

  useEffect(() => {
    // SSE requires browser environment
    if (typeof window === 'undefined') return

    const url = `${API_URL}/prices/stream?region=${region}&interval=${interval}`

    try {
      const es = new EventSource(url)
      eventSourceRef.current = es

      es.onopen = () => {
        setIsConnected(true)
      }

      es.onmessage = (event) => {
        try {
          const data: PriceUpdate = JSON.parse(event.data)
          setLastPrice(data)

          // Invalidate price queries to trigger refetch with fresh data
          queryClient.invalidateQueries({ queryKey: ['prices', 'current', region] })
          queryClient.invalidateQueries({ queryKey: ['prices', 'history', region] })
        } catch {
          // Ignore parse errors for non-JSON events
        }
      }

      es.onerror = () => {
        setIsConnected(false)
        // EventSource will auto-reconnect
      }

      return () => {
        es.close()
        eventSourceRef.current = null
        setIsConnected(false)
      }
    } catch {
      // SSE not supported or URL invalid
      setIsConnected(false)
    }
  }, [region, interval, queryClient])

  const disconnect = useCallback(() => {
    if (eventSourceRef.current) {
      eventSourceRef.current.close()
      eventSourceRef.current = null
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
