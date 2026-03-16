'use client'

import { useQuery } from '@tanstack/react-query'
import { apiClient, ApiClientError } from '@/lib/api/client'

export interface Connection {
  id: string
  method: string
  status: string
  supplier_name: string | null
  email_provider: string | null
  last_sync_at: string | null
  last_sync_error: string | null
  current_rate: number | null
  created_at: string
  label?: string | null
  connection_type?: string
}

interface ConnectionsResponse {
  connections: Connection[]
}

async function fetchConnections(): Promise<ConnectionsResponse> {
  try {
    const data = await apiClient.get<ConnectionsResponse>('/connections')
    // Map backend connection_type to frontend method for compat
    data.connections = data.connections.map((c: Connection) => ({
      ...c,
      method: c.connection_type ?? c.method,
    }))
    return data
  } catch (err) {
    if (err instanceof ApiClientError && err.status === 403) {
      throw Object.assign(new Error('upgrade'), { status: 403 })
    }
    throw new Error('Failed to load connections')
  }
}

export function useConnections() {
  return useQuery({
    queryKey: ['connections'],
    queryFn: fetchConnections,
    staleTime: 30000,
    retry: false,
  })
}
