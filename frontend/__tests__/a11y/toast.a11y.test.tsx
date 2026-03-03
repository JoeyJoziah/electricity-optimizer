import { render } from '@testing-library/react'
import { axe } from 'jest-axe'
import { Toast } from '@/components/ui/toast'
import '@testing-library/jest-dom'

jest.mock('@/lib/utils/cn', () => ({
  cn: (...args: unknown[]) => args.filter(Boolean).join(' '),
}))

jest.mock('lucide-react', () => ({
  X: (props: React.SVGAttributes<SVGElement>) => <svg data-testid="x-icon" {...props} />,
  CheckCircle: (props: React.SVGAttributes<SVGElement>) => <svg data-testid="check-icon" {...props} />,
  AlertCircle: (props: React.SVGAttributes<SVGElement>) => <svg data-testid="alert-circle-icon" {...props} />,
  AlertTriangle: (props: React.SVGAttributes<SVGElement>) => <svg data-testid="alert-triangle-icon" {...props} />,
  Info: (props: React.SVGAttributes<SVGElement>) => <svg data-testid="info-icon" {...props} />,
}))

const mockDismiss = jest.fn()

describe('Toast a11y', () => {
  beforeEach(() => {
    mockDismiss.mockClear()
  })

  it('has no accessibility violations for success variant', async () => {
    const { container } = render(
      <Toast
        id="toast-1"
        variant="success"
        title="Settings saved"
        onDismiss={mockDismiss}
      />
    )
    const results = await axe(container)
    expect(results).toHaveNoViolations()
  })

  it('has no accessibility violations for error variant', async () => {
    const { container } = render(
      <Toast
        id="toast-2"
        variant="error"
        title="Connection failed"
        description="Could not connect to your utility provider."
        onDismiss={mockDismiss}
      />
    )
    const results = await axe(container)
    expect(results).toHaveNoViolations()
  })

  it('has no accessibility violations for warning variant', async () => {
    const { container } = render(
      <Toast
        id="toast-3"
        variant="warning"
        title="Prices increasing"
        description="Prices are rising in your area."
        onDismiss={mockDismiss}
      />
    )
    const results = await axe(container)
    expect(results).toHaveNoViolations()
  })

  it('has no accessibility violations for info variant', async () => {
    const { container } = render(
      <Toast
        id="toast-4"
        variant="info"
        title="Price data updated"
        onDismiss={mockDismiss}
      />
    )
    const results = await axe(container)
    expect(results).toHaveNoViolations()
  })

  it('has role="alert" and aria-atomic="true" for screen reader announcement', () => {
    const { container } = render(
      <Toast id="toast-5" variant="success" title="Done" onDismiss={mockDismiss} />
    )
    const toastEl = container.querySelector('[role="alert"]')
    expect(toastEl).toBeInTheDocument()
    expect(toastEl).toHaveAttribute('aria-atomic', 'true')
  })

  it('dismiss button has descriptive aria-label', () => {
    const { getByRole } = render(
      <Toast id="toast-6" variant="info" title="Update available" onDismiss={mockDismiss} />
    )
    const dismissBtn = getByRole('button', { name: /dismiss/i })
    expect(dismissBtn).toBeInTheDocument()
  })
})
