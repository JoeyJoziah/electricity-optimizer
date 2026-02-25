'use client'

import React from 'react'
import { cn } from '@/lib/utils/cn'
import { Button } from '@/components/ui/button'
import { Skeleton } from '@/components/ui/skeleton'
import { Plus, FileText } from 'lucide-react'
import type { DiagramEntry } from '@/lib/hooks/useDiagrams'

interface DiagramListProps {
  diagrams: DiagramEntry[] | undefined
  isLoading: boolean
  selected: string | null
  onSelect: (name: string) => void
  onCreateClick: () => void
}

export function DiagramList({ diagrams, isLoading, selected, onSelect, onCreateClick }: DiagramListProps) {
  return (
    <div className="flex h-full flex-col border-r border-gray-200 bg-gray-50">
      <div className="flex items-center justify-between border-b border-gray-200 px-4 py-3">
        <h2 className="text-sm font-semibold text-gray-700">Diagrams</h2>
        <Button variant="ghost" size="sm" onClick={onCreateClick} aria-label="Create diagram">
          <Plus className="h-4 w-4" />
        </Button>
      </div>

      <div className="flex-1 overflow-y-auto">
        {isLoading ? (
          <div className="space-y-2 p-4" data-testid="diagram-list-loading">
            <Skeleton variant="text" className="h-8 w-full" />
            <Skeleton variant="text" className="h-8 w-full" />
            <Skeleton variant="text" className="h-8 w-full" />
          </div>
        ) : diagrams && diagrams.length > 0 ? (
          <ul role="list" className="p-2">
            {diagrams.map((d) => (
              <li key={d.name}>
                <button
                  onClick={() => onSelect(d.name)}
                  className={cn(
                    'flex w-full items-center gap-2 rounded-md px-3 py-2 text-left text-sm transition-colors',
                    selected === d.name
                      ? 'bg-primary-100 text-primary-700 font-medium'
                      : 'text-gray-600 hover:bg-gray-100'
                  )}
                >
                  <FileText className="h-4 w-4 flex-shrink-0" />
                  <span className="truncate">{d.name}</span>
                </button>
              </li>
            ))}
          </ul>
        ) : (
          <div className="p-4 text-center text-sm text-gray-500">
            No diagrams yet
          </div>
        )}
      </div>
    </div>
  )
}
