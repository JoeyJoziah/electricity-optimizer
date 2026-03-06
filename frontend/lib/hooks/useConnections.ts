'use client'

import { useQuery } from '@tanstack/react-query'
import { API_ORIGIN } from '@/lib/config/env'

interface Connection {
  id: string
  method: string
  status: string
  supplier_name: string | null
  email_provider: string | null
  last_sync_at: string | null
  last_sync_error: string | null
  current_rate: number | null
  created_at: string
}

interface ConnectionsResponse {
  connections: Connection[]
}

async function fetchConnections(): Promise<ConnectionsResponse> {
  const res = await fetch(`${API_ORIGIN}/api/v1/connections`, {
    credentials: 'include',
  })

  if (res.status === 403) {
    throw Object.assign(new Error('upgrade'), { status: 403 })
  }

  if (!res.ok) {
    throw new Error('Failed to load connections')
  }

  return res.json()
}

export function useConnections() {
  return useQuery({
    queryKey: ['connections'],
    queryFn: fetchConnections,
    staleTime: 30000,
    retry: false,
  })
}
