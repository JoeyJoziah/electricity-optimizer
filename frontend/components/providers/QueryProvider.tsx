'use client'

import React, { useState } from 'react'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'

export function QueryProvider({ children }: { children: React.ReactNode }) {
  const [queryClient] = useState(
    () =>
      new QueryClient({
        defaultOptions: {
          queries: {
            staleTime: 60 * 1000, // 1 minute
            gcTime: 5 * 60 * 1000, // 5 minutes
            refetchOnWindowFocus: true,
            // Do not retry 4xx errors — they indicate client/auth problems that
            // won't resolve on retry and only delay the redirect to login.
            retry: (failureCount, error) => {
              if (
                error &&
                typeof error === 'object' &&
                'status' in error &&
                typeof (error as { status: unknown }).status === 'number' &&
                (error as { status: number }).status < 500
              ) {
                return false
              }
              return failureCount < 2
            },
            retryDelay: (attemptIndex) =>
              Math.min(1000 * 2 ** attemptIndex, 30000),
          },
        },
      })
  )

  return (
    <QueryClientProvider client={queryClient}>{children}</QueryClientProvider>
  )
}
