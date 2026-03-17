/**
 * Integration tests: SSE streaming via useAgentQuery
 *
 * queryAgent() is a fetch-based async generator that reads a response body
 * via response.body.getReader(). These tests exercise the hook end-to-end by:
 *   - Providing a mock fetch whose body.getReader() returns a controlled mock reader
 *   - Rendering useAgentQuery inside a minimal React component
 *   - Asserting on the messages / isStreaming / error state exposed by the hook
 *
 * We avoid constructing a real ReadableStream (unavailable in jsdom) and instead
 * implement the minimal reader interface { read() } that queryAgent() relies on.
 */

import React from 'react'
import { render, screen, act, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import '@testing-library/jest-dom'
import { TextEncoder, TextDecoder } from 'util'

// jsdom does not provide TextEncoder / TextDecoder — polyfill from Node's util
global.TextEncoder = TextEncoder as typeof global.TextEncoder
global.TextDecoder = TextDecoder as typeof global.TextDecoder

// ---------------------------------------------------------------------------
// Module mocks
// ---------------------------------------------------------------------------

jest.mock('@/lib/auth/client', () => ({
  authClient: {
    useSession: () => ({ data: null, isPending: false, error: null }),
    changePassword: jest.fn(),
    signOut: jest.fn(),
  },
}))

// ---------------------------------------------------------------------------
// Test subject
// ---------------------------------------------------------------------------

import { useAgentQuery } from '@/lib/hooks/useAgent'

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

/**
 * Build a mock reader (compatible with the ReadableStreamDefaultReader interface)
 * from an array of raw SSE line strings.
 *
 * queryAgent() only uses reader.read(), which resolves to { done, value }.
 * Each line is encoded as a Uint8Array chunk; after all lines are consumed the
 * reader signals { done: true }.
 */
function buildMockReader(lines: string[]) {
  const encoder = new TextEncoder()
  const chunks = lines.map((line) => encoder.encode(line + '\n'))
  let index = 0

  return {
    read: jest.fn(async (): Promise<{ done: boolean; value: Uint8Array | undefined }> => {
      if (index < chunks.length) {
        return { done: false, value: chunks[index++] }
      }
      return { done: true, value: undefined }
    }),
  }
}

/**
 * Build a mock response body (only needs a getReader() method).
 */
function buildMockBody(lines: string[]) {
  const reader = buildMockReader(lines)
  return { getReader: () => reader }
}

/**
 * Minimal component that exercises the hook so we can assert on rendered output.
 */
function AgentHarness() {
  const { messages, isStreaming, error, sendQuery, cancel } = useAgentQuery()

  return (
    <div>
      <button onClick={() => sendQuery('tell me about rates')}>Send</button>
      <button onClick={cancel}>Cancel</button>
      {isStreaming && <span data-testid="streaming">streaming</span>}
      {error && <span data-testid="error">{error}</span>}
      <ul>
        {messages.map((m, i) => (
          <li key={i} data-testid={`msg-${i}`} data-role={m.role}>
            {m.content}
          </li>
        ))}
      </ul>
    </div>
  )
}

// ---------------------------------------------------------------------------
// Tests
// ---------------------------------------------------------------------------

const mockFetch = global.fetch as jest.Mock

describe('useAgentQuery — SSE streaming integration', () => {
  beforeEach(() => {
    jest.clearAllMocks()
  })

  it('appends user message immediately before stream resolves', async () => {
    mockFetch.mockResolvedValueOnce({
      ok: true,
      body: buildMockBody(['data: [DONE]']),
    })

    const user = userEvent.setup()
    render(<AgentHarness />)

    await user.click(screen.getByRole('button', { name: 'Send' }))

    await waitFor(() => {
      const userMsg = screen.getByTestId('msg-0')
      expect(userMsg).toHaveAttribute('data-role', 'user')
      expect(userMsg).toHaveTextContent('tell me about rates')
    })
  })

  it('appends assistant messages parsed from SSE data lines', async () => {
    const chunk = JSON.stringify({ role: 'assistant', content: 'Rates are low.' })
    mockFetch.mockResolvedValueOnce({
      ok: true,
      body: buildMockBody([`data: ${chunk}`, 'data: [DONE]']),
    })

    const user = userEvent.setup()
    render(<AgentHarness />)

    await user.click(screen.getByRole('button', { name: 'Send' }))

    await waitFor(() => {
      // msg-0 is user, msg-1 is the assistant response
      const assistantMsg = screen.getByTestId('msg-1')
      expect(assistantMsg).toHaveAttribute('data-role', 'assistant')
      expect(assistantMsg).toHaveTextContent('Rates are low.')
    })
  })

  it('clears isStreaming indicator after the stream completes', async () => {
    mockFetch.mockResolvedValueOnce({
      ok: true,
      body: buildMockBody(['data: [DONE]']),
    })

    const user = userEvent.setup()
    render(<AgentHarness />)

    await user.click(screen.getByRole('button', { name: 'Send' }))

    await waitFor(() => {
      expect(screen.queryByTestId('streaming')).not.toBeInTheDocument()
    })
  })

  it('sets error state and appends error message when server returns non-ok response', async () => {
    mockFetch.mockResolvedValueOnce({
      ok: false,
      status: 500,
      json: async () => ({ detail: 'Internal server error' }),
    })

    const user = userEvent.setup()
    render(<AgentHarness />)

    await user.click(screen.getByRole('button', { name: 'Send' }))

    await waitFor(() => {
      expect(screen.getByTestId('error')).toHaveTextContent('Internal server error')
    })

    // An error-role message should also appear in the message list
    expect(screen.getByTestId('msg-1')).toHaveAttribute('data-role', 'error')
  })

  it('handles a fetch network failure (thrown exception)', async () => {
    mockFetch.mockRejectedValueOnce(new Error('Network failure'))

    const user = userEvent.setup()
    render(<AgentHarness />)

    await user.click(screen.getByRole('button', { name: 'Send' }))

    await waitFor(() => {
      expect(screen.getByTestId('error')).toHaveTextContent('Network failure')
    })
  })

  it('silently aborts without setting error when cancel() is called', async () => {
    // Fetch never resolves — we will reject it with an AbortError to simulate cancellation
    let rejectFetch!: (err: Error) => void
    mockFetch.mockReturnValueOnce(
      new Promise<Response>((_, rej) => {
        rejectFetch = rej
      })
    )

    const user = userEvent.setup()
    render(<AgentHarness />)

    // Start the in-flight request (fire-and-forget — no await)
    act(() => { screen.getByRole('button', { name: 'Send' }).click() })

    // Cancel and simultaneously reject with an AbortError
    await act(async () => {
      screen.getByRole('button', { name: 'Cancel' }).click()
      rejectFetch(Object.assign(new DOMException('Aborted', 'AbortError')))
    })

    await waitFor(() => {
      expect(screen.queryByTestId('streaming')).not.toBeInTheDocument()
    })

    // Abort is treated as user-initiated cancel — no error indicator
    expect(screen.queryByTestId('error')).not.toBeInTheDocument()
  })

  it('skips malformed SSE data lines and still yields valid messages', async () => {
    const valid = JSON.stringify({ role: 'assistant', content: 'OK response' })
    mockFetch.mockResolvedValueOnce({
      ok: true,
      body: buildMockBody([
        'data: {invalid-json!!}',
        `data: ${valid}`,
        'data: [DONE]',
      ]),
    })

    const user = userEvent.setup()
    render(<AgentHarness />)

    await user.click(screen.getByRole('button', { name: 'Send' }))

    await waitFor(() => {
      // msg-0 user, msg-1 valid assistant — malformed line is silently skipped
      expect(screen.getByTestId('msg-1')).toHaveTextContent('OK response')
      expect(screen.queryByTestId('msg-2')).not.toBeInTheDocument()
    })
  })
})
