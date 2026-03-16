'use client'

import { useEffect } from 'react'
import { PageErrorFallback } from '@/components/page-error-fallback'

export default function AppError({
  error,
  reset,
}: {
  error: Error & { digest?: string }
  reset: () => void
}) {
  useEffect(() => {
    console.error('App section error:', error)
  }, [error])

  return <PageErrorFallback error={error} onReset={reset} />
}
