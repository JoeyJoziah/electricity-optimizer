'use client'

import React, { useState, useCallback } from 'react'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { DiagramList } from '@/components/dev/DiagramList'
import { DiagramEditor } from '@/components/dev/DiagramEditor'
import { useDiagramList, useDiagram, useSaveDiagram, useCreateDiagram } from '@/lib/hooks/useDiagrams'

const queryClient = new QueryClient()

function ArchitectureContent() {
  const [selected, setSelected] = useState<string | null>(null)
  const { data: diagrams, isLoading: listLoading } = useDiagramList()
  const { data: diagramDetail, isLoading: detailLoading } = useDiagram(selected)
  const saveMutation = useSaveDiagram()
  const createMutation = useCreateDiagram()

  const handleSave = useCallback(
    (data: Record<string, unknown>) => {
      if (selected) {
        saveMutation.mutate({ name: selected, data })
      }
    },
    [selected, saveMutation]
  )

  const handleCreate = useCallback(() => {
    const name = window.prompt('Diagram name (letters, numbers, hyphens, underscores):')
    if (name) {
      createMutation.mutate(name, {
        onSuccess: () => setSelected(name),
      })
    }
  }, [createMutation])

  return (
    <div className="flex flex-1 overflow-hidden">
      <div className="w-64 flex-shrink-0">
        <DiagramList
          diagrams={diagrams}
          isLoading={listLoading}
          selected={selected}
          onSelect={setSelected}
          onCreateClick={handleCreate}
        />
      </div>
      <div className="flex-1">
        <DiagramEditor
          name={selected}
          data={diagramDetail?.data}
          isLoading={detailLoading}
          onSave={handleSave}
          isSaving={saveMutation.isPending}
        />
      </div>
    </div>
  )
}

export default function ArchitecturePage() {
  return (
    <QueryClientProvider client={queryClient}>
      <ArchitectureContent />
    </QueryClientProvider>
  )
}
