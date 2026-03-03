import { render } from '@testing-library/react'
import { axe } from 'jest-axe'
import { Input, Checkbox } from '@/components/ui/input'
import '@testing-library/jest-dom'

jest.mock('@/lib/utils/cn', () => ({
  cn: (...args: unknown[]) => args.filter(Boolean).join(' '),
}))

describe('Input a11y', () => {
  it('has no accessibility violations with label', async () => {
    const { container } = render(<Input label="Email address" placeholder="you@example.com" />)
    const results = await axe(container)
    expect(results).toHaveNoViolations()
  })

  it('has no accessibility violations with error state', async () => {
    const { container } = render(
      <Input label="Email address" error="Please enter a valid email address" />
    )
    const results = await axe(container)
    expect(results).toHaveNoViolations()
  })

  it('has no accessibility violations with helper text', async () => {
    const { container } = render(
      <Input label="Password" helperText="Must be at least 12 characters" type="password" />
    )
    const results = await axe(container)
    expect(results).toHaveNoViolations()
  })

  it('has no accessibility violations in disabled state', async () => {
    const { container } = render(<Input label="Username" disabled />)
    const results = await axe(container)
    expect(results).toHaveNoViolations()
  })
})

describe('Checkbox a11y', () => {
  it('has no accessibility violations', async () => {
    const { container } = render(<Checkbox label="Accept terms and conditions" />)
    const results = await axe(container)
    expect(results).toHaveNoViolations()
  })

  it('has no accessibility violations when checked', async () => {
    const { container } = render(
      <Checkbox label="Subscribe to newsletter" defaultChecked />
    )
    const results = await axe(container)
    expect(results).toHaveNoViolations()
  })

  it('has no accessibility violations when disabled', async () => {
    const { container } = render(<Checkbox label="Feature unavailable" disabled />)
    const results = await axe(container)
    expect(results).toHaveNoViolations()
  })
})
