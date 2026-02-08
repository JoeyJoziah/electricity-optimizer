'use client'

import { useEffect } from 'react'
import { Header } from '@/components/layout/Header'

export default function SuppliersError({
  error,
  reset,
}: {
  error: Error & { digest?: string }
  reset: () => void
}) {
  useEffect(() => {
    console.error('Suppliers error:', error)
  }, [error])

  return (
    <div>
      <Header title="Suppliers" />
      <div className="flex h-96 items-center justify-center p-6">
        <div className="text-center">
          <h2 className="text-xl font-bold text-gray-900">Supplier Data Error</h2>
          <p className="mt-2 text-gray-600">
            Failed to load supplier data. Please try again.
          </p>
          <button
            onClick={reset}
            className="mt-4 rounded-lg bg-primary-600 px-4 py-2 text-white hover:bg-primary-700"
          >
            Reload Suppliers
          </button>
        </div>
      </div>
    </div>
  )
}
