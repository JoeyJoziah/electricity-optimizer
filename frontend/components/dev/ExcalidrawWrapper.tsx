'use client'

import React, { useCallback } from 'react'
import dynamic from 'next/dynamic'
import { Skeleton } from '@/components/ui/skeleton'

const Excalidraw = dynamic(
  () => import('@excalidraw/excalidraw').then((mod) => mod.Excalidraw),
  {
    ssr: false,
    loading: () => (
      <div className="flex h-full items-center justify-center" data-testid="excalidraw-loading">
        <Skeleton variant="rectangular" className="h-full w-full" />
      </div>
    ),
  }
)

interface ExcalidrawWrapperProps {
  initialData?: Record<string, unknown>
  onChange?: (elements: readonly any[], appState: Record<string, unknown>) => void
  theme?: 'light' | 'dark'
}

export function ExcalidrawWrapper({ initialData, onChange, theme = 'light' }: ExcalidrawWrapperProps) {
  const handleChange = useCallback(
    (elements: readonly any[], appState: any, files: any) => {
      onChange?.(elements, appState)
    },
    [onChange]
  )

  return (
    <div className="h-full w-full" data-testid="excalidraw-wrapper">
      <Excalidraw
        initialData={initialData as any}
        onChange={handleChange as any}
        theme={theme}
      />
    </div>
  )
}
