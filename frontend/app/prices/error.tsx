'use client'

import { useEffect } from 'react'
import { Header } from '@/components/layout/Header'

export default function PricesError({
  error,
  reset,
}: {
  error: Error & { digest?: string }
  reset: () => void
}) {
  useEffect(() => {
    console.error('Prices error:', error)
  }, [error])

  return (
    <div>
      <Header title="Prices" />
      <div className="flex h-96 items-center justify-center p-6">
        <div className="text-center">
          <h2 className="text-xl font-bold text-gray-900">Price Data Error</h2>
          <p className="mt-2 text-gray-600">
            Failed to load price data. Please try again.
          </p>
          <button
            onClick={reset}
            className="mt-4 rounded-lg bg-primary-600 px-4 py-2 text-white hover:bg-primary-700"
          >
            Reload Prices
          </button>
        </div>
      </div>
    </div>
  )
}
