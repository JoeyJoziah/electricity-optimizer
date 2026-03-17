'use client'

import { useState, useCallback } from 'react'
import { apiClient } from '@/lib/api/client'

interface GeocodeResult {
  lat: number
  lng: number
  state: string | null
  formatted_address: string | null
}

interface GeocodeResponse {
  result: GeocodeResult | null
}

export function useGeocoding() {
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)

  const geocode = useCallback(async (address: string): Promise<GeocodeResult | null> => {
    setLoading(true)
    setError(null)
    try {
      const data = await apiClient.post<GeocodeResponse>('/geocode', { address })
      return data.result ?? null
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Geocoding failed')
      return null
    } finally {
      setLoading(false)
    }
  }, [])

  return { geocode, loading, error }
}
