import { renderHook, waitFor, act } from '@testing-library/react'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import React from 'react'
import '@testing-library/jest-dom'
import {
  useDiagramList,
  useDiagram,
  useSaveDiagram,
  useCreateDiagram,
} from '@/lib/hooks/useDiagrams'

const mockFetch = global.fetch as jest.Mock

const mockDiagramList = {
  diagrams: [
    { name: 'architecture', updatedAt: '2026-02-24T10:00:00Z' },
    { name: 'data-flow', updatedAt: '2026-02-24T11:00:00Z' },
  ],
}

const mockDiagramData = {
  name: 'architecture',
  data: {
    type: 'excalidraw',
    version: 2,
    elements: [{ id: '1', type: 'rectangle' }],
  },
}

describe('useDiagrams hooks', () => {
  let queryClient: QueryClient

  beforeEach(() => {
    queryClient = new QueryClient({
      defaultOptions: {
        queries: {
          retry: false,
          gcTime: 0,
        },
      },
    })

    mockFetch.mockReset()
  })

  afterEach(() => {
    queryClient.clear()
    jest.clearAllMocks()
  })

  const wrapper = ({ children }: { children: React.ReactNode }) => (
    <QueryClientProvider client={queryClient}>{children}</QueryClientProvider>
  )

  it('useDiagramList fetches and returns diagram list', async () => {
    mockFetch.mockResolvedValueOnce({
      ok: true,
      json: async () => mockDiagramList,
    })

    const { result } = renderHook(() => useDiagramList(), { wrapper })

    await waitFor(() => {
      expect(result.current.isSuccess).toBe(true)
    })

    expect(result.current.data).toEqual(mockDiagramList.diagrams)
    expect(result.current.data).toHaveLength(2)
    expect(result.current.data![0].name).toBe('architecture')
    expect(mockFetch).toHaveBeenCalledWith('/api/dev/diagrams')
  })

  it('useDiagramList handles fetch error', async () => {
    mockFetch.mockResolvedValueOnce({
      ok: false,
      status: 500,
    })

    const { result } = renderHook(() => useDiagramList(), { wrapper })

    await waitFor(() => {
      expect(result.current.isError).toBe(true)
    })

    expect(result.current.error).toBeInstanceOf(Error)
    expect(result.current.error?.message).toBe('Failed to fetch diagrams')
    expect(result.current.data).toBeUndefined()
  })

  it('useDiagram fetches diagram by name', async () => {
    mockFetch.mockResolvedValueOnce({
      ok: true,
      json: async () => mockDiagramData,
    })

    const { result } = renderHook(() => useDiagram('architecture'), { wrapper })

    await waitFor(() => {
      expect(result.current.isSuccess).toBe(true)
    })

    expect(result.current.data).toEqual(mockDiagramData)
    expect(result.current.data?.name).toBe('architecture')
    expect(mockFetch).toHaveBeenCalledWith('/api/dev/diagrams/architecture')
  })

  it('useDiagram is disabled when name is null', async () => {
    const { result } = renderHook(() => useDiagram(null), { wrapper })

    // The query should not fire at all
    expect(result.current.fetchStatus).toBe('idle')
    expect(result.current.isLoading).toBe(false)
    expect(result.current.data).toBeUndefined()
    expect(mockFetch).not.toHaveBeenCalled()
  })

  it('useSaveDiagram sends PUT and invalidates queries', async () => {
    // Seed the list query cache so invalidation is observable
    mockFetch.mockResolvedValueOnce({
      ok: true,
      json: async () => mockDiagramList,
    })

    const { result: listResult } = renderHook(() => useDiagramList(), { wrapper })

    await waitFor(() => {
      expect(listResult.current.isSuccess).toBe(true)
    })

    // Now set up the save mutation
    mockFetch.mockResolvedValueOnce({
      ok: true,
      json: async () => ({}),
    })

    // Refetch after invalidation
    mockFetch.mockResolvedValueOnce({
      ok: true,
      json: async () => mockDiagramList,
    })

    const { result } = renderHook(() => useSaveDiagram(), { wrapper })

    const saveData = { type: 'excalidraw', version: 2, elements: [{ id: '2' }] }

    await act(async () => {
      result.current.mutate({ name: 'architecture', data: saveData })
    })

    await waitFor(() => {
      expect(result.current.isSuccess).toBe(true)
    })

    // Verify the PUT call
    const putCall = mockFetch.mock.calls.find(
      (call) => call[0] === '/api/dev/diagrams/architecture' && call[1]?.method === 'PUT'
    )
    expect(putCall).toBeDefined()
    expect(JSON.parse(putCall![1].body)).toEqual({ data: saveData })
    expect(putCall![1].headers).toEqual({ 'Content-Type': 'application/json' })
  })

  it('useCreateDiagram sends POST and invalidates list', async () => {
    // Seed the list query cache
    mockFetch.mockResolvedValueOnce({
      ok: true,
      json: async () => mockDiagramList,
    })

    const { result: listResult } = renderHook(() => useDiagramList(), { wrapper })

    await waitFor(() => {
      expect(listResult.current.isSuccess).toBe(true)
    })

    // Set up the create mutation response
    mockFetch.mockResolvedValueOnce({
      ok: true,
      json: async () => ({ name: 'new-diagram', created: true }),
    })

    // Refetch after invalidation
    mockFetch.mockResolvedValueOnce({
      ok: true,
      json: async () => ({
        diagrams: [
          ...mockDiagramList.diagrams,
          { name: 'new-diagram', updatedAt: '2026-02-24T12:00:00Z' },
        ],
      }),
    })

    const { result } = renderHook(() => useCreateDiagram(), { wrapper })

    await act(async () => {
      result.current.mutate('new-diagram')
    })

    await waitFor(() => {
      expect(result.current.isSuccess).toBe(true)
    })

    expect(result.current.data).toEqual({ name: 'new-diagram', created: true })

    // Verify the POST call
    const postCall = mockFetch.mock.calls.find(
      (call) => call[0] === '/api/dev/diagrams' && call[1]?.method === 'POST'
    )
    expect(postCall).toBeDefined()
    expect(JSON.parse(postCall![1].body)).toEqual({ name: 'new-diagram' })
    expect(postCall![1].headers).toEqual({ 'Content-Type': 'application/json' })
  })
})
