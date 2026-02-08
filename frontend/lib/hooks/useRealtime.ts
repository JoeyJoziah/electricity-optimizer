'use client'

import { useEffect, useState, useCallback, useRef } from 'react'
import { useQueryClient } from '@tanstack/react-query'
import { createClient, RealtimeChannel } from '@supabase/supabase-js'

const supabaseUrl = process.env.NEXT_PUBLIC_SUPABASE_URL || ''
const supabaseKey = process.env.NEXT_PUBLIC_SUPABASE_ANON_KEY || ''

let supabase: ReturnType<typeof createClient> | null = null

function getSupabase() {
  if (!supabase && supabaseUrl && supabaseKey) {
    supabase = createClient(supabaseUrl, supabaseKey)
  }
  return supabase
}

export interface RealtimeConfig {
  table: string
  event?: 'INSERT' | 'UPDATE' | 'DELETE' | '*'
  filter?: string
}

/**
 * Hook for subscribing to realtime price updates
 */
export function useRealtimePrices(region: string = 'uk') {
  const queryClient = useQueryClient()
  const [isConnected, setIsConnected] = useState(false)
  const channelRef = useRef<RealtimeChannel | null>(null)

  useEffect(() => {
    const client = getSupabase()
    if (!client) return

    const channel = client
      .channel(`prices:${region}`)
      .on(
        'postgres_changes',
        {
          event: 'INSERT',
          schema: 'public',
          table: 'price_history',
          filter: `region=eq.${region}`,
        },
        (payload) => {
          // Invalidate price queries to trigger refetch
          queryClient.invalidateQueries({ queryKey: ['prices', 'current', region] })
          queryClient.invalidateQueries({ queryKey: ['prices', 'history', region] })
        }
      )
      .subscribe((status) => {
        setIsConnected(status === 'SUBSCRIBED')
      })

    channelRef.current = channel

    return () => {
      channel.unsubscribe()
    }
  }, [region, queryClient])

  return { isConnected }
}

/**
 * Hook for subscribing to realtime optimization updates
 */
export function useRealtimeOptimization() {
  const queryClient = useQueryClient()
  const [isConnected, setIsConnected] = useState(false)

  useEffect(() => {
    const client = getSupabase()
    if (!client) return

    const channel = client
      .channel('optimization')
      .on(
        'postgres_changes',
        {
          event: '*',
          schema: 'public',
          table: 'optimization_schedules',
        },
        (payload) => {
          queryClient.invalidateQueries({ queryKey: ['optimization'] })
        }
      )
      .subscribe((status) => {
        setIsConnected(status === 'SUBSCRIBED')
      })

    return () => {
      channel.unsubscribe()
    }
  }, [queryClient])

  return { isConnected }
}

/**
 * Generic hook for subscribing to any table changes
 */
export function useRealtimeSubscription(
  config: RealtimeConfig,
  onUpdate?: (payload: unknown) => void
) {
  const queryClient = useQueryClient()
  const [isConnected, setIsConnected] = useState(false)
  const [lastUpdate, setLastUpdate] = useState<Date | null>(null)

  useEffect(() => {
    const client = getSupabase()
    if (!client) return

    const channel = client
      .channel(`table-changes-${config.table}`)
      .on(
        'postgres_changes',
        {
          event: config.event || '*',
          schema: 'public',
          table: config.table,
          filter: config.filter,
        },
        (payload) => {
          setLastUpdate(new Date())
          onUpdate?.(payload)
        }
      )
      .subscribe((status) => {
        setIsConnected(status === 'SUBSCRIBED')
      })

    return () => {
      channel.unsubscribe()
    }
  }, [config, onUpdate, queryClient])

  return { isConnected, lastUpdate }
}

/**
 * Hook for broadcasting updates to other clients
 */
export function useRealtimeBroadcast(channelName: string) {
  const channelRef = useRef<RealtimeChannel | null>(null)
  const [isConnected, setIsConnected] = useState(false)

  useEffect(() => {
    const client = getSupabase()
    if (!client) return

    const channel = client.channel(channelName).subscribe((status) => {
      setIsConnected(status === 'SUBSCRIBED')
    })

    channelRef.current = channel

    return () => {
      channel.unsubscribe()
    }
  }, [channelName])

  const broadcast = useCallback(
    (event: string, payload: unknown) => {
      if (channelRef.current) {
        channelRef.current.send({
          type: 'broadcast',
          event,
          payload,
        })
      }
    },
    []
  )

  return { isConnected, broadcast }
}
