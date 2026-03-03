'use client'

import React, { useCallback } from 'react'
import dynamic from 'next/dynamic'
import { Skeleton } from '@/components/ui/skeleton'

/**
 * Local Excalidraw type aliases.
 * The package does not re-export its internal types (AppState, OrderedExcalidrawElement,
 * BinaryFiles) via a path that bundler module resolution can reach. These opaque aliases
 * keep the wrapper boundary typed without pulling in unstable internals.
 * This component is dev-only (triple-gated, notFound in production).
 */
export type ExcalidrawElement = Record<string, unknown>
type ExcalidrawAppState = Record<string, unknown>
type ExcalidrawFiles = Record<string, unknown>

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
  onChange?: (elements: readonly ExcalidrawElement[], appState: ExcalidrawAppState) => void
  theme?: 'light' | 'dark'
}

export function ExcalidrawWrapper({ initialData, onChange, theme = 'light' }: ExcalidrawWrapperProps) {
  const handleChange = useCallback(
    // Excalidraw passes branded internal types; we accept them as our opaque aliases
    (elements: readonly ExcalidrawElement[], appState: ExcalidrawAppState, _files: ExcalidrawFiles) => {
      onChange?.(elements, appState)
    },
    [onChange]
  )

  return (
    <div className="h-full w-full" data-testid="excalidraw-wrapper">
      <Excalidraw
        {...{
          initialData,
          // Cast required: our opaque ExcalidrawAppState alias is structurally
          // compatible but lacks the index signature on the library's AppState.
          // This component is dev-only (triple-gated, notFound in production).
          // eslint-disable-next-line @typescript-eslint/no-explicit-any
          onChange: handleChange as unknown as (elements: any, appState: any, files: any) => void,
          theme,
        }}
      />
    </div>
  )
}
