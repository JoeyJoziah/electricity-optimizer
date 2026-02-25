'use client'

import React, { useCallback, useEffect, useRef, useState } from 'react'
import { ExcalidrawWrapper } from './ExcalidrawWrapper'
import { Button } from '@/components/ui/button'
import { Skeleton } from '@/components/ui/skeleton'
import { Save, Check } from 'lucide-react'

interface DiagramEditorProps {
  name: string | null
  data: Record<string, unknown> | undefined
  isLoading: boolean
  onSave: (data: Record<string, unknown>) => void
  isSaving: boolean
}

export function DiagramEditor({ name, data, isLoading, onSave, isSaving }: DiagramEditorProps) {
  const [hasChanges, setHasChanges] = useState(false)
  const [showSaved, setShowSaved] = useState(false)
  const latestDataRef = useRef<Record<string, unknown> | null>(null)

  // Reset state when diagram changes
  useEffect(() => {
    setHasChanges(false)
    setShowSaved(false)
    latestDataRef.current = null
  }, [name])

  const handleChange = useCallback((elements: readonly any[], appState: Record<string, unknown>) => {
    latestDataRef.current = {
      type: 'excalidraw',
      version: 2,
      source: 'electricity-optimizer',
      elements: [...elements],
      appState: { gridSize: appState.gridSize ?? null, viewBackgroundColor: appState.viewBackgroundColor ?? '#ffffff' },
      files: {},
    }
    setHasChanges(true)
    setShowSaved(false)
  }, [])

  const handleSave = useCallback(() => {
    if (latestDataRef.current && name) {
      onSave(latestDataRef.current)
      setHasChanges(false)
      setShowSaved(true)
      setTimeout(() => setShowSaved(false), 2000)
    }
  }, [name, onSave])

  // Ctrl+S / Cmd+S shortcut
  useEffect(() => {
    const handleKeyDown = (e: KeyboardEvent) => {
      if ((e.metaKey || e.ctrlKey) && e.key === 's') {
        e.preventDefault()
        handleSave()
      }
    }
    window.addEventListener('keydown', handleKeyDown)
    return () => window.removeEventListener('keydown', handleKeyDown)
  }, [handleSave])

  if (!name) {
    return (
      <div className="flex h-full items-center justify-center text-gray-400">
        Select a diagram or create a new one
      </div>
    )
  }

  if (isLoading) {
    return (
      <div className="flex h-full items-center justify-center" data-testid="editor-loading">
        <Skeleton variant="rectangular" className="h-3/4 w-3/4" />
      </div>
    )
  }

  return (
    <div className="flex h-full flex-col">
      <div className="flex items-center justify-between border-b border-gray-200 px-4 py-2">
        <h3 className="text-sm font-medium text-gray-700">{name}</h3>
        <div className="flex items-center gap-2">
          {showSaved && (
            <span className="flex items-center gap-1 text-xs text-success-600" data-testid="save-indicator">
              <Check className="h-3 w-3" />
              Saved
            </span>
          )}
          {hasChanges && !showSaved && (
            <span className="text-xs text-gray-400">Unsaved changes</span>
          )}
          <Button
            variant="primary"
            size="sm"
            onClick={handleSave}
            disabled={!hasChanges || isSaving}
            aria-label="Save diagram"
          >
            <Save className="mr-1 h-3 w-3" />
            {isSaving ? 'Saving...' : 'Save'}
          </Button>
        </div>
      </div>

      <div className="flex-1">
        <ExcalidrawWrapper
          initialData={data}
          onChange={handleChange}
        />
      </div>
    </div>
  )
}
