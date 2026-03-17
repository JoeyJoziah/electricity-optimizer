import { render, screen, fireEvent } from '@testing-library/react'
import '@testing-library/jest-dom'
import { ErrorBoundary } from '@/components/error-boundary'
import { PageErrorFallback } from '@/components/page-error-fallback'

// Mock cn utility
jest.mock('@/lib/utils/cn', () => ({
  cn: (...args: unknown[]) => args.filter(Boolean).join(' '),
}))

// Suppress React error boundary console.error noise in tests
const originalConsoleError = console.error
beforeAll(() => {
  console.error = (...args: unknown[]) => {
    const msg = typeof args[0] === 'string' ? args[0] : ''
    if (
      msg.includes('ErrorBoundary') ||
      msg.includes('The above error occurred') ||
      msg.includes('Error: Uncaught')
    ) {
      return
    }
    originalConsoleError(...args)
  }
})
afterAll(() => {
  console.error = originalConsoleError
})

// A component that always throws — return type is `never` because it always throws
function ThrowingComponent({ message }: { message?: string }): never {
  throw new Error(message || 'Test error')
}

// A component that renders normally
function GoodComponent() {
  return <div data-testid="good-child">Working fine</div>
}

// ---- ErrorBoundary Tests ----
describe('ErrorBoundary', () => {
  it('renders children when no error occurs', () => {
    render(
      <ErrorBoundary>
        <GoodComponent />
      </ErrorBoundary>
    )
    expect(screen.getByTestId('good-child')).toBeInTheDocument()
    expect(screen.getByText('Working fine')).toBeInTheDocument()
  })

  it('renders default fallback UI when a child throws', () => {
    render(
      <ErrorBoundary>
        <ThrowingComponent />
      </ErrorBoundary>
    )
    expect(screen.getByRole('alert')).toBeInTheDocument()
    expect(screen.getByText('Something went wrong')).toBeInTheDocument()
    expect(screen.getByText('Test error')).toBeInTheDocument()
    expect(screen.getByText('Try again')).toBeInTheDocument()
  })

  it('displays the error message in default fallback', () => {
    render(
      <ErrorBoundary>
        <ThrowingComponent message="Custom error message" />
      </ErrorBoundary>
    )
    expect(screen.getByText('Custom error message')).toBeInTheDocument()
  })

  it('renders custom fallback when provided', () => {
    render(
      <ErrorBoundary fallback={<div data-testid="custom-fallback">Custom error UI</div>}>
        <ThrowingComponent />
      </ErrorBoundary>
    )
    expect(screen.getByTestId('custom-fallback')).toBeInTheDocument()
    expect(screen.getByText('Custom error UI')).toBeInTheDocument()
    expect(screen.queryByText('Something went wrong')).not.toBeInTheDocument()
  })

  it('calls onError callback when error is caught', () => {
    const onError = jest.fn()
    render(
      <ErrorBoundary onError={onError}>
        <ThrowingComponent message="callback test" />
      </ErrorBoundary>
    )
    expect(onError).toHaveBeenCalledTimes(1)
    expect(onError).toHaveBeenCalledWith(
      expect.objectContaining({ message: 'callback test' }),
      expect.objectContaining({ componentStack: expect.any(String) })
    )
  })

  it('resets error state when Try again is clicked', () => {
    let shouldThrow = true

    function ConditionalThrower() {
      if (shouldThrow) {
        throw new Error('Conditional error')
      }
      return <div data-testid="recovered">Recovered</div>
    }

    render(
      <ErrorBoundary>
        <ConditionalThrower />
      </ErrorBoundary>
    )

    expect(screen.getByText('Something went wrong')).toBeInTheDocument()

    // Fix the error before clicking retry
    shouldThrow = false
    fireEvent.click(screen.getByText('Try again'))

    expect(screen.getByTestId('recovered')).toBeInTheDocument()
    expect(screen.queryByText('Something went wrong')).not.toBeInTheDocument()
  })

  it('catches errors only in its subtree', () => {
    render(
      <div>
        <ErrorBoundary>
          <ThrowingComponent />
        </ErrorBoundary>
        <div data-testid="sibling">Unaffected sibling</div>
      </div>
    )
    expect(screen.getByRole('alert')).toBeInTheDocument()
    expect(screen.getByTestId('sibling')).toBeInTheDocument()
    expect(screen.getByText('Unaffected sibling')).toBeInTheDocument()
  })
})

// ---- PageErrorFallback Tests ----
describe('PageErrorFallback', () => {
  it('renders error message and action buttons', () => {
    render(<PageErrorFallback />)
    expect(screen.getByText('Something went wrong')).toBeInTheDocument()
    expect(screen.getByText('Go back')).toBeInTheDocument()
    expect(screen.getByText('Try again')).toBeInTheDocument()
  })

  it('displays custom error message when error is provided', () => {
    const error = new Error('Page load failed')
    render(<PageErrorFallback error={error} />)
    expect(screen.getByText('Page load failed')).toBeInTheDocument()
  })

  it('displays default message when no error is provided', () => {
    render(<PageErrorFallback />)
    expect(
      screen.getByText('An unexpected error occurred while loading this page.')
    ).toBeInTheDocument()
  })

  it('calls onReset when Try again is clicked', () => {
    const onReset = jest.fn()
    render(<PageErrorFallback onReset={onReset} />)
    fireEvent.click(screen.getByText('Try again'))
    expect(onReset).toHaveBeenCalledTimes(1)
  })

  it('calls window.history.back when Go back is clicked', () => {
    const backSpy = jest.spyOn(window.history, 'back').mockImplementation(() => {})
    render(<PageErrorFallback />)
    fireEvent.click(screen.getByText('Go back'))
    expect(backSpy).toHaveBeenCalledTimes(1)
    backSpy.mockRestore()
  })

  it('calls window.location.reload when Try again is clicked without onReset', () => {
    const reloadMock = jest.fn()
    window.location.reload = reloadMock
    render(<PageErrorFallback />)
    fireEvent.click(screen.getByText('Try again'))
    expect(reloadMock).toHaveBeenCalledTimes(1)
  })
})
