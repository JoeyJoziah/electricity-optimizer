'use client'

import { useState, useCallback, useRef } from 'react'
import { useQuery } from '@tanstack/react-query'
import {
  queryAgent,
  getAgentUsage,
  type AgentMessage,
} from '@/lib/api/agent'

/**
 * Hook for streaming agent queries
 */
export function useAgentQuery() {
  const [messages, setMessages] = useState<AgentMessage[]>([])
  const [isStreaming, setIsStreaming] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const abortRef = useRef<AbortController | null>(null)

  const sendQuery = useCallback(async (prompt: string) => {
    setError(null)
    setIsStreaming(true)

    // Add user message
    const userMsg: AgentMessage = { role: 'user', content: prompt }
    setMessages((prev) => [...prev, userMsg])

    try {
      for await (const msg of queryAgent(prompt)) {
        if (msg.role === 'error') {
          setError(msg.content)
        }
        setMessages((prev) => [...prev, msg])
      }
    } catch (err) {
      const errMsg = err instanceof Error ? err.message : 'Unknown error'
      setError(errMsg)
      setMessages((prev) => [
        ...prev,
        { role: 'error', content: errMsg },
      ])
    } finally {
      setIsStreaming(false)
    }
  }, [])

  const cancel = useCallback(() => {
    abortRef.current?.abort()
    setIsStreaming(false)
  }, [])

  const reset = useCallback(() => {
    setMessages([])
    setError(null)
    setIsStreaming(false)
  }, [])

  return { messages, isStreaming, error, sendQuery, cancel, reset }
}

/**
 * Hook for agent usage stats (TanStack Query)
 */
export function useAgentStatus() {
  return useQuery({
    queryKey: ['agent', 'usage'],
    queryFn: () => getAgentUsage(),
    staleTime: 60000, // 1 minute
    retry: false,
  })
}
