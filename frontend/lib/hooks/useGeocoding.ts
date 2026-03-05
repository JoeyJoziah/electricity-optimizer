'use client'

import { useState, useCallback } from 'react'
import { API_URL } from '@/lib/config/env'

interface GeocodeResult {
  lat: number
  lng: number
  state: string | null
  formatted_address: string | null
}

export function useGeocoding() {
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)

  const geocode = useCallback(async (address: string): Promise<GeocodeResult | null> => {
    setLoading(true)
    setError(null)
    try {
      const resp = await fetch(`${API_URL}/internal/geocode`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ address }),
      })
      if (!resp.ok) {
        setError('Geocoding failed')
        return null
      }
      const data = await resp.json()
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
