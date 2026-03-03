import { render } from '@testing-library/react'
import { axe } from 'jest-axe'
import { Button } from '@/components/ui/button'
import '@testing-library/jest-dom'

jest.mock('@/lib/utils/cn', () => ({
  cn: (...args: unknown[]) => args.filter(Boolean).join(' '),
}))

jest.mock('lucide-react', () => ({
  Loader2: (props: React.SVGAttributes<SVGElement>) => <svg data-testid="loader-icon" {...props} />,
}))

describe('Button a11y', () => {
  it('has no accessibility violations when rendered with text', async () => {
    const { container } = render(<Button>Click me</Button>)
    const results = await axe(container)
    expect(results).toHaveNoViolations()
  })

  it('has no accessibility violations in disabled state', async () => {
    const { container } = render(<Button disabled>Disabled button</Button>)
    const results = await axe(container)
    expect(results).toHaveNoViolations()
  })

  it('has no accessibility violations in loading state', async () => {
    const { container } = render(<Button loading aria-label="Loading, please wait">Loading</Button>)
    const results = await axe(container)
    expect(results).toHaveNoViolations()
  })

  it('has no accessibility violations with danger variant', async () => {
    const { container } = render(<Button variant="danger">Delete item</Button>)
    const results = await axe(container)
    expect(results).toHaveNoViolations()
  })

  it('has no accessibility violations with outline variant', async () => {
    const { container } = render(<Button variant="outline">Cancel</Button>)
    const results = await axe(container)
    expect(results).toHaveNoViolations()
  })
})
