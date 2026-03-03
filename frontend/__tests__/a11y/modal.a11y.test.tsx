import { render } from '@testing-library/react'
import { axe } from 'jest-axe'
import { Modal } from '@/components/ui/modal'
import '@testing-library/jest-dom'

jest.mock('@/lib/utils/cn', () => ({
  cn: (...args: unknown[]) => args.filter(Boolean).join(' '),
}))

jest.mock('lucide-react', () => ({
  Loader2: (props: React.SVGAttributes<SVGElement>) => <svg data-testid="loader-icon" {...props} />,
  X: (props: React.SVGAttributes<SVGElement>) => <svg data-testid="x-icon" {...props} />,
}))

describe('Modal a11y', () => {
  it('has no accessibility violations when open with title', async () => {
    const { container } = render(
      <Modal open={true} onClose={jest.fn()} title="Confirm action">
        <p>Are you sure you want to proceed?</p>
      </Modal>
    )
    const results = await axe(container)
    expect(results).toHaveNoViolations()
  })

  it('has no accessibility violations with description', async () => {
    const { container } = render(
      <Modal
        open={true}
        onClose={jest.fn()}
        title="Delete account"
        description="This action cannot be undone. Your account will be permanently deleted."
      />
    )
    const results = await axe(container)
    expect(results).toHaveNoViolations()
  })

  it('has no accessibility violations with confirm and cancel buttons', async () => {
    const { container } = render(
      <Modal
        open={true}
        onClose={jest.fn()}
        title="Remove connection"
        description="This will disconnect your utility account."
        confirmLabel="Remove"
        cancelLabel="Keep connection"
        onConfirm={jest.fn()}
      />
    )
    const results = await axe(container)
    expect(results).toHaveNoViolations()
  })

  it('has no accessibility violations with danger variant', async () => {
    const { container } = render(
      <Modal
        open={true}
        onClose={jest.fn()}
        title="Delete data"
        description="All your data will be permanently erased."
        confirmLabel="Delete"
        onConfirm={jest.fn()}
        variant="danger"
      />
    )
    const results = await axe(container)
    expect(results).toHaveNoViolations()
  })

  it('renders nothing when closed (no violations)', async () => {
    const { container } = render(
      <Modal open={false} onClose={jest.fn()} title="Hidden modal" />
    )
    const results = await axe(container)
    expect(results).toHaveNoViolations()
  })
})
