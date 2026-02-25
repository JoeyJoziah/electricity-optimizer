'use client'

import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'

export interface DiagramEntry {
  name: string
  updatedAt: string
}

export interface DiagramData {
  name: string
  data: Record<string, unknown>
}

async function fetchDiagramList(): Promise<DiagramEntry[]> {
  const res = await fetch('/api/dev/diagrams')
  if (!res.ok) throw new Error('Failed to fetch diagrams')
  const json = await res.json()
  return json.diagrams
}

async function fetchDiagram(name: string): Promise<DiagramData> {
  const res = await fetch(`/api/dev/diagrams/${name}`)
  if (!res.ok) throw new Error('Failed to fetch diagram')
  return res.json()
}

async function saveDiagram(name: string, data: Record<string, unknown>): Promise<void> {
  const res = await fetch(`/api/dev/diagrams/${name}`, {
    method: 'PUT',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ data }),
  })
  if (!res.ok) throw new Error('Failed to save diagram')
}

async function createDiagram(name: string): Promise<{ name: string; created: boolean }> {
  const res = await fetch('/api/dev/diagrams', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ name }),
  })
  if (!res.ok) {
    const err = await res.json()
    throw new Error(err.error || 'Failed to create diagram')
  }
  return res.json()
}

export function useDiagramList() {
  return useQuery({
    queryKey: ['diagrams', 'list'],
    queryFn: fetchDiagramList,
  })
}

export function useDiagram(name: string | null) {
  return useQuery({
    queryKey: ['diagrams', 'detail', name],
    queryFn: () => fetchDiagram(name!),
    enabled: !!name,
  })
}

export function useSaveDiagram() {
  const queryClient = useQueryClient()

  return useMutation({
    mutationFn: ({ name, data }: { name: string; data: Record<string, unknown> }) =>
      saveDiagram(name, data),
    onSuccess: (_data, variables) => {
      queryClient.invalidateQueries({ queryKey: ['diagrams', 'detail', variables.name] })
      queryClient.invalidateQueries({ queryKey: ['diagrams', 'list'] })
    },
  })
}

export function useCreateDiagram() {
  const queryClient = useQueryClient()

  return useMutation({
    mutationFn: (name: string) => createDiagram(name),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['diagrams', 'list'] })
    },
  })
}
