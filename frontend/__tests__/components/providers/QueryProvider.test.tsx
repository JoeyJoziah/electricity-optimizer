import { render, screen } from '@testing-library/react'
import '@testing-library/jest-dom'
import { useQuery } from '@tanstack/react-query'
import { QueryProvider } from '@/components/providers/QueryProvider'

// Test that QueryProvider correctly wraps children with a React Query context
// by rendering a component that uses useQuery inside the provider.
function TestConsumer() {
  const { status } = useQuery({
    queryKey: ['test'],
    queryFn: () => Promise.resolve('data'),
    enabled: false,
  })
  return <div data-testid="query-consumer">status: {status}</div>
}

describe('QueryProvider', () => {
  it('renders children without crashing', () => {
    render(
      <QueryProvider>
        <p data-testid="child">Hello</p>
      </QueryProvider>
    )

    expect(screen.getByTestId('child')).toBeInTheDocument()
    expect(screen.getByText('Hello')).toBeInTheDocument()
  })

  it('provides a React Query context to children', () => {
    // If QueryProvider does not wrap a QueryClientProvider, useQuery throws.
    // This test passing proves the context is provided.
    expect(() => {
      render(
        <QueryProvider>
          <TestConsumer />
        </QueryProvider>
      )
    }).not.toThrow()

    expect(screen.getByTestId('query-consumer')).toBeInTheDocument()
  })

  it('useQuery has pending status when query is disabled', () => {
    render(
      <QueryProvider>
        <TestConsumer />
      </QueryProvider>
    )

    // With enabled: false, status should be 'pending'
    expect(screen.getByText(/status: pending/i)).toBeInTheDocument()
  })

  it('renders multiple children', () => {
    render(
      <QueryProvider>
        <p data-testid="first">First</p>
        <p data-testid="second">Second</p>
      </QueryProvider>
    )

    expect(screen.getByTestId('first')).toBeInTheDocument()
    expect(screen.getByTestId('second')).toBeInTheDocument()
  })
})
